import argparse
import os
import subprocess
import tempfile
import requests
from datetime import datetime

CHANNEL_REPOS = {
    "minute_mystere": {
        "hf_api_url": "https://huggingface.co/api/datasets/soradata/minute-mystere-videos/tree/main/videos",
        "direct_url": "https://huggingface.co/datasets/soradata/minute-mystere-videos/raw/main/",
        "tiktok_env": "TIKTOK_ACCOUNT_ID_MYSTERE",
        "youtube_env": "YOUTUBE_ACCOUNT_ID_MYSTERE",
        "hashtag": "#MinuteMystere"
    },
    "finance": {
        "hf_api_url": "https://huggingface.co/api/datasets/soradata/finance-videos/tree/main/videos",
        "direct_url": "https://huggingface.co/datasets/soradata/finance-videos/raw/main/",
        "tiktok_env": "TIKTOK_ACCOUNT_ID_FINANCE",
        "youtube_env": "YOUTUBE_ACCOUNT_ID_FINANCE",
        "hashtag": "#Finance #Bourse #Argent"
    }
}


def get_latest_video_url(channel_name: str):
    if channel_name not in CHANNEL_REPOS:
        raise Exception(f"❌ Chaîne '{channel_name}' inconnue pour la publication.")

    config = CHANNEL_REPOS[channel_name]
    response = requests.get(config["hf_api_url"])

    if response.status_code != 200:
        raise Exception(f"❌ Erreur de lecture sur le HF de {channel_name} : {response.status_code}")

    files = response.json()
    videos = [f['path'] for f in files if f['path'].endswith('.mp4')]

    today_str = datetime.utcnow().strftime("%Y%m%d")
    todays_videos = [v for v in videos if today_str in v]
    todays_videos.sort()

    if not todays_videos:
        raise Exception(f"❌ Aucune vidéo générée aujourd'hui trouvée pour {channel_name}.")

    current_hour = datetime.utcnow().hour

    if len(todays_videos) >= 2 and current_hour >= 15:
        target_video_path = todays_videos[1]
        print(f"🌙 Evening Execution ({channel_name}) : publication de la 2ème vidéo.")
    else:
        target_video_path = todays_videos[0]
        print(f"☀️ Middle Execution ({channel_name}) : publication de la 1ère vidéo.")

    direct_url = f"{config['direct_url']}{target_video_path}"
    return direct_url, target_video_path, config


def check_audio_loudness(video_url: str):
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            print("🔊 Téléchargement temporaire pour analyse loudness...")
            with requests.get(video_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)

        result = subprocess.run(
            ["ffmpeg", "-i", tmp_path, "-af", "loudnorm=print_format=summary", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60
        )

        report = result.stderr
        with open("loudness_report.txt", "w", encoding="utf-8") as f:
            f.write(report)

        for line in report.splitlines():
            if any(key in line for key in ["Input Integrated", "Input LRA", "Output Integrated"]):
                print(f"   {line.strip()}")

        os.remove(tmp_path)

    except Exception as e:
        print(f"⚠️ Analyse loudness impossible (non bloquant) : {e}")


def publish_video(channel_name: str):
    video_url, file_path, config = get_latest_video_url(channel_name)
    print(f"🎥 Lien direct de la vidéo : {video_url}")

    check_audio_loudness(video_url)

    api_key = os.environ.get("ZERNIO_API_KEY")
    tiktok_account_id = os.environ.get(config["tiktok_env"])
    youtube_account_id = os.environ.get(config["youtube_env"])

    if not api_key or not tiktok_account_id or not youtube_account_id:
        raise ValueError(f"❌ Identifiants API ou comptes manquants pour la chaîne {channel_name}.")

    raw_filename = file_path.split("/")[-1]
    clean_title = raw_filename.replace(".mp4", "").replace("_", " ")[16:]

    caption = f"{clean_title} 🧠✨ #IA {config['hashtag']} #Decouverte"
    print(f"📝 Légende générée : {caption}")

    url = "https://zernio.com/api/v1/posts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "content": caption,
        "mediaItems": [{"type": "video", "url": video_url}],
        "platforms": [
            {"platform": "tiktok", "accountId": tiktok_account_id},
            {"platform": "youtube", "accountId": youtube_account_id}
        ],
        "youtubeSettings": {
            "title": clean_title,
            "privacy_status": "PUBLIC"
        },
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

    print(f"🚀 Envoi de la requête à Zernio pour {channel_name}...")
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in [200, 201]:
        print(f"✅ Succès ! La vidéo de {channel_name} a été publiée.")
    elif response.status_code == 409:
        print("⚠️ Zernio a bloqué la publication : Cette vidéo a déjà été publiée récemment (Doublon).")
    else:
        raise Exception(f"❌ Erreur lors de la publication ({response.status_code}) : {response.text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Channel Publisher with Zernio")
    parser.add_argument("--channel", type=str, required=True, help="Nom de la chaîne (ex: minute_mystere, finance)")
    args = parser.parse_args()

    publish_video(args.channel)