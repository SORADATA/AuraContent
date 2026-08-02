import os
import urllib.parse
import requests


FALLBACK_VIDEO = os.path.join(os.getcwd(), "assets", "videos", "fallback.mp4")


class AssetManager:
    def __init__(self):
        self.video_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.video_dir, exist_ok=True)

    def get_videos(self, script_data):
        """
        Récupère un visuel par scène selon le rôle :
        - Pexels pour hook/example/cta
        - Pollinations pour analogy/misconception
        - fallback vidéo si tout échoue
        Retourne une liste de chemins vidéos alignée avec script_data.
        """
        video_paths = []

        for scene in script_data:
            scene_id = scene["id"]
            role = scene.get("role", "example")
            output_path = os.path.join(self.video_dir, f"scene_{scene_id}.mp4")

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"   ✅ Vidéo déjà en cache pour la scène {scene_id}")
                video_paths.append(output_path)
                continue

            query = scene.get("stock_search", "finance")
            image_prompt = scene.get("image_prompt", "")

            # Pollinations pour les scènes abstraites / métaphores
            if role in {"analogy", "misconception"} and image_prompt:
                print(f"🎨 Scene {scene_id} - Pollinations pour {role}...")
                pollinations_path = self._try_pollinations(scene_id, image_prompt, output_path)
                if pollinations_path:
                    video_paths.append(pollinations_path)
                    continue

            # Pexels par défaut
            print(f"🎬 Scene {scene_id} - Récupération de la vidéo Pexels...")
            pexels_path = self._try_pexels(query, output_path)
            if pexels_path:
                video_paths.append(pexels_path)
                continue

            print(f"   ⚠️ Scene {scene_id}: échec Pexels/Pollinations, utilisation de la vidéo fallback")
            if os.path.exists(FALLBACK_VIDEO):
                video_paths.append(FALLBACK_VIDEO)
            else:
                print(f"   ❌ Scene {scene_id}: fallback introuvable (ajoute assets/fallback_finance.mp4) !")
                video_paths.append(None)

        return video_paths

    def _try_pexels(self, query, output_path):
        try:
            from modules.utils.pexels_client import get_pexels_video
            video_path = get_pexels_video(query, output_path)
            if video_path and os.path.exists(video_path):
                return video_path
        except Exception as e:
            print(f"   ⚠️ Pexels indisponible: {e}")
        return None

    def _try_pollinations(self, scene_id, prompt, output_path):
        """Pollinations sans token : récupère une image puis la transforme en clip via FFmpeg.
        Le rendu final est une vidéo courte avec zoom léger."""
        try:
            import ffmpeg
        except Exception as e:
            print(f"   ⚠️ FFmpeg indisponible pour Pollinations: {e}")
            return None

        image_path = os.path.join(self.video_dir, f"pollinations_{scene_id}.jpg")
        encoded_prompt = urllib.parse.quote(prompt)
        seed = scene_id * 9973
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1080&height=1920&model=flux&nologo=true&safe=true&seed={seed}"
        )

        try:
            resp = requests.get(url, timeout=35)
            if resp.status_code != 200 or len(resp.content) < 1000:
                return None
            with open(image_path, "wb") as f:
                f.write(resp.content)
        except Exception as e:
            print(f"   ⚠️ Pollinations erreur: {e}")
            return None

        try:
            duration = 5.0
            zoom_frames = int(duration * 30)
            (
                ffmpeg.input(image_path, loop=1, t=duration)
                .filter("scale", 2160, 3840)
                .filter(
                    "zoompan",
                    z="min(zoom+0.0008,1.15)",
                    d=zoom_frames,
                    x="iw/2-(iw/zoom/2)",
                    y="ih/2-(ih/zoom/2)",
                    s="1080x1920",
                    fps=30,
                )
                .output(output_path, vcodec="libx264", pix_fmt="yuv420p", crf=18, preset="medium", t=duration)
                .run(overwrite_output=True, quiet=True)
            )
            return output_path
        except Exception as e:
            print(f"   ⚠️ Pollinations conversion vidéo échouée: {e}")
            return None
