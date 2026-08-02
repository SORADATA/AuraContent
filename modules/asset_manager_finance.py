import os
from modules.utils.pexels_client import get_pexels_video


FALLBACK_VIDEO = os.path.join(os.getcwd(), "assets", "videos", "fallback_finance.mp4")


class AssetManager:
    def __init__(self):
        # On renomme intelligemment le dossier en "video_clips"
        self.video_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.video_dir, exist_ok=True)

    def get_videos(self, script_data):
        """
        Récupère 1 vidéo Pexels par scène en utilisant le 'stock_search' du script.
        Si échec, utilise la vidéo de secours (fallback).
        Retourne une liste simple de chemins vidéos alignée avec script_data.
        """
        video_paths = []

        for scene in script_data:
            scene_id = scene["id"]
            output_path = os.path.join(self.video_dir, f"scene_{scene_id}.mp4")

            print(f"🎬 Scene {scene_id} - Récupération de la vidéo Pexels...")

            # On vérifie si la vidéo existe déjà (pratique si tu relances le script après un bug)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"    ✅ Vidéo déjà en cache pour la scène {scene_id}")
                video_paths.append(output_path)
                continue

            # On extrait les mots-clés générés par le Cerveau IA
            query = scene.get("stock_search", "finance")
            
            # Appel à notre script Pexels
            video_path = get_pexels_video(query, output_path)

            if video_path and os.path.exists(video_path):
                video_paths.append(video_path)
            else:
                print(f"    ⚠️ Scene {scene_id}: échec Pexels, utilisation de la vidéo de fallback")
                if os.path.exists(FALLBACK_VIDEO):
                    video_paths.append(FALLBACK_VIDEO)
                else:
                    print(
                        f"    ❌ Scene {scene_id}: fallback introuvable (pense à ajouter assets/fallback_finance.mp4) ! Scène ignorée.")
                    video_paths.append(None)

        return video_paths
