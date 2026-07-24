import os
import requests
from dotenv import load_dotenv

load_dotenv()

class AIImageGenerator:
    def __init__(self):
        # Récupère ta clé Hugging Face (à ajouter dans tes secrets GitHub : HF_TOKEN)
        self.api_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")
        # Modèle rapide et de haute qualité pour du rendu 3D/stylisé moderne
        # self.api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        self.api_url = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
        
        self.headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}

    def generate_image(self, prompt_text, output_path):
        print(f"🎨 Génération d'une image par IA pour : {prompt_text}")
        
        # On enrichit le prompt pour forcer un style visuel ultra moderne / 3D / TikTok
        enhanced_prompt = f"{prompt_text}, 3D Pixar style, vibrant colors, highly detailed, trending on artstation, cinematic lighting, vertical 9:16 aspect ratio"
        
        payload = {
            "inputs": enhanced_prompt,
            "options": {"wait_for_model": True}
        }
        
        try:
            response = requests.post(self.api_url, headers=self.headers, json=payload)
            
            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                print(f"    ✅ Image IA sauvegardée : {output_path}")
                return True
            else:
                print(f"    ❌ Erreur API Hugging Face ({response.status_code}): {response.text}")
                return False
        except Exception as e:
            print(f"    ❌ Erreur de génération d'image : {e}")
            return False
