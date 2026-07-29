import os
import requests


def publish_to_tiktok():
    # Retour au chemin classique assets/mimolune/
    video_path = os.path.join("assets", "mimolune", "final", "final_short.mp4")
    
    if not os.path.exists(video_path):
        print("❌ Aucune vidéo trouvée pour la publication.")
        return

    api_key = os.getenv("ZERNIO_API_KEY")
    account_id = os.getenv("TIKTOK_ACCOUNT_ID_MIMOLUNE")
    
    print(f"📡 Envoi de la vidéo à Zernio pour le compte TikTok Mimolune...")
    
    url = "https://api.zernio.com/v1/publish"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"video": open(video_path, "rb")}
    data = {"account_id": account_id, "description": "Nouvelle comptine Mimolune ! 🌙✨ #Enfants #Comptine #Mimolune"}
    
    response = requests.post(url, headers=headers, files=files, data=data)
    
    if response.status_code == 200:
        print("✅ Vidéo publiée avec succès sur TikTok !")
    elif response.status_code == 409:
        print("⚠️ Erreur 409 : Doublon détecté (déjà publié dans les 24h).")
    else:
        print(f"❌ Échec de la publication : {response.text}")

if __name__ == "__main__":
    publish_to_tiktok()