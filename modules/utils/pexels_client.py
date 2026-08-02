import os
import requests
import random


def get_pexels_video(query, output_path, is_fallback=False):
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        print("❌ Erreur : PEXELS_API_KEY introuvable dans les variables d'environnement.")
        return None

    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=5"

    print(f"🔍 Recherche Pexels pour : '{query}'...")

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException as e:
        print(f"❌ Erreur réseau Pexels : {e}")
        return None

    if response.status_code != 200:
        print(f"❌ Erreur API Pexels ({response.status_code}): {response.text}")
        return None

    data = response.json()

    if not data.get("videos"):
        if not is_fallback:
            fallback_keywords = [
                "finance chart",
                "business office laptop",
                "money counting",
                "stock market smartphone",
                "saving money coin"
            ]
            fallback_query = random.choice(fallback_keywords)
            print(f"⚠️ Aucune vidéo trouvée pour : '{query}'.")
            print(f"🔄 Déclenchement de la roue de secours avec : '{fallback_query}'...")
            return get_pexels_video(fallback_query, output_path, is_fallback=True)
        else:
            print("❌ Échec critique : aucune vidéo trouvée même avec la roue de secours.")
            return None

    video_data = data["videos"][0]
    video_files = video_data.get("video_files", [])

    if not video_files:
        print("❌ Aucun fichier vidéo disponible dans le résultat Pexels.")
        return None

    video_files.sort(key=lambda x: x.get("height", 0), reverse=True)

    best_file = None
    for vf in video_files:
        if vf.get("file_type") == "video/mp4" or vf.get("link", "").endswith(".mp4"):
            best_file = vf
            break

    if best_file is None:
        best_file = video_files[0]

    best_video_url = best_file["link"]
    print(
        f"⬇️ Téléchargement de la vidéo Pexels ({best_file.get('quality')} - "
        f"{best_file.get('width')}x{best_file.get('height')})..."
    )

    try:
        video_response = requests.get(best_video_url, stream=True, timeout=60)
        if video_response.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"✅ Vidéo sauvegardée sous : {output_path}")
            return output_path
        else:
            print(f"❌ Échec du téléchargement de la vidéo : {video_response.status_code}")
            return None
    except requests.RequestException as e:
        print(f"❌ Erreur téléchargement vidéo : {e}")
        return None


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_query = "astronaut trading crypto on mars with purple aliens"
    get_pexels_video(test_query, "test_finance.mp4")
