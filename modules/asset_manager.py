import os
import time
import requests
import urllib.parse
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
        import random
        
        # On force un style sombre, réaliste et cinématique pour éviter les hallucinations abstraites de Pollinations
        forced_style = ", dark cinematic moody lighting, mysterious historical documentary style, photorealistic, high detail"
        clean_prompt = prompt.replace(forced_style, "") + forced_style
        
        # Ajout d'un seed aléatoire pour forcer l'IA à générer une nouvelle image à chaque fois et éviter l'image par défaut en cache
        seed = random.randint(1, 1000000)
        
        url = self.pollinations_url + urllib.parse.quote(clean_prompt) + f"?seed={seed}&nologo=true"
        
        r = requests.get(url, timeout=90)
        if r.status_code == 429:
            raise RuntimeError("429 Too Many Requests")
        r.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(r.content)
            
        # Sécurité supplémentaire : si le fichier récupéré est l'image par défaut connue de Pollinations, on déclenche une erreur
        if os.path.getsize(output_path) < 15000: # Les images par défaut de fallback font souvent une taille spécifique
            pass # Tu pourrais ajouter un contrôle ici si besoin
            
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
                        # On teste plusieurs formats, pas seulement "medium"
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
                        # Priorité au HD, sinon on prend le premier mp4 valide
                        selected = next(
                            (f for f in mp4_files if f.get("quality") == "hd"),
                            mp4_files[0],
                        )
                        return selected["link"]
        except Exception as e:
            print(f"❌ Exception Pexels : {e}")
        return None

    def fetch_background_video(self, query, output_path):
        """Fonction principale pour télécharger le fond vidéo en cascade."""
        print(f"📡 Recherche du fond vidéo pour : '{query}'...")

        # 1. Pixabay
        video_url = self._get_pixabay_video(query)
        if video_url:
            print("✅ Vidéo trouvée sur Pixabay !")

        # 2. Pexels (Fallback)
        if not video_url:
            print("🔄 Basculement vers Pexels...")
            video_url = self._get_pexels_video(query)
            if video_url:
                print("✅ Vidéo trouvée sur Pexels !")

        # 3. Téléchargement
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

        print("❌ Impossible de récupérer un fond vidéo via les API.")
        return False
