import os
import requests

class AIImageGenerator:
    def __init__(self):
        print("🎨 Utilisation du generateur d'images Pollinations.ai (Sans token requis)")

    def _try_generate(self, prompt_text, output_path):
        enhanced_prompt = f"{prompt_text}, 3D Pixar style, vibrant colors, highly detailed, cinematic lighting, vertical 9:16 aspect ratio"
        encoded_prompt = requests.utils.quote(enhanced_prompt)
        api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"

        try:
            response = requests.get(api_url, timeout=60)
            if response.status_code == 200 and len(response.content) > 5000:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                return True
            print(f"    ❌ Erreur API Pollinations ({response.status_code})")
            return False
        except Exception as e:
            print(f"    ❌ Erreur de generation d'image : {e}")
            return False

    def generate_image(self, prompt_text, output_path, retries=2):
        print(f"🎨 Generation d'une image pour : {prompt_text}")
        for attempt in range(retries + 1):
            if attempt > 0:
                print(f"    🔁 Tentative {attempt + 1}/{retries + 1}...")
            if self._try_generate(prompt_text, output_path):
                print(f"    ✅ Image IA sauvegardee : {output_path}")
                return True
        return False