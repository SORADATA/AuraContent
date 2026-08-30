import os
import requests
from dotenv import load_dotenv

load_dotenv()

REQUEST_TIMEOUT = 15  # secondes

# Aliases de metriques : certaines plateformes utilisent des noms differents
# pour un concept equivalent (ex: TikTok "plays" ~ "views", Twitter "retweets" ~ "shares").
VIEW_ALIASES = ["views", "plays", "videoViews", "impressions"]
LIKE_ALIASES = ["likes", "reactions"]
COMMENT_ALIASES = ["comments"]
SHARE_ALIASES = ["shares", "retweets"]
POSTS_ROOT_ALIASES = ["posts", "data", "results", "items"]


def _first_available(d, keys, default=0):
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return default


def _aggregate_platforms_metrics(platforms_dict, preferred_platform=None):
    """
    La reponse reelle de Zernio peut structurer les metriques par
    plateforme (ex: {"tiktok": {...}, "youtube": {...}}), pas dans un
    champ 'analytics' plat. On agrege ici, avec la possibilite de
    prioriser une plateforme precise (utile si tu publies surtout sur
    TikTok/YouTube Shorts et veux ignorer le bruit d'autres canaux).
    """
    if not isinstance(platforms_dict, dict) or not platforms_dict:
        return {"views": 0, "likes": 0, "comments": 0, "shares": 0}

    if preferred_platform and preferred_platform in platforms_dict:
        sources = [platforms_dict[preferred_platform]]
    else:
        sources = list(platforms_dict.values())

    totals = {"views": 0.0, "likes": 0.0, "comments": 0.0, "shares": 0.0}
    for platform_metrics in sources:
        if not isinstance(platform_metrics, dict):
            continue
        totals["views"] += _first_available(platform_metrics, VIEW_ALIASES)
        totals["likes"] += _first_available(platform_metrics, LIKE_ALIASES)
        totals["comments"] += _first_available(platform_metrics, COMMENT_ALIASES)
        totals["shares"] += _first_available(platform_metrics, SHARE_ALIASES)

    return {k: int(v) for k, v in totals.items()}


def _extract_metrics_from_post(post):
    """
    Gere les deux formats possibles renvoyes par l'API Zernio :
    1) post["analytics"] = {"views": .., "likes": .., "comments": ..} (format plat)
    2) post["platforms"] = {"tiktok": {...}, "youtube": {...}} (format par plateforme)
    On essaie d'abord le format plat (retro-compatibilite), puis on
    bascule sur l'agregation par plateforme si le premier ne renvoie rien.
    """
    flat_analytics = post.get("analytics")
    if isinstance(flat_analytics, dict) and any(
        k in flat_analytics for k in VIEW_ALIASES + LIKE_ALIASES + COMMENT_ALIASES
    ):
        return {
            "views": int(_first_available(flat_analytics, VIEW_ALIASES)),
            "likes": int(_first_available(flat_analytics, LIKE_ALIASES)),
            "comments": int(_first_available(flat_analytics, COMMENT_ALIASES)),
        }

    platforms_dict = post.get("platforms")
    preferred_platform = os.getenv("ZERNIO_PREFERRED_PLATFORM", "").strip().lower() or None
    aggregated = _aggregate_platforms_metrics(platforms_dict, preferred_platform=preferred_platform)
    return {
        "views": aggregated["views"],
        "likes": aggregated["likes"],
        "comments": aggregated["comments"],
    }


def _extract_posts_list(data):
    """
    CORRECTIF : essaie plusieurs cles racines possibles avant d'abandonner,
    car le schema exact de reponse n'est pas garanti par la doc publique
    Zernio (elle ne documente que les query params, pas le corps de reponse).
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in POSTS_ROOT_ALIASES:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def get_latest_videos_stats():
    api_key = os.getenv("ZERNIO_API_KEY")
    if not api_key:
        print("⚠️ ZERNIO_API_KEY introuvable dans le fichier .env")
        return None

    base_url = "https://zernio.com/api/v1"
    url = f"{base_url}/analytics"

    # CORRECTIF : filtre platform/accountId injecte directement cote API
    # plutot qu'apres coup -- evite que sortBy=engagement melange des
    # plateformes non comparables (TikTok vs YouTube) dans le top 5.
    # Definis ZERNIO_PREFERRED_PLATFORM=youtube (ou tiktok) et/ou
    # ZERNIO_ACCOUNT_ID=<id_du_compte> dans ton .env selon ton besoin.
    preferred_platform = os.getenv("ZERNIO_PREFERRED_PLATFORM", "").strip().lower() or None
    preferred_account_id = os.getenv("ZERNIO_ACCOUNT_ID", "").strip() or None

    params = {"sortBy": "engagement", "limit": 5}
    if preferred_platform:
        params["platform"] = preferred_platform
    if preferred_account_id:
        params["accountId"] = preferred_account_id

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # CORRECTIF : timeout explicite pour eviter tout blocage indefini
        # du pipeline (critique en CI/CD sur GitHub Actions).
        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)

        if response.status_code == 403:
            print("❌ Zernio 403 : verifie que l'add-on Analytics est bien active sur ton plan.")
            return None
        if response.status_code == 429:
            print("❌ Zernio 429 : trop de requetes, reessaie plus tard.")
            return None

        response.raise_for_status()
        data = response.json()

        posts = _extract_posts_list(data)
        if not posts:
            available_keys = list(data.keys()) if isinstance(data, dict) else type(data)
            print("⚠️ Aucune statistique trouvée sur Zernio (ou aucun post publié). "
                  f"Cles disponibles dans la reponse : {available_keys}")
            return None

        recent_stats = []
        for post in posts:
            if not isinstance(post, dict):
                continue
            metrics = _extract_metrics_from_post(post)
            recent_stats.append({
                "title": post.get("content", "Contenu inconnu"),
                "views": metrics["views"],
                "likes": metrics["likes"],
                "comments": metrics["comments"],
            })

        if not recent_stats:
            print("⚠️ Liste de posts recuperee mais aucune metrique exploitable.")
            return None

        # CORRECTIF : si tout est a zero, on ne renvoie plus une liste
        # trompeuse -- on retourne None pour eviter de polluer le prompt
        # de ContentBrain avec un faux signal "performances nulles".
        if all(s["views"] == 0 and s["likes"] == 0 for s in recent_stats):
            print("⚠️ Toutes les stats recuperees sont a 0 — verifie le format de reponse "
                  "de l'API Zernio (structure 'platforms' vs 'analytics'). "
                  "Aucune donnee fiable, retour de None.")
            return None

        platform_suffix = f", plateforme={preferred_platform}" if preferred_platform else ""
        print(f"📊 Stats Zernio récupérées avec succès ({len(recent_stats)} vidéos analysées{platform_suffix}).")
        return recent_stats

    except requests.exceptions.Timeout:
        print(f"❌ Timeout ({REQUEST_TIMEOUT}s) lors de l'appel a l'API Zernio.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion à l'API Zernio : {e}")
        return None
    except Exception as e:
        print(f"❌ Erreur inattendue lors du traitement des données Zernio : {e}")
        return None
