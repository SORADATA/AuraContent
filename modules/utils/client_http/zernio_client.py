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
    CORRECTIF : la reponse reelle de Zernio structure les metriques par
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


def get_latest_videos_stats():
    api_key = os.getenv("ZERNIO_API_KEY")
    if not api_key:
        print("⚠️ ZERNIO_API_KEY introuvable dans le fichier .env")
        return None

    base_url = "https://zernio.com/api/v1"
    url = f"{base_url}/analytics"
    params = {"sortBy": "engagement", "limit": 5}
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

        posts = data.get("posts", [])
        if not posts:
            print("⚠️ Aucune statistique trouvée sur Zernio (ou aucun post publié).")
            return None

        recent_stats = []
        for post in posts:
            metrics = _extract_metrics_from_post(post)
            recent_stats.append({
                "title": post.get("content", "Contenu inconnu"),
                "views": metrics["views"],
                "likes": metrics["likes"],
                "comments": metrics["comments"],
            })

       
        # zero -> signe quasi certain d'un souci de parsing de reponse,
        # plutot que de laisser passer silencieusement des donnees vides
        # dans le feedback loop (ContentBrain / hook_tracker).
        if all(s["views"] == 0 and s["likes"] == 0 for s in recent_stats):
            print("⚠️ Toutes les stats recuperees sont a 0 — verifie le format de reponse "
                  "de l'API Zernio (structure 'platforms' vs 'analytics').")

        print(f"📊 Stats Zernio récupérées avec succès ({len(recent_stats)} vidéos analysées).")
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
