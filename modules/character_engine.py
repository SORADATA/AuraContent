import os
import shutil
from constants_mimolune import SPEAKERS
from modules.ai_image import AIImageGenerator


class CharacterEngine:
    """
    Gère l'image de référence de chaque personnage et génère
    l'illustration complète de chaque scène, utilisée ensuite
    comme image d'entrée pour l'animation Wan 2.2.
    """
    def __init__(self):
        self.char_dir = os.path.join("assets", "mimolune", "characters")
        self.images_dir = os.path.join("assets", "mimolune", "images")
        self.scene_dir = os.path.join("assets", "mimolune", "scenes")
        os.makedirs(self.char_dir, exist_ok=True)
        os.makedirs(self.scene_dir, exist_ok=True)

        self.image_gen = AIImageGenerator()

    def _manual_reference_path(self, speaker):
        """Cherche une image fournie manuellement dans assets/mimolune/images/."""
        candidate = os.path.join(self.images_dir, f"{speaker}.png")
        return candidate if os.path.exists(candidate) else None

    def prepare_assets(self):
        print("🔍 Vérification des images de référence des personnages...")

        for speaker in SPEAKERS:
            ref_path = os.path.join(self.char_dir, f"{speaker}_reference.png")

            if os.path.exists(ref_path):
                continue

            manual_path = self._manual_reference_path(speaker)
            if manual_path:
                shutil.copy(manual_path, ref_path)
                print(f"   ✅ Référence {speaker} récupérée depuis assets/mimolune/images/{speaker}.png")
                continue

            print(f"   ⚠️ [Test] Référence manquante : {speaker}, génération IA...")
            prompt = (
                f"Official character reference sheet of {speaker}, "
                "cute 2D cartoon style, full body, front view, "
                "solid white background, consistent design"
            )
            self.image_gen.generate_image(prompt, ref_path)

        print("✅ Images de référence des personnages prêtes.")

    def get_reference_path(self, speaker):
        ref_path = os.path.join(self.char_dir, f"{speaker}_reference.png")
        return ref_path if os.path.exists(ref_path) else None

    def generate_scene_images(self, scenes):
        """
        Pour chaque scène : si le personnage a une image de référence
        officielle, on l'utilise directement (cohérence garantie).
        Sinon, on génère une illustration de décor via l'IA.
        """
        print("🖼️ Préparation des illustrations de scène...")

        for scene in scenes:
            scene_id = scene["id"]
            speaker = scene.get("speaker", "mimolune")

            ref_path = self.get_reference_path(speaker)
            if ref_path:
                scene["background_image"] = ref_path
                continue

            scene_prompt = scene.get(
                "scene_prompt",
                f"{speaker} in a beautiful colorful magical landscape, "
                f"kids cartoon style, doing {scene.get('action', 'standing')}"
            )
            scene_path = os.path.join(self.scene_dir, f"scene_{scene_id}.png")

            if not os.path.exists(scene_path):
                self.image_gen.generate_image(scene_prompt, scene_path)

            scene["background_image"] = scene_path

        return scenes