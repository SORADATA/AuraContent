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

    # Filter to take only .mp4 file
    videos = [f['path'] for f in files if f['path'].endswith('.mp4')]
    videos.sort() # Trie par ordre alphabétique/chronologique (les plus récents à la fin)

    if not videos:
        raise Exception(" No video found on HF.")

    # Current day format YYYYMMDD
    today_str = datetime.utcnow().strftime("%Y%m%d")

    # Take only videos today generated
    todays_videos = [v for v in videos if today_str in v]

    # Fallback robuste : si le filtre du jour strict est vide (décalage horaire), 
    # on prend les deux dernières vidéos globales du dépôt pour ne pas bloquer
    if not todays_videos:
        print("⚠️ Aucune vidéo trouvée pour la date exacte UTC, utilisation des plus récentes du dépôt.")
        todays_videos = videos[-2:] if len(videos) >= 2 else videos

    # Current hour (en UTC)
    current_hour = datetime.utcnow().hour

    # Selection video: 1ère vidéo à midi, 2ème vidéo le soir
    if len(todays_videos) >= 2 and current_hour >= 15:
        target_video_path = todays_videos[1]
        print("🌙 Evening Exécution  : publication of 2d  daily video.")
    else:
        target_video_path = todays_videos[-1] # Toujours la plus récente disponible
        print("☀️ Midle Exécution: publication of 1st daily video.")

    direct_url = f"{DIRECT_URL}{target_video_path}"
    return direct_url, target_video_path


def publish_to_tiktok():
    # Recup recent video
    video_url, file_path = get_latest_video_url()
    print(f"🎥 Daily video found : {video_url}")

    api_key = os.environ.get("ZERNIO_API_KEY")
    account_id = os.environ.get("TIKTOK_ACCOUNT_ID") 

    if not api_key or not account_id:
        raise ValueError(" Zernio or tiktok api keys not found")

    # Cleaning filename output
    raw_filename = file_path.split("/")[-1]
    clean_title = raw_filename.replace(".mp4", "").replace("_", " ")[16:]
    caption = f"{clean_title} 🧠✨ #IA #MinuteMystère #Decouverte"
    print(f"📝 Légende generated : {caption}")

    # Sending to zernio api for publish on tiktok
    url = "https://zernio.com/api/v1/posts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "content": caption,
        "mediaItems": [{"type": "video", "url": video_url}],
        "platforms": [{"platform": "tiktok", "accountId": account_id}],
        "tiktokSettings": {
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "allow_comment": True,
            "allow_duet": False,
            "allow_stitch": False,
            "content_preview_confirmed": True,
            "express_consent_given": True,
            "video_made_with_ai": True
        },
        "publishNow": True
    }

    print("🚀 Envoi de la requête à Zernio...")
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in [200, 201]:
        print("✅ Succès ! La vidéo a été publiée sur le compte TikTok @minute_mystereko.")
    elif response.status_code == 409:
        print("⚠️ Zernio a bloqué la publication : Cette vidéo a déjà été publiée récemment (Doublon).")
    else:
        raise Exception(f"❌ Errors during publishing {response.status_code} : {response.text}")


if __name__ == "__main__":
    publish_to_tiktok()
