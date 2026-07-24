import os
import time
import requests

class AIImageGenerator:
    def __init__(self):
        print("🎨 Utilisation du générateur d'images Pollinations.ai (Sans token requis)")

    def generate_image(self, prompt_text, output_path):
        print(f"🎨 Génération d'une image pour : {prompt_text}")
        
        # On enrichit le prompt pour le style 3D / TikTok
        enhanced_prompt = f"{prompt_text}, 3D Pixar style, vibrant colors, highly detailed, cinematic lighting, vertical 9:16 aspect ratio"
        
        # URL de l'API gratuite Pollinations
        encoded_prompt = requests.utils.quote(enhanced_prompt)
        api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"
        
        try:
            # Petite pause pour éviter de saturer la file d'attente de l'API
            time.sleep(3)
            
            response = requests.get(api_url, timeout=60)
            
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                print(f"    ✅ Image IA sauvegardée : {output_path}")
                return True
            else:
                print(f"    ❌ Erreur API Pollinations ({response.status_code})")
                return False
        except Exception as e:
            print(f"    ❌ Erreur de génération d'image : {e}")
            return False

class AssetManager:
    def __init__(self):
        self.image_gen = AIImageGenerator()
        
        # Répertoire de stockage temporaire pour les images générées
        self.assets_dir = os.path.join(os.getcwd(), "assets", "temp")
        os.makedirs(self.assets_dir, exist_ok=True)

    def get_videos(self, script_data):
        """
        Remplace les vidéos de Pexels par des images fixes générées par IA 
        (deux images par scène : visual_1 et visual_2) au format vertical 9:16.
        Retourne un DICTIONNAIRE indexé par scene_id pour correspondre au compositeur.
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

            # 5. Enregistrement dans le dictionnaire des assets par scene_id
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
