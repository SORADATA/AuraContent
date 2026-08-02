import os
import urllib.parse
import requests
from modules.utils.pexels_client import get_pexels_video


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
                print(f"    ⚠️ Scene {scene_id}: échec Pexels, utilisation de la vidéo de fallback")
                if os.path.exists(FALLBACK_VIDEO):
                    video_paths.append(FALLBACK_VIDEO)
                else:
                    print(
                        f"    ❌ Scene {scene_id}: fallback introuvable (pense à ajouter assets/fallback_finance.mp4) ! Scène ignorée.")
                    video_paths.append(None)

        return video_paths
