import os
import requests
from constants import API_URL, DIRECT_URL


def get_latest_video_url():
    """
    Interroge l'api hugging face pour trouver la dernière vidéo
    """
    api_url = API_URL
    response = requests.get(api_url)
    if response.status_code != 200:
        raise Exception(f"Do not read folder on HF : {response.status_code}")
    files = response.json()
    # Filter to take only .mp4 file
    videos = [f['path'] for f in files if f['path'].endswith('.mp4')]
    videos.sort()
    # Take recent video
    latest_video_path = videos[-1]
    direct_url = f"{DIRECT_URL}{latest_video_path}" 
    return direct_url, latest_video_path


def publish_to_tiktok():
    # Recup recent video
    video_url, file_path = get_latest_video_url()
    print(f"🎥 Daily video found : {video_url}")

    api_key = os.environ.get("ZERNIO_API_KEY")
    # ⚠️ CORRECTION 3 : Correction de la faute de frappe (ACCOUNT avec un T)
    account_id = os.environ.get("TIKTOK_ACCOUNT_ID") 

    if not api_key or not account_id:
        raise ValueError("Zernio or tiktok api keys not found")

    # Cleaning filename output
    raw_filename = file_path.split("/")[-1]
    clean_title = raw_filename.replace(".mp4", "").replace("_", " ")[16:]
    caption = f"{clean_title} 🧠✨ #IA #MinuteMystère #Decouverte"
    print(f"📝 Légende générée : {caption}")

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
    if response.status_code == 200:
        print("✅ Succès ! La vidéo a été publiée sur le compte TikTok @minute_mystereko.")
    else:
        raise Exception(f"❌ Errors during publishing {response.status_code} : {response.text}")


if __name__ == "__main__":
    publish_to_tiktok()