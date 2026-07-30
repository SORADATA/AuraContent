import os
import requests
from datetime import datetime
from constants import API_URL, DIRECT_URL


def get_latest_video_url():
    """
    Interroge l'API Hugging Face pour trouver la TOUTE DERNIÈRE vidéo générée.
    Vérifie qu'elle a bien été générée aujourd'hui pour éviter de recycler du vieux contenu.
    """
    api_url = API_URL
    response = requests.get(api_url)

    if response.status_code != 200:
        raise Exception(f"❌ Erreur de lecture sur HF : {response.status_code}")

    files = response.json()

    # 1. Filtrer uniquement les fichiers MP4
    videos = [f['path'] for f in files if f['path'].endswith('.mp4')]
    
    if not videos:
        raise Exception("❌ Aucune vidéo trouvée sur Hugging Face.")

    # 2. Trier chronologiquement et prendre la dernière
    videos.sort()
    target_video_path = videos[-1]
    filename = target_video_path.split("/")[-1]

    # --- 🛡️ NOUVELLE SÉCURITÉ : VÉRIFICATION DE LA DATE ---
    # Extrait "YYYYMMDD" du nom du fichier (les 8 premiers caractères)
    video_date = filename[:8] 
    # Récupère la date du jour au même format
    today_date = datetime.utcnow().strftime("%Y%m%d")

    if video_date != today_date:
        raise Exception(f"🛑 Alerte Sécurité : La dernière vidéo date du {video_date}, mais nous sommes le {today_date}. Le générateur a probablement échoué. Annulation de la publication.")
    # ------------------------------------------------------

    print(f"🎯 Vidéo du jour sélectionnée : {filename}")

    direct_url = f"{DIRECT_URL}{target_video_path}"
    return direct_url, target_video_path


def publish_to_tiktok():
    video_url, file_path = get_latest_video_url()
    print(f"🎥 Lien direct de la vidéo : {video_url}")

    api_key = os.environ.get("ZERNIO_API_KEY")
    tiktok_account_id = os.environ.get("TIKTOK_ACCOUNT_ID")
    youtube_account_id = os.environ.get("YOUTUBE_ACCOUNT_ID")

    if not api_key or not tiktok_account_id or not youtube_account_id:
        raise ValueError("❌ Clés d'API ou IDs de compte manquants dans les variables d'environnement.")

    # Extraction du titre propre à partir du nom du fichier
    raw_filename = file_path.split("/")[-1]
    clean_title = raw_filename.replace(".mp4", "").replace("_", " ")[16:]
    
    caption = f"{clean_title} 🧠✨ #IA #MinuteMystère #Decouverte"
    print(f"📝 Légende générée : {caption}")

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
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in [200, 201]:
        print("✅ Succès ! La vidéo a été envoyée pour publication.")
    elif response.status_code == 409:
        print("⚠️ Zernio a bloqué la publication : Cette vidéo a déjà été publiée (Doublon géré avec succès).")
    else:
        raise Exception(f"❌ Erreur lors de la publication ({response.status_code}) : {response.text}")


if __name__ == "__main__":
    publish_to_tiktok()
