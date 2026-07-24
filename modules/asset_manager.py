import os
from modules.image_generator import AIImageGenerator

class AssetManager:
    def __init__(self):
        # On initialise notre générateur d'images IA (Hugging Face)
        self.image_gen = AIImageGenerator()
        
        # Répertoire de stockage temporaire pour les images générées
        self.assets_dir = os.path.join(os.getcwd(), "assets", "temp")
        os.makedirs(self.assets_dir, exist_ok=True)

    def get_videos(self, script_data):
        """
        Remplace les vidéos de Pexels par des images fixes générées par IA 
        (deux images par scène : visual_1 et visual_2) au format vertical 9:16.
        """
        print("🤖 Génération des visuels par IA (Style 3D / Tendance TikTok)...")
        assets_map = {}

        for scene in script_data:
            scene_id = scene.get('id')
            
            # 1. Récupération des prompts textuels en anglais
            query_a = scene.get('visual_1', scene.get('keywords', 'cinematic abstract background'))
            query_b = scene.get('visual_2', query_a) # Utilise visual_1 si visual_2 est absent

            path_a = os.path.join(self.assets_dir, f"scene_{scene_id}_a.jpg")
            path_b = os.path.join(self.assets_dir, f"scene_{scene_id}_b.jpg")

            print(f"\n--- Scène {scene_id} ---")
            
            # 2. Génération de l'image A par IA
            success_a = self.image_gen.generate_image(query_a, path_a)
            
            # 3. Génération de l'image B par IA (pour le switch visuel)
            success_b = self.image_gen.generate_image(query_b, path_b)

            # 4. Logique de secours (Self-Healing) si une image échoue
            if not success_a and success_b:
                path_a = path_b
                print(f"    ⚠️ Scène {scene_id} Image A manquante. Utilisation de l'image B.")
            if not success_b and success_a:
                path_b = path_a
                print(f"    ⚠️ Scène {scene_id} Image B manquante. Utilisation de l'image A.")

            # 5. Enregistrement dans la carte des assets au format attendu par le reste du projet
            if os.path.exists(path_a) and os.path.exists(path_b):
                assets_map[scene_id] = {
                    "a": path_a,
                    "b": path_b
                }
                print(f"    ✅ Scène {scene_id} prête (Visuels A + B générés par IA).")
            else:
                print(f"    ❌ Échec de génération pour la scène {scene_id}.")
                assets_map[scene_id] = None

        return assets_map

# --- TESTING ---
if __name__ == "__main__":
    manager = AssetManager()
    
    test_script = [
        {
            "id": 1, 
            "visual_1": "cute cartoon lion in a magical forest, 3d pixar style", 
            "visual_2": "little baby looking at a white fluffy cat, cute animation"
        }
    ]
    
    results = manager.get_videos(test_script)
    print("🎨 Assets IA Générés:", results)
