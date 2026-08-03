import os
import subprocess
import tempfile
import requests
from datetime import datetime
from constants import API_URL, DIRECT_URL


def get_latest_video_url():
    """
    Interroge l'API Hugging Face pour trouver la TOUTE DERNIÈRE vidéo générée.
    Vérifie qu'elle a bien été générée aujourd'hui pour éviter de recycler du vieux contenu.
    """
    response = requests.get(API_URL, timeout=30)

    if response.status_code != 200:
        raise Exception(f"❌ Erreur de lecture sur HF : {response.status_code}")

    files = response.json()
    videos = [f['path'] for f in files if f['path'].endswith('.mp4')]

    if not videos:
        raise Exception("❌ Aucune vidéo trouvée sur Hugging Face.")

    videos.sort()
    target_video_path = videos[-1]
    filename = target_video_path.split("/")[-1]

    video_date = filename[:8]
    today_date = datetime.utcnow().strftime("%Y%m%d")

    if video_date != today_date:
        raise Exception(
            f"🛑 Alerte Sécurité : La dernière vidéo date du {video_date}, mais nous sommes le {today_date}. "
            f"Le générateur a probablement échoué. Annulation de la publication."
        )

    print(f"🎯 Vidéo du jour sélectionnée : {filename}")

    direct_url = f"{DIRECT_URL}{target_video_path}"
    return direct_url, target_video_path


def check_audio_loudness(video_url):
    """
    Télécharge temporairement la vidéo et vérifie le niveau sonore
    avant publication via ffmpeg loudnorm. Le fichier temporaire est
    systématiquement supprimé (succès ou échec).
    """
    tmp_path = None
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

    except Exception as e:
        print(f"⚠️ Analyse loudness impossible (non bloquant) : {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception as e:
                print(f"⚠️ Impossible de supprimer le fichier temporaire {tmp_path} : {e}")


def publish_to_tiktok():
    video_url, file_path = get_latest_video_url()
    print(f"🎥 Lien direct de la vidéo : {video_url}")

    check_audio_loudness(video_url)

    api_key = os.environ.get("ZERNIO_API_KEY")
    tiktok_account_id = os.environ.get("TIKTOK_ACCOUNT_ID")
    youtube_account_id = os.environ.get("YOUTUBE_ACCOUNT_ID")

    if not api_key or not tiktok_account_id or not youtube_account_id:
        raise ValueError("❌ Clés d'API ou IDs de compte manquants dans les variables d'environnement.")

    raw_filename = file_path.split("/")[-1]
    clean_title = raw_filename.replace(".mp4", "").replace("_", " ")[16:]

    # =========================================================================
    # --- RÉCUPÉRATION DE LA LÉGENDE IA ---
    # =========================================================================
    caption_path = os.path.join(os.getcwd(), "caption.txt")
    
    if os.path.exists(caption_path):
        try:
            with open(caption_path, "r", encoding="utf-8") as f:
                caption = f.read().strip()
            print("✅ Légende IA récupérée avec succès depuis caption.txt !")
        except Exception as e:
            print(f"⚠️ Erreur de lecture de caption.txt ({e}). Utilisation de la légende de secours.")
            caption = f"{clean_title} 🧠✨ #IA #MinuteMystère #Decouverte #PourToi"
    else:
        print("⚠️ Fichier caption.txt introuvable. Utilisation de la légende de secours.")
        caption = f"{clean_title} 🧠✨ #IA #MinuteMystère #Decouverte #PourToi"
        
    print(f"📝 Légende finale utilisée pour la publication :\n{caption}")
    # =========================================================================

    url = "https://zernio.com/api/v1/posts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    platforms_list = [
        {"platform": "tiktok", "accountId": tiktok_account_id},
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
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.exceptions.Timeout:
        raise Exception("❌ La requête vers Zernio a expiré (timeout).")

    if response.status_code in [200, 201]:
        print("✅ Succès ! La vidéo a été envoyée pour publication.")
    elif response.status_code == 409:
        print("⚠️ Zernio a bloqué la publication : Cette vidéo a déjà été publiée (Doublon géré avec succès).")
    else:
        raise Exception(f"❌ Erreur lors de la publication ({response.status_code}) : {response.text}")


if __name__ == "__main__":
    publish_to_tiktok()
