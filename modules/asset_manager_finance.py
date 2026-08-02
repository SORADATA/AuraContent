import os
import urllib.parse
import requests
import random
import ffmpeg

from modules.utils.pexels_client import get_pexels_video

FALLBACK_VIDEO = os.path.join(os.getcwd(), "assets", "videos", "fallback.mp4")


class AssetManager:
    def __init__(self):
        self.video_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        self.temp_dir = os.path.join(os.getcwd(), "assets", "temp")
        os.makedirs(self.video_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        self.width = 1080
        self.height = 1920
        self.fps = 30

    def _safe_exists(self, path):
        return path and os.path.exists(path) and os.path.getsize(path) > 0

    def _try_pexels(self, query, output_path):
        """Télécharge une vidéo Pexels et la sauvegarde localement."""
        try:
            result_path = get_pexels_video(query, output_path)
            if self._safe_exists(result_path):
                return result_path
            return None
        except Exception as e:
            print(f"    ❌ Erreur Pexels pour la requête '{query}': {e}")
            return None

    def _pollinations_image_to_video(self, img_path, output_path, duration=4.0):
        """Transforme une image en mini vidéo avec léger zoom."""
        try:
            zoom_frames = int(duration * self.fps)
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

    def _try_pollinations(self, scene_id, image_prompt, output_path, duration=4.0):
        """Génère un visuel via Pollinations puis le convertit en vidéo."""
        try:
            encoded_prompt = urllib.parse.quote(image_prompt)
            seed = random.randint(1, 999999)
            url = (
                f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                f"?width={self.width}&height={self.height}&nologo=true&seed={seed}"
            )

            img_path = os.path.join(self.temp_dir, f"pollinations_{scene_id}.jpg")
            response = requests.get(url, timeout=60)
            response.raise_for_status()

            with open(img_path, "wb") as f:
                f.write(response.content)

            if not self._safe_exists(img_path):
                return None

            return self._pollinations_image_to_video(img_path, output_path, duration=duration)

        except Exception as e:
            print(f"    ❌ Erreur Pollinations pour la scène {scene_id}: {e}")
            return None

    def _copy_fallback(self, output_path):
        """Retourne une vidéo fallback sûre."""
        try:
            if self._safe_exists(FALLBACK_VIDEO):
                import shutil
                shutil.copy2(FALLBACK_VIDEO, output_path)
                return output_path if self._safe_exists(output_path) else None
            return None
        except Exception as e:
            print(f"    ❌ Erreur fallback vidéo: {e}")
            return None

    def get_videos(self, script_data):
        """
        Récupère un visuel par scène selon le rôle :
        - Pollinations pour analogy/misconception
        - Pexels pour le reste
        - fallback vidéo si tout échoue
        Retourne une liste de chemins vidéos alignée avec script_data.
        """
        video_paths = []

        for scene in script_data:
            scene_id = scene["id"]
            role = scene.get("role", "example")
            output_path = os.path.join(self.video_dir, f"scene_{scene_id}.mp4")

            if self._safe_exists(output_path):
                print(f"    ✅ Vidéo déjà en cache pour la scène {scene_id}")
                video_paths.append(output_path)
                continue

            query = scene.get("stock_search", "finance")
            image_prompt = scene.get("image_prompt", "")

            if role in {"analogy", "misconception"} and image_prompt:
                print(f"🎨 Scene {scene_id} - Pollinations pour {role}...")
                pollinations_path = self._try_pollinations(scene_id, image_prompt, output_path)
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
