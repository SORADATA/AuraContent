
import os
import time
import random
import requests


class AIImageGenerator:
    BASE_STYLE = (
        "cinematic realistic mystery documentary still, "
        "photorealistic, atmospheric depth, subtle film grain, "
        "dramatic volumetric lighting, rich natural textures, "
        "high contrast, visually clear central subject, "
        "vertical composition, subject inside the center safe zone, "
        "clean space near the top and bottom for captions"
    )

    NEGATIVE_PROMPT = (
        "text, letters, numbers, subtitles, captions, logo, watermark, "
        "signature, interface, collage, split screen, border, frame, "
        "low resolution, blurry subject, oversaturated colors, "
        "deformed face, malformed hands, extra fingers, duplicate people, "
        "cropped head, gore, cartoon, Pixar, Disney, anime"
    )

    def __init__(self):
        print("Utilisation du generateur d'images Pollinations.ai (sans token requis)")

    def _build_prompt(self, prompt_text, visual_identity=None):
        parts = [prompt_text.strip().rstrip(","), self.BASE_STYLE]
        if visual_identity:
            parts.append(f"visual continuity: {visual_identity.strip().rstrip(',')}")
        parts.append(f"avoid: {self.NEGATIVE_PROMPT}")
        return ", ".join(parts)

    def _try_generate(self, prompt_text, output_path, visual_identity=None, seed=None):
        enhanced_prompt = self._build_prompt(prompt_text, visual_identity=visual_identity)
        encoded_prompt = requests.utils.quote(enhanced_prompt, safe="")

        if seed is None:
            seed = random.randint(1, 999999)

        api_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1080&height=1920&nologo=true&seed={seed}&enhance=true"
        )

        try:
            response = requests.get(
                api_url,
                timeout=120,
                headers={"User-Agent": "TikTokMysteryGenerator/1.0"},
            )

            content_type = response.headers.get("Content-Type", "")

            if (
                response.status_code == 200
                and content_type.startswith("image/")
                and len(response.content) > 5000
            ):
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as file:
                    file.write(response.content)
                return True

            if response.status_code == 429:
                print("    Limite de requetes atteinte.")
            else:
                print(f"    Erreur Pollinations : {response.status_code}, type={content_type}")

            return False

        except requests.RequestException as error:
            print(f"    Erreur reseau : {error}")
            return False

    def generate_image(self, prompt_text, output_path, visual_identity=None, retries=4):
        print(f"Generation d'une image pour : {prompt_text}")

        for attempt in range(retries + 1):
            if attempt > 0:
                wait_time = min(5 * (2 ** (attempt - 1)) + random.uniform(0, 2), 30)
                print(f"    Tentative {attempt + 1}/{retries + 1} (pause {wait_time:.1f}s)...")
                time.sleep(wait_time)

            success = self._try_generate(
                prompt_text=prompt_text,
                output_path=output_path,
                visual_identity=visual_identity,
                seed=random.randint(1, 999999),
            )

            if success:
                print(f"    Image sauvegardee : {output_path}")
                return True

        print(f"    Echec definitif pour : {output_path}")
        return False

