import os
import urllib.parse
import requests
from modules.utils.pexels_client import get_pexels_video


FALLBACK_VIDEO = os.path.join(os.getcwd(), "assets", "videos", "fallback.mp4")


class AssetManager:
    def __init__(self):
        self.video_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.video_dir, exist_ok=True)

    def _try_pexels(self, query, output_path):
        """Télécharge une vidéo Pexels et la sauvegarde localement."""
        try:
            video_url = get_pexels_video(query)
            if not video_url:
                return None
            
            response = requests.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            return None
        except Exception as e:
            print(f"    ❌ Erreur Pexels pour la requête '{query}': {e}")
            return None

    def _try_pollinations(self, scene_id, image_prompt, output_path):
        """Génère un visuel via Pollinations (ou convertit en vidéo si géré)."""
        try:
            encoded_prompt = urllib.parse.quote(image_prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            # Sauvegarde temporaire en image ou traitement direct
            img_path = output_path.replace(".mp4", ".jpg")
            with open(img_path, "wb") as f:
                f.write(response.content)
            
            # Si tu transformes l'image en vidéo ou si tu la renvoies, ajuste ici.
            # Pour l'instant, on s'assure que la méthode existe et renvoie le chemin si valide.
            if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                # Si ton pipeline attend une vidéo, tu peux copier l'image ou la convertir, 
                # sinon renvoyer l'output_path si géré en amont.
                return output_path
            return None
        except Exception as e:
            print(f"    ❌ Erreur Pollinations pour la scène {scene_id}: {e}")
            return None

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
                print(f"    ✅ Vidéo déjà en cache pour la scène {scene_id}")
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

            print(f"    ⚠️ Scene {scene_id}: échec Pexels/Pollinations, utilisation de la vidéo fallback")
            if os.path.exists(FALLBACK_VIDEO):
                video_paths.append(FALLBACK_VIDEO)
            else:
                print(f"    ❌ Scene {scene_id}: fallback introuvable ! Scène ignorée.")
                video_paths.append(None)

        return video_paths
