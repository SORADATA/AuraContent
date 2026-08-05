import os
import time
import requests
from PIL import Image, ImageDraw, ImageFont



class AIImageGenerator:
    def __init__(self):
        self.pollinations_url = "https://image.pollinations.ai/prompt/"
        self.hf_token = os.getenv("HF_TOKEN")
        self.hf_model_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

    def _save_text_fallback(self, prompt, output_path):
        img = Image.new("RGB", (1080, 1920), (15, 15, 18))
        draw = ImageDraw.Draw(img)
        text = "Fallback image\n\n" + prompt[:180]

        try:
            font = ImageFont.truetype("arial.ttf", 42)
        except Exception:
            font = ImageFont.load_default()

        draw.multiline_text((80, 120), text, fill="white", font=font, spacing=14)
        img.save(output_path)
        return True

    def _pollinations(self, prompt, output_path):
        url = self.pollinations_url + requests.utils.quote(prompt)
        r = requests.get(url, timeout=90)
        if r.status_code == 429:
            raise RuntimeError("429 Too Many Requests")
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)
        return True

    def _huggingface(self, prompt, output_path):
        if not self.hf_token:
            return False

        headers = {
            "Authorization": f"Bearer {self.hf_token}",
            "Content-Type": "application/json",
        }
        payload = {"inputs": prompt}

        r = requests.post(
            self.hf_model_url,
            headers=headers,
            json=payload,
            timeout=120,
        )

        if r.status_code == 503:
            raise RuntimeError("HF model loading")
        r.raise_for_status()

        if "application/json" in r.headers.get("Content-Type", ""):
            data = r.json()
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(data["error"])
            return False

        with open(output_path, "wb") as f:
            f.write(r.content)
        return True

    def generate_image(self, prompt, output_path, visual_identity=None):
        full_prompt = f"{visual_identity}. {prompt}" if visual_identity else prompt

        for attempt in range(1, 4):
            try:
                if self._pollinations(full_prompt, output_path):
                    return True
            except Exception as e:
                print(f"⚠️ Pollinations échec tentative {attempt}/3: {e}")
                time.sleep(min(2 ** attempt, 10))

                try:
                    if self._huggingface(full_prompt, output_path):
                        print("✅ Hugging Face Inference API utilisée")
                        return True
                except Exception as hf_e:
                    print(f"⚠️ Hugging Face échec: {hf_e}")
                    time.sleep(2)

        print("⚠️ Fallback texte utilisé")
        return self._save_text_fallback(full_prompt, output_path)