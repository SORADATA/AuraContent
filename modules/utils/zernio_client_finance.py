import os
import requests
from dotenv import load_dotenv

load_dotenv()


def get_latest_videos_stats():
    api_key = os.getenv("ZERNIO_API_KEYS_FINANCE")
    if not api_key:
        print("⚠️ ZERNIO_API_KEYS_FINANCE introuvable dans le fichier .env")
        return None
        

    base_url = "https://zernio.com/api/v1"
    url = f"{base_url}/analytics?sortBy=engagement&limit=5"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        posts = data.get("posts", [])
        if not posts:
            print("⚠️ Aucune statistique trouvée sur Zernio (ou aucun post publié).")
            return None

        recent_stats = []
        for post in posts:
            analytics = post.get("analytics", {})
            recent_stats.append({
                "title": post.get("content", "Contenu inconnu"),
                "views": analytics.get("views", 0),
                "likes": analytics.get("likes", 0),
                "comments": analytics.get("comments", 0)
            })

        print(f"📊 Stats Zernio récupérées avec succès ({len(recent_stats)} vidéos analysées).")
        return recent_stats

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion à l'API Zernio : {e}")
        return None
    except Exception as e:
        print(f"❌ Erreur inattendue lors du traitement des données Zernio : {e}")
        return None
