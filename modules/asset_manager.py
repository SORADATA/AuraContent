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

        # === CORRECTIF 1 : User-Agent conforme à la politique Wikimedia ===
        # Format exigé : NomApp/version (contact-email-ou-URL-du-projet)
        # Remplace l'email/URL ci-dessous par les tiens (repo GitHub ou email valide).
        contact = os.getenv("WIKIMEDIA_CONTACT", "https://github.com/tonuser/AuraContent")
        self.wiki_headers = {
            "User-Agent": f"AuraContentPipeline/1.2 ({contact}) requests/{requests.__version__}"
        }
        self.wiki_api_url = "https://commons.wikimedia.org/w/api.php"

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
        forced_style = ", dark cinematic moody lighting, mysterious historical documentary style, photorealistic, high detail"
        clean_prompt = prompt.replace(forced_style, "") + forced_style

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

    def _wiki_get(self, params, timeout=10, max_retries=2):
        """
        CORRECTIF 2 : wrapper centralisé pour tous les appels API Wikimedia.
        - Utilise le bon User-Agent
        - Logge le vrai status code HTTP au lieu d'échouer silencieusement
        - Gère le 429 en respectant Retry-After
        """
        for attempt in range(max_retries + 1):
            try:
                r = requests.get(
                    self.wiki_api_url,
                    params=params,
                    headers=self.wiki_headers,
                    timeout=timeout,
                )
            except Exception as e:
                print(f"❌ Exception réseau Wikimedia API : {e}")
                return None

            if r.status_code == 200:
                return r
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5))
                print(f"⏳ 429 Too Many Requests (API) — attente {wait}s...")
                time.sleep(wait)
                continue
            if r.status_code == 403:
                print(f"❌ 403 Forbidden (API) — vérifier le User-Agent / policy Wikimedia.")
                return None

            print(f"❌ HTTP {r.status_code} inattendu sur l'API Wikimedia.")
            return None

        return None

    def _download_first_valid(self, pages, output_path, headers):
        """
        Parcourt les pages retournées par l'API Commons et télécharge la première
        image jpeg/png valide trouvée, puis s'arrête immédiatement.

        CORRECTIF 3 : on logge le status HTTP réel du téléchargement du fichier
        (au lieu de dépendre uniquement de _file_ok pour deviner un échec),
        on gère le 429 avec backoff, et on ajoute un petit délai entre
        chaque tentative pour respecter les limites de débit Wikimedia.
        """
        for page_id, page_info in pages.items():
            image_info_list = page_info.get("imageinfo", [])
            if not image_info_list:
                continue
            info = image_info_list[0]
            mime_type = info.get("mime", "")
            img_url = info.get("url", "")
            if not (img_url and ("jpeg" in mime_type or "jpg" in mime_type or "png" in mime_type)):
                continue

            title = page_info.get("title", "image")
            print(f"⬇️ Téléchargement de l'archive Wikimedia ({title})...")

            try:
                resp = requests.get(img_url, headers=headers, timeout=15)

                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 5))
                    print(f"⏳ 429 Too Many Requests (fichier) — attente {wait}s puis retry...")
                    time.sleep(wait)
                    resp = requests.get(img_url, headers=headers, timeout=15)

                if resp.status_code != 200:
                    print(f"❌ HTTP {resp.status_code} pour {img_url}")
                    time.sleep(0.5)
                    continue

                with open(output_path, "wb") as f:
                    f.write(resp.content)

                if self._file_ok(output_path):
                    print("✅ Image historique sauvegardée avec succès !")
                    return True
                else:
                    print(f"⚠️ Fichier téléchargé mais trop petit/corrompu ({title}).")

            except Exception as e:
                print(f"❌ Exception téléchargement image Wikimedia : {e}")

            # CORRECTIF 4 : throttling entre chaque tentative de fichier
            time.sleep(0.5)

        return False

    def fetch_wikimedia_image(self, query, output_path):
        """Recherche et télécharge une photo exacte d'un lieu (ex: 'Île de Saint-Cado').

        Stratégie en cascade :
        1) Catégorie Commons exacte ("Catégorie:<query>" ou "Category:<query>")
        2) Catégorie approchante trouvée via une recherche dans le namespace Catégorie.
        3) Recherche plein texte classique sur les fichiers en dernier recours.
        """
        headers = self.wiki_headers

        # --- 1) Catégorie exacte ---
        print(f"🏛️ Recherche de la catégorie Wikimedia exacte pour : '{query}'...")
        cat_target = f"Catégorie:{query}" if not query.startswith("Category:") and not query.startswith("Catégorie:") else query
        params = {
            "action": "query",
            "format": "json",
            "generator": "categorymembers",
            "gcmtitle": cat_target,
            "gcmtype": "file",
            "gcmlimit": "3",  # réduit de 5 à 3 pour limiter le volume de requêtes
            "prop": "imageinfo",
            "iiprop": "url|mime",
        }
        r = self._wiki_get(params)
        if r is not None:
            pages = r.json().get("query", {}).get("pages", {})
            if pages and self._download_first_valid(pages, output_path, headers):
                return True

        time.sleep(0.5)  # throttling entre les étapes de la cascade

        # --- 2) Catégorie approchante trouvée via recherche dans le namespace Catégorie (14) ---
        print(f"🔎 Aucune catégorie exacte, recherche d'une catégorie approchante pour : '{query}'...")
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srnamespace": "14",  # namespace "Category"
            "srlimit": "3",
        }
        r = self._wiki_get(params)
        if r is not None:
            results = r.json().get("query", {}).get("search", [])
            for result in results:
                cat_title = result.get("title")  # ex: "Category:Île de Saint-Cado"
                params2 = {
                    "action": "query",
                    "format": "json",
                    "generator": "categorymembers",
                    "gcmtitle": cat_title,
                    "gcmtype": "file",
                    "gcmlimit": "3",
                    "prop": "imageinfo",
                    "iiprop": "url|mime",
                }
                r2 = self._wiki_get(params2)
                if r2 is not None:
                    pages = r2.json().get("query", {}).get("pages", {})
                    if pages and self._download_first_valid(pages, output_path, headers):
                        return True
                time.sleep(0.5)

        time.sleep(0.5)

        # --- 3) Fallback : recherche plein texte sur les fichiers ---
        print(f"🏛️ Recherche plein texte Wikimedia pour : '{query}'...")
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": "6",  # Fichiers média
            "gsrlimit": "3",
            "prop": "imageinfo",
            "iiprop": "url|mime",
        }
        r = self._wiki_get(params)
        if r is not None:
            pages = r.json().get("query", {}).get("pages", {})
            if pages and self._download_first_valid(pages, output_path, headers):
                return True

        print("⚠️ Aucun lieu exact exploitable trouvé sur Wikimedia.")
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
