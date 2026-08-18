import os
import random
import requests
import urllib.parse
from modules.utils.download.utils_assets import is_used, mark_used, calculate_relevance, download_file


class VideoProvider:
    def __init__(self, history):
        self.pixabay_key = os.getenv("PIXABAY_API_KEY")
        self.pexels_key = os.getenv("PEXELS_API_KEY")
        self.history = history

        # CORRECTIF : ancien pool de secours générique et déconnecté du
        # thème ("dark ocean waves", "foggy rocky coast", "old stone
        # ruins") remplacé par un pool neutre documentaire/mystère, utilisé
        # UNIQUEMENT si aucun fallback_keywords thématique n'est fourni par
        # l'appelant (voir asset_manager.py, qui dérive désormais ce pool
        # du "mood" de la scène généré par le brain).
        self.default_fallback_pool = [
            "dark documentary atmosphere",
            "mysterious abandoned building",
            "old archive footage texture",
            "dim candlelight corridor",
        ]

    def get_pixabay(self, query, min_relevance=0.1):
        if not self.pixabay_key: return None
        url = f"https://pixabay.com/api/videos/?key={self.pixabay_key}&q={urllib.parse.quote(query)}&video_type=film&per_page=10"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                candidates = []
                for hit in r.json().get("hits", []):
                    vid_id = hit.get("id")
                    if is_used(self.history, "pixabay", vid_id): continue
                    
                    score = calculate_relevance(query, hit.get("tags", ""))
                    for size in ("large", "medium", "small", "tiny"):
                        stream = hit["videos"].get(size)
                        if stream and stream["height"] > stream["width"]:
                            candidates.append((score, vid_id, stream["url"]))
                            break
                            
                candidates.sort(key=lambda x: x[0], reverse=True)
                if candidates and candidates[0][0] >= min_relevance:
                    mark_used(self.history, "pixabay", candidates[0][1])
                    return candidates[0][2]
        except Exception as e:
            print(f"❌ Pixabay Exception: {e}")
        return None

    def get_pexels(self, query, min_relevance=0.1):
        if not self.pexels_key: return None
        url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&orientation=portrait&per_page=10"
        try:
            r = requests.get(url, headers={"Authorization": self.pexels_key}, timeout=10)
            if r.status_code == 200:
                candidates = []
                for video in r.json().get("videos", []):
                    vid_id = video.get("id")
                    if is_used(self.history, "pexels", vid_id): continue
                    
                    text_to_check = urllib.parse.unquote(video.get("url", "")).replace("-", " ")
                    score = calculate_relevance(query, text_to_check)
                    
                    mp4_files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
                    if not mp4_files: continue
                    selected = next((f for f in mp4_files if f.get("quality") == "hd"), mp4_files[0])
                    
                    candidates.append((score, vid_id, selected["link"]))
                    
                candidates.sort(key=lambda x: x[0], reverse=True)
                if candidates and candidates[0][0] >= min_relevance:
                    mark_used(self.history, "pexels", candidates[0][1])
                    return candidates[0][2]
        except Exception as e:
            print(f"❌ Pexels Exception: {e}")
        return None

    def fetch_background(self, query, output_path, is_fallback=False, fallback_keywords=None):
        """
        CORRECTIF : le pool de secours utilisé en cas d'échec de la
        recherche initiale n'est plus un pool générique fixe sans rapport
        avec le sujet ("dark ocean waves", "foggy rocky coast", "old stone
        ruins"). Il est désormais piloté par 'fallback_keywords', que
        l'appelant (AssetManager) construit à partir du 'mood' réel de la
        scène (ominous, tense, awe, etc.), pour rester dans le thème
        sombre/mystère/documentaire même quand la recherche précise
        échoue. Le pool générique interne ci-dessous ne sert plus que de
        filet de sécurité ultime si aucun mood n'a pu être déterminé.
        """
        print(f"📡 Recherche vidéo d'ambiance : '{query}'...")
        
        video_url = self.get_pixabay(query)
        if not video_url:
            video_url = self.get_pexels(query)

        if not video_url:
            if not is_fallback:
                pool = fallback_keywords or self.default_fallback_pool
                fallback_query = random.choice(pool)
                print(f"🔄 Roue de secours vidéo activée avec : '{fallback_query}'...")
                return self.fetch_background(fallback_query, output_path, is_fallback=True)
            return False

        if video_url:
            print("📥 Téléchargement vidéo en cours...")
            return download_file(video_url, output_path)