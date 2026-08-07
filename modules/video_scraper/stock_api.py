import os
import requests
import urllib.parse

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

def get_pixabay_vertical_video(query):
    """Cherche une vidéo sur Pixabay et filtre pour garder un format vertical (H > L)."""
    if not PIXABAY_API_KEY:
        print("❌ Clé API Pixabay manquante.")
        return None

    encoded_query = urllib.parse.quote(query)
    pixabay_url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={encoded_query}&video_type=film"
    
    try:
        response = requests.get(pixabay_url, timeout=10)
        limit_remaining = response.headers.get('X-RateLimit-Remaining')
        if limit_remaining:
            print(f"📊 Pixabay : Il reste {limit_remaining} requêtes pour cette minute.")
            
        if response.status_code == 200:
            data = response.json()
            if data.get("totalHits", 0) > 0:
                for hit in data["hits"]:
                    video_stream = hit["videos"].get("medium")
                    if not video_stream:
                        continue
                        
                    width = video_stream["width"]
                    height = video_stream["height"]
                    
                    if height > width:
                        print(f"✅ Vidéo verticale trouvée sur Pixabay ({width}x{height}) !")
                        return {"source": "pixabay", "url": video_stream["url"]}
                
                print("⚠️ Pixabay : aucune vidéo au format vertical trouvée.")
            else:
                print("⚠️ Aucun résultat sur Pixabay.")
        else:
            print(f"❌ Erreur Pixabay HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Exception Pixabay : {e}")

    return None

def get_pexels_vertical_video(query):
    """Cherche une vidéo au format vertical sur Pexels (utilise orientation=portrait)."""
    if not PEXELS_API_KEY:
        print("❌ Clé API Pexels manquante.")
        return None

    encoded_query = urllib.parse.quote(query)
    pexels_url = f"https://api.pexels.com/videos/search?query={encoded_query}&orientation=portrait&per_page=5"
    headers = {"Authorization": PEXELS_API_KEY}
    
    try:
        response = requests.get(pexels_url, headers=headers, timeout=10)
        limit_remaining = response.headers.get('X-Ratelimit-Remaining')
        if limit_remaining:
            print(f"📊 Pexels : Il reste {limit_remaining} requêtes pour cette heure.")
            
        if response.status_code == 200:
            data = response.json()
            if data.get("total_results", 0) > 0:
                for video in data["videos"]:
                    video_files = video.get("video_files", [])
                    selected_file = None
                    
                    for file in video_files:
                        if file.get("file_type") == "video/mp4":
                            if file.get("quality") == "hd":
                                selected_file = file
                                break
                            elif not selected_file:
                                selected_file = file
                                
                    if selected_file:
                        width = selected_file.get("width", "N/A")
                        height = selected_file.get("height", "N/A")
                        print(f"✅ Vidéo verticale trouvée sur Pexels ({width}x{height}) !")
                        return {"source": "pexels", "url": selected_file["link"]}
                
                print("⚠️ Pexels : aucun fichier mp4 valide extrait.")
            else:
                print("⚠️ Aucun résultat sur Pexels.")
        else:
            print(f"❌ Erreur Pexels HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Exception Pexels : {e}")

    return None

def get_background_video_cascade(query):
    """Orchestre la recherche : Pixabay d'abord, Pexels ensuite."""
    print(f"📡 Recherche du fond vidéo pour : '{query}'...")
    
    result = get_pixabay_vertical_video(query)
    if result:
        return result
        
    print("🔄 Basculement vers Pexels...")
    result = get_pexels_vertical_video(query)
    if result:
        return result
        
    print("⚠️ Bases de données stock épuisées.")
    return None