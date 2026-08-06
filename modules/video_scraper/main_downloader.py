import requests
from .stock_apis import get_background_video_cascade


def download_video_to_local(url, destination_path):
    """Télécharge le fichier mp4 direct depuis l'URL de l'API."""
    print(f"📥 Téléchargement en cours depuis la source officielle...")
    try:
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()
        
        with open(destination_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print("✅ Vidéo sauvegardée avec succès !")
        return True
    except Exception as e:
        print(f"❌ Erreur lors du téléchargement : {e}")
        return False


def fetch_background_video(query, destination_path):
    """
    Tente de récupérer une vidéo via les API (Pixabay/Pexels).
    Si ça échoue, on passe directement aux images IA.
    """
    # 1. On tente via les API officielles en cascade
    api_result = get_background_video_cascade(query)
    
    if api_result and api_result.get("url"):
        success = download_video_to_local(api_result["url"], destination_path)
        if success:
            return True
            
    # 2. Tout a échoué (les API n'ont rien trouvé ou sont inaccessibles)
    # Fini yt-dlp, on passe directement à la génération d'images (ton fallback Pollinations)
    print("❌ Impossible de récupérer un fond vidéo via les API. Passage au fallback images IA.")
    return False