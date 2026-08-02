import os
import requests
import random


def get_pexels_video(query, output_path, is_fallback=False):
    """
    Recherche et télécharge une vidéo verticale sur Pexels.
    Intègre un système de roue de secours si aucun résultat n'est trouvé.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        print("❌ Erreur : PEXELS_API_KEY introuvable dans les variables d'environnement.")
        return None

    headers = {
        "Authorization": api_key
    }
    
    # Recherche de vidéos verticales (portrait)
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=5"
    
    print(f"🔍 Recherche Pexels pour : '{query}'...")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Erreur API Pexels ({response.status_code}): {response.text}")
        return None
        
    data = response.json()
    
    # --- SYSTÈME DE FALLBACK (ROUE DE SECOURS) ---
    if not data.get("videos") or len(data["videos"]) == 0:
        if not is_fallback:
            # Liste de mots-clés de secours qui marchent à 100% pour la finance
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
            
            # On relance la fonction avec le mot-clé de secours
            return get_pexels_video(fallback_query, output_path, is_fallback=True)
        else:
            print(f"❌ Échec critique : Aucune vidéo trouvée même avec la roue de secours.")
            return None
    # ---------------------------------------------

    # On prend la première vidéo des résultats
    video_data = data["videos"][0]
    video_files = video_data.get("video_files", [])
    
    if not video_files:
        return None
        
    # Trier les fichiers par résolution (hauteur décroissante) pour avoir la meilleure qualité HD
    video_files.sort(key=lambda x: x.get('height', 0), reverse=True)
    best_video_url = video_files[0]["link"]
    
    print(f"⬇️ Téléchargement de la vidéo Pexels ({video_files[0].get('quality')} - {video_files[0].get('width')}x{video_files[0].get('height')})...")
    
    # Téléchargement du fichier mp4
    video_response = requests.get(best_video_url, stream=True)
    if video_response.status_code == 200:
        with open(output_path, 'wb') as f:
            for chunk in video_response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✅ Vidéo sauvegardée sous : {output_path}")
        return output_path
    else:
        print(f"❌ Échec du téléchargement de la vidéo : {video_response.status_code}")
        return None

# --- Test rapide en local ---
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test avec un mot-clé volontairement absurde pour forcer le déclenchement de la roue de secours
    test_query = "astronaut trading crypto on mars with purple aliens"
    get_pexels_video(test_query, "test_finance.mp4")