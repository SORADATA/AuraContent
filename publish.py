import os
import requests
from datetime import datetime
from constants import API_URL, DIRECT_URL


def get_latest_video_url():
    """
    Interroge l'api hugging face pour trouver la vidéo à publier selon l'heure
    """
    api_url = API_URL
    response = requests.get(api_url)

    if response.status_code != 200:
        raise Exception(f" Do not read folder on HF : {response.status_code}")

    files = response.json()

    # Récupère tous les fichiers .mp4 et les trie par nom (le nom commence par YYYYMMDD_HHMMSS, 
    # donc un tri alphabétique classe parfaitement du plus ancien au plus récent)
    videos = [f['path'] for f in files if f['path'].endswith('.mp4')]
    videos.sort()

    if not videos:
        raise Exception(" No video found on HF.")

    # On prend les deux dernières vidéos les plus récentes du dépôt (ou la dernière si y en a qu'une)
    recent_videos = videos[-2:] if len(videos) >= 2 else videos

    # Current hour (en UTC) -> 7h UTC = 9h à Paris (en été)
    current_hour = datetime.utcnow().hour

    # Selection video :
    # Si on est le matin (avant 15h UTC / 17h Paris), on prend la plus ancienne des deux du jour (la 1ère)
    # Si on est le soir, on prend la plus récente (la 2ème)
    if current_hour >= 15 and len(recent_videos) >= 2:
        target_video_path = recent_videos[1]
        print("🌙 Soir : publication de la 2ème vidéo du jour.")
    else:
        target_video_path = recent_videos[0]
        print("☀️ Matin : publication de la 1ère vidéo du jour.")

    direct_url = f"{DIRECT_URL}{target_video_path}"
    return direct_url, target_video_path


def publish_to_tiktok():
    # Recup recent video
    video_url, file_path = get_latest_video_url()
    print(f"🎥 Daily video found : {video_url}")

    api_key = os.environ.get("ZERNIO_API_KEY")
    tiktok_account_id = os.environ.get("TIKTOK_ACCOUNT_ID") 
    youtube_account_id = os.environ.get("YOUTUBE_ACCOUNT_ID") 

    if not api_key or not tiktok_account_id:
        raise ValueError(" Zernio or tiktok api keys not found")

    # Cleaning filename output
    raw_filename = file_path.split("/")[-1]
    clean_title = raw_filename.replace(".mp4", "").replace("_", " ")[16:]
    caption = f"{clean_title} 🧠✨ #IA #MinuteMystère #Decouverte"
    print(f"📝 Légende generated : {caption}")

    # Sending to zernio api for publish on platforms
    url = "https://zernio.com/api/v1/posts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Au lieu d'inclure TikTok, on ne met que YouTube pour ce test
    platforms_list = [
        {"platform": "youtube", "accountId": youtube_account_id}
    ]
    payload = {
        "content": caption,
        "mediaItems": [{"type": "video", "url": video_url}],
        "platforms": platforms_list,
        "youtubeSettings": {
            "title": clean_title,
            "privacy_status": "PUBLIC"
        },
    
        "publishNow": True
    }

    print("🚀 Envoi de la requête à Zernio...")
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in [200, 201]:
        print("✅ Succès ! La vidéo a été publiée sur TikTok et YouTube.")
    elif response.status_code == 409:
        print("⚠️ Zernio a bloqué la publication : Cette vidéo a déjà été publiée récemment (Doublon).")
    else:
        raise Exception(f"❌ Errors during publishing {response.status_code} : {response.text}")


if __name__ == "__main__":
    publish_to_tiktok()
