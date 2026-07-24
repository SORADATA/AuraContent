import os
import requests

class AIImageGenerator:
    def __init__(self):
        print("🎨 Utilisation du générateur d'images Pollinations.ai (Sans token requis)")

    def generate_image(self, prompt_text, output_path):
        print(f"🎨 Génération d'une image pour : {prompt_text}")
        
        # On enrichit le prompt pour le style 3D / TikTok
        enhanced_prompt = f"{prompt_text}, 3D Pixar style, vibrant colors, highly detailed, cinematic lighting, vertical 9:16 aspect ratio"
        
        # URL de l'API gratuite Pollinations (encodage propre du texte)
        encoded_prompt = requests.utils.quote(enhanced_prompt)
        api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"
        
        try:
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
