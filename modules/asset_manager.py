import os
from modules.ai_image import AIImageGenerator

FALLBACK_IMAGE = os.path.join(os.getcwd(), "assets", "fallback.png")


class AssetManager:
    def __init__(self):
        self.image_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.image_dir, exist_ok=True)
        self.generator = AIImageGenerator()

    def get_videos(self, script_data):
        """
        Genere 2 images IA (a/b) par scene, avec retry en cas d'echec.
        Si les deux tentatives echouent, utilise une image de secours locale
        pour eviter qu'une scene entiere soit ignoree.
        Retourne une liste de dicts {"a": path, "b": path} alignee avec script_data.
        """
        pairs = []
        for scene in script_data:
            scene_id = scene["id"]
            path_a = os.path.join(self.image_dir, f"scene_{scene_id}_a.png")
            path_b = os.path.join(self.image_dir, f"scene_{scene_id}_b.png")

            print(f"🎨 Scene {scene_id} — generation des visuels IA...")

            ok_a = self.generator.generate_image(scene["visual_1"], path_a)
            ok_b = self.generator.generate_image(scene["visual_2"], path_b)

            if ok_a and ok_b:
                pairs.append({"a": path_a, "b": path_b})
            elif ok_a:
                print(f"    ⚠️ Scene {scene_id}: visual_2 a echoue, reutilisation de visual_1")
                pairs.append({"a": path_a, "b": path_a})
            elif ok_b:
                print(f"    ⚠️ Scene {scene_id}: visual_1 a echoue, reutilisation de visual_2")
                pairs.append({"a": path_b, "b": path_b})
            else:
                print(f"    ⚠️ Scene {scene_id}: aucune image generee, utilisation du fallback")
                if os.path.exists(FALLBACK_IMAGE):
                    pairs.append({"a": FALLBACK_IMAGE, "b": FALLBACK_IMAGE})
                else:
                    print(f"    ❌ Scene {scene_id}: fallback introuvable, scene ignoree")
                    pairs.append(None)

        return pairs
