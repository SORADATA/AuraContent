import os
import requests
from dotenv import load_dotenv

# Charge les variables d'environnement (dont ZERNIO_API_KEY)
load_dotenv()


def get_latest_videos_stats():
    """
    Récupère les statistiques des 5 dernières vidéos (ou les plus engageantes)
    via l'API Zernio pour fournir un contexte de performance au LLM.
    """
    api_key = os.getenv("ZERNIO_API_KEY")
    if not api_key:
        print("⚠️ ZERNIO_API_KEY introuvable dans le fichier .env (elle doit commencer par sk_)")
        return None

    # L'URL de base définie par la documentation Zernio
    base_url = "https://zernio.com/api/v1"
    
    # Endpoint Analytics avec limit=5 pour récupérer un historique représentatif
    url = f"{base_url}/analytics?sortBy=engagement&limit=5"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # Appel à l'API Zernio
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Lève une exception si l'API renvoie une erreur (ex: 401 Unauthorized)
        data = response.json()
        
        # Extraction des données en fonction de la structure standard
        posts = data.get("data", [])
        
        if not posts:
            print("⚠️ Aucune statistique trouvée sur Zernio (ou aucun post publié).")
            return None
            
        # Création de la liste des statistiques récentes
        recent_stats = []
        for post in posts:
            recent_stats.append({
                "title": post.get("title", "Titre inconnu"),
                "views": post.get("views", 0),
                "likes": post.get("likes", 0),
                "comments": post.get("comments", 0)
            })
            
        print(f"📊 Stats Zernio récupérées avec succès ({len(recent_stats)} vidéos analysées).")
        return recent_stats

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion à l'API Zernio : {e}")
        return None
    except Exception as e:
        print(f"❌ Erreur inattendue lors du traitement des données Zernio : {e}")
        return None

# ==========================================
# Bloc de test (s'exécute uniquement si on lance ce fichier directement)
# ==========================================
if __name__ == "__main__":
    print("Test de connexion à l'API Zernio...")
    stats = get_latest_videos_stats()
    
    if stats:
        print("\n--- Historique des performances récupéré ---")
        for i, stat in enumerate(stats, 1):
            print(f"{i}. \"{stat['title']}\" | Vues: {stat['views']} | Likes: {stat['likes']} | Coms: {stat['comments']}")
    else:
        print("\n❌ Impossible de récupérer les statistiques. Vérifie ta clé API.")