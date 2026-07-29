import os
from constants_mimolune import SPEAKERS, POSES, MOUTHS
from modules.ai_image import AIImageGenerator

class CharacterEngine:
    """
    Gère la bibliothèque d'images des personnages et génère les décors.
    Pour le mode test, si une image n'existe pas, elle est générée via Pollinations.
    """
    def __init__(self):
        self.char_dir = os.path.join("assets", "mimolune", "characters")
        self.bg_dir = os.path.join("assets", "mimolune", "backgrounds")
        os.makedirs(self.char_dir, exist_ok=True)
        os.makedirs(self.bg_dir, exist_ok=True)
        
        # On instancie ton générateur d'images IA
        self.image_gen = AIImageGenerator()

    def prepare_assets(self):
        print("🔍 Vérification des assets visuels des personnages...")
        
        for speaker in SPEAKERS:
            speaker_dir = os.path.join(self.char_dir, speaker)
            os.makedirs(speaker_dir, exist_ok=True)

            # 1. Vérification/Génération des poses du corps
            for action in POSES:
                path = os.path.join(speaker_dir, f"pose_{action}.png")
                if not os.path.exists(path):
                    print(f"   ⚠️ [Test] Pose manquante : {speaker} - {action}.")
                    prompt = f"A simple cute cartoon 2D character {speaker}, doing action {action}, solid white background, minimal details"
                    self.image_gen.generate_image(prompt, path)

            # 2. Vérification/Génération des bouches
            for mouth in MOUTHS:
                path = os.path.join(speaker_dir, f"mouth_{mouth}.png")
                if not os.path.exists(path):
                    print(f"   ⚠️ [Test] Bouche manquante : {speaker} - {mouth}.")
                    prompt = f"A simple cartoon drawing of a mouth, {mouth}, on solid white background"
                    self.image_gen.generate_image(prompt, path)

        print("✅ Tous les assets personnages (poses et bouches) sont prêts.")

    def generate_backgrounds(self, scenes):
        """
        Génère les images de décor pour chaque scène de la comptine.
        """
        print("🖼️ Vérification et génération des décors...")
        
        for scene in scenes:
            scene_id = scene["id"]
            # Récupère le prompt généré par l'IA texte, avec un fallback de sécurité
            bg_prompt = scene.get("background", f"beautiful colorful magical landscape, kids cartoon style")
            bg_path = os.path.join(self.bg_dir, f"bg_{scene_id}.png")
            
            # Ne génère que si l'image n'existe pas déjà
            if not os.path.exists(bg_path):
                self.image_gen.generate_image(bg_prompt, bg_path)
            
            # 🔴 TRÈS IMPORTANT : On enregistre le chemin du décor dans la scène 
            # pour que le SceneAnimator (FFmpeg) puisse le trouver à l'étape suivante !
            scene["background_image"] = bg_path
            
        return scenes