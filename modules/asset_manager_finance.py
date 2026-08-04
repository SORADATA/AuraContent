import os
import shutil
import time
import urllib.parse
import requests
import random
import ffmpeg

from modules.utils.pexels_client import get_pexels_video

FALLBACK_VIDEO = os.path.join(os.getcwd(), "assets", "videos", "fallback.mp4")

DEFAULT_CLIP_DURATION = 4.0

class AssetManager:
    def __init__(self, run_id=None):
        self.run_id = run_id or time.strftime("%Y%m%d_%H%M%S")

        self.video_dir = os.path.join(os.getcwd(), "assets", "video_clips", self.run_id)
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        os.makedirs(self.video_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        self.width = 1080
        self.height = 1920
        self.fps = 30

    def _safe_exists(self, path):
        return path and os.path.exists(path) and os.path.getsize(path) > 0

    def _try_pexels(self, query, output_path):
        try:
            result_path = get_pexels_video(query, output_path)
            if self._safe_exists(result_path):
                return result_path
            return None
        except Exception as e:
            print(f"    ❌ Erreur Pexels pour la requête '{query}': {e}")
            return None

    def _pollinations_image_to_video(self, img_path, output_path, duration):
        try:
            zoom_frames = max(int(duration * self.fps), 1)
            (
                ffmpeg.input(img_path, loop=1, t=duration)
                .filter("scale", self.width * 2, self.height * 2)
                .filter(
                    "zoompan",
                    z="min(zoom+0.0008,1.15)",
                    d=zoom_frames,
                    x="iw/2-(iw/zoom/2)",
                    y="ih/2-(ih/zoom/2)",
                    s=f"{self.width}x{self.height}",
                    fps=self.fps,
                )
                .output(output_path, vcodec="libx264", pix_fmt="yuv420p", crf=18, preset="medium", t=duration)
                .run(overwrite_output=True, quiet=True)
            )
            return output_path if self._safe_exists(output_path) else None
        except Exception as e:
            print(f"    ❌ Conversion image->vidéo échouée: {e}")
            return None

    def _try_pollinations(self, scene_id, image_prompt, output_path, duration, retries=3):
        """Génère un visuel via Pollinations avec le système de retry robuste de ton autre script."""
        img_path = os.path.join(self.temp_dir, f"pollinations_{self.run_id}_{scene_id}.jpg")
        
        for attempt in range(retries + 1):
            if attempt > 0:
                wait_time = min(4 * (2 ** (attempt - 1)) + random.uniform(0, 1.5), 15)
                print(f"    ⏳ Tentative {attempt + 1}/{retries + 1} Pollinations (pause {wait_time:.1f}s)...")
                time.sleep(wait_time)

            try:
                encoded_prompt = urllib.parse.quote(image_prompt)
                seed = random.randint(1, 999999)
                # Ajout de enhance=true comme dans ton script pour de meilleurs visuels
                url = (
                    f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                    f"?width={self.width}&height={self.height}&nologo=true&seed={seed}&enhance=true"
                )

                # Timeout passé à 120s avec un User-Agent
                response = requests.get(
                    url, 
                    timeout=120, 
                    headers={"User-Agent": "FinanceGenerator/1.0"}
                )

                content_type = response.headers.get("Content-Type", "")

                if response.status_code == 200 and content_type.startswith("image/") and len(response.content) > 5000:
                    with open(img_path, "wb") as f:
                        f.write(response.content)

                    if self._safe_exists(img_path):
                        return self._pollinations_image_to_video(img_path, output_path, duration=duration)
                
                elif response.status_code == 429:
                    print("    ⚠️ Limite de requêtes Pollinations atteinte.")
                else:
                    print(f"    ⚠️ Erreur Pollinations : HTTP {response.status_code}")

            except requests.exceptions.Timeout:
                print("    ⚠️ Timeout Pollinations (serveur surchargé).")
            except Exception as e:
                print(f"    ❌ Erreur Pollinations pour la scène {scene_id}: {e}")
                
        print(f"    ❌ Échec définitif de Pollinations après {retries} tentatives.")
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except OSError:
                pass
        return None

    def _copy_fallback(self, output_path):
        try:
            if self._safe_exists(FALLBACK_VIDEO):
                shutil.copy2(FALLBACK_VIDEO, output_path)
                return output_path if self._safe_exists(output_path) else None
            return None
        except Exception as e:
            print(f"    ❌ Erreur fallback vidéo: {e}")
            return None

    def get_videos(self, script_data):
        video_paths = []

        # Utilisation de enumerate pour permettre l'alternance 1 scène sur 2
        for idx, scene in enumerate(script_data):
            scene_id = scene["id"]
            role = scene.get("role", "example")
            output_path = os.path.join(self.video_dir, f"scene_{scene_id}.mp4")

            duration = float(scene.get("duration") or DEFAULT_CLIP_DURATION)

            if self._safe_exists(output_path):
                print(f"    ✅ Vidéo déjà en cache pour la scène {scene_id}")
                video_paths.append(output_path)
                continue

            query = scene.get("stock_search", "finance")
            image_prompt = scene.get("image_prompt", "")

            # MODIFICATION ICI : Alternance IA (1 sur 2) ou rôles spécifiques
            if image_prompt and (idx % 2 == 0 or role in {"analogy", "misconception", "example"}):
                print(f"🎨 Scene {scene_id} - Génération IA Pollinations (Flux)...")
                pollinations_path = self._try_pollinations(scene_id, image_prompt, output_path, duration=duration)
                if self._safe_exists(pollinations_path):
                    video_paths.append(pollinations_path)
                    continue

            print(f"🎬 Scene {scene_id} - Récupération de la vidéo Pexels...")
            pexels_path = self._try_pexels(query, output_path)
            if self._safe_exists(pexels_path):
                video_paths.append(pexels_path)
                continue

            print(f"    ⚠️ Scene {scene_id}: échec Pexels/Pollinations, utilisation de la vidéo fallback")
            fallback_path = self._copy_fallback(output_path)
            if self._safe_exists(fallback_path):
                video_paths.append(fallback_path)
            else:
                print(f"    ❌ Scene {scene_id}: fallback introuvable !")
                video_paths.append(None)

        return video_paths
