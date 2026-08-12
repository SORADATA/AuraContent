import os
import time
import requests
import urllib.parse
import random
from PIL import Image, ImageDraw, ImageFont


class AssetManager:
    def __init__(self):
        # Configuration Images
        self.pollinations_url = "https://image.pollinations.ai/prompt/"
        # Configuration Vidéos
        self.pixabay_api_key = os.getenv("PIXABAY_API_KEY")
        self.pexels_api_key = os.getenv("PEXELS_API_KEY")

    def _file_ok(self, path, min_bytes=5000):
        """Vérifie que le fichier existe et n'est pas corrompu/vide."""
        return os.path.exists(path) and os.path.getsize(path) >= min_bytes

    # ==========================================
    # 🖼️ PARTIE IMAGES (POLLINATIONS & FALLBACK)
    # ==========================================

    def _save_text_fallback(self, prompt, output_path):
        """Génère une image noire avec le texte du prompt en cas de crash total."""
        img = Image.new("RGB", (1080, 1920), (15, 15, 18))
        draw = ImageDraw.Draw(img)
        text = "Fallback image\n\n" + prompt[:180]

        try:
            font = ImageFont.truetype("arial.ttf", 42)
        except Exception:
            font = ImageFont.load_default()

        draw.multiline_text((80, 120), text, fill="white", font=font, spacing=14)
        img.save(output_path)
        return self._file_ok(output_path, min_bytes=1000)

    def _pollinations(self, prompt, output_path):
        """Génère une image via Pollinations.ai avec un style sombre forcé et un seed aléatoire."""
        # On force un style sombre, réaliste et cinématique pour éviter les hallucinations abstraites de Pollinations
        forced_style = ", dark cinematic moody lighting, mysterious historical documentary style, photorealistic, high detail"
        clean_prompt = prompt.replace(forced_style, "") + forced_style
        
        # Ajout d'un seed aléatoire pour forcer l'IA à générer une nouvelle image
        seed = random.randint(1, 1000000)
        
        url = self.pollinations_url + urllib.parse.quote(clean_prompt) + f"?seed={seed}&nologo=true"
        
        r = requests.get(url, timeout=90)
        if r.status_code == 429:
            raise RuntimeError("429 Too Many Requests")
        r.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(r.content)
            
        return self._file_ok(output_path)

    def generate_image(self, prompt, output_path, visual_identity=None):
        """Fonction principale pour obtenir une image de scène."""
        full_prompt = f"{visual_identity}. {prompt}" if visual_identity else prompt
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            try:
                if self._pollinations(full_prompt, output_path):
                    print("✅ Pollinations utilisée avec succès")
                    return True
            except Exception as e:
                print(f"⚠️ Pollinations échec tentative {attempt}/{max_attempts}: {e}")
                if attempt < max_attempts:
                    time.sleep(min(2 ** attempt, 10))

        print("⚠️ Fallback texte utilisé")
        return self._save_text_fallback(full_prompt, output_path)

    # ==========================================
    # 🏛️ PARTIE ARCHIVES (WIKIMEDIA COMMONS)
    # ==========================================

    def fetch_wikimedia_image(self, query, output_path):
        """Recherche et télécharge une photo exacte d'un lieu (ex: 'Saint-Cado')."""
        print(f"🏛️ Recherche Wikimedia pour le lieu : '{query}'...")
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",  # Fichiers média
            "gsrlimit": "3",
            "prop": "imageinfo",
            "iiprop": "url|mime"
        }
        headers = {"User-Agent": "MinuteMysterePipeline/1.0"}
        
        try:
            r = requests.get(url, params=params, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    image_info_list = page_info.get("imageinfo", [])
                    if not image_info_list:
                        continue
                        
                    info = image_info_list[0]
                    mime_type = info.get("mime", "")
                    img_url = info.get("url", "")
                    
                    if img_url and ("jpeg" in mime_type or "png" in mime_type):
                        print("⬇️ Téléchargement de l'archive Wikimedia...")
                        img_data = requests.get(img_url, headers=headers, timeout=15).content
                        with open(output_path, "wb") as f:
                            f.write(img_data)
                        
                        if self._file_ok(output_path):
                            print("✅ Image historique sauvegardée avec succès !")
                            return True
        except Exception as e:
            print(f"❌ Exception Wikimedia : {e}")
            
        print("⚠️ Aucun lieu exact trouvé sur Wikimedia.")
        return False

    # ==========================================
    # 🎥 PARTIE VIDÉOS (PIXABAY & PEXELS)
    # ==========================================

    def _get_pixabay_video(self, query):
        if not self.pixabay_api_key:
            return None

        encoded_query = urllib.parse.quote(query)
        url = f"https://pixabay.com/api/videos/?key={self.pixabay_api_key}&q={encoded_query}&video_type=film"

        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("totalHits", 0) > 0:
                    for hit in data["hits"]:
                        for size in ("large", "medium", "small", "tiny"):
                            stream = hit["videos"].get(size)
                            if stream and stream["height"] > stream["width"]:
                                return stream["url"]
        except Exception as e:
            print(f"❌ Exception Pixabay : {e}")
        return None

    def _get_pexels_video(self, query):
        if not self.pexels_api_key:
            return None

        encoded_query = urllib.parse.quote(query)
        url = f"https://api.pexels.com/videos/search?query={encoded_query}&orientation=portrait&per_page=5"
        headers = {"Authorization": self.pexels_api_key}

        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("total_results", 0) > 0:
                    for video in data["videos"]:
                        mp4_files = [
                            f for f in video.get("video_files", [])
                            if f.get("file_type") == "video/mp4"
                        ]
                        if not mp4_files:
                            continue
                        selected = next(
                            (f for f in mp4_files if f.get("quality") == "hd"),
                            mp4_files[0],
                        )
                        return selected["link"]
        except Exception as e:
            print(f"❌ Exception Pexels : {e}")
        return None

    def fetch_background_video(self, query, output_path, is_fallback=False):
        """Fonction principale pour télécharger le fond vidéo en cascade avec filet de sécurité."""
        print(f"📡 Recherche du fond vidéo pour : '{query}'...")

        # 1. Pixabay
        video_url = self._get_pixabay_video(query)
        if video_url:
            print("✅ Vidéo trouvée sur Pixabay !")

        # 2. Pexels (Fallback API)
        if not video_url:
            print("🔄 Basculement vers Pexels...")
            video_url = self._get_pexels_video(query)
            if video_url:
                print("✅ Vidéo trouvée sur Pexels !")

        # 3. Roue de secours (Fallback Ambiance "Minute Mystère")
        if not video_url:
            if not is_fallback:
                fallback_keywords = [
                    "dark ocean waves", "foggy rocky coast", 
                    "creepy dark forest", "old stone ruins", 
                    "dark rainy night", "ancient stone bridge"
                ]
                fallback_query = random.choice(fallback_keywords)
                print(f"⚠️ Aucun résultat pour '{query}'.")
                print(f"🔄 Déclenchement de la roue de secours avec : '{fallback_query}'...")
                # On relance la fonction avec le mot-clé de secours
                return self.fetch_background_video(fallback_query, output_path, is_fallback=True)
            else:
                print("❌ Impossible de récupérer un fond vidéo même avec la roue de secours.")
                return False

        # 4. Téléchargement
        if video_url:
            print("📥 Téléchargement en cours...")
            try:
                r = requests.get(video_url, stream=True, timeout=30)
                r.raise_for_status()
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                if self._file_ok(output_path):
                    print("✅ Vidéo sauvegardée avec succès !")
                    return True
            except Exception as e:
                print(f"❌ Erreur de téléchargement : {e}")

        return False
