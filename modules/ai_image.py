import os
import time
import hashlib
import random
import requests


class AIImageGenerator:
    BASE_STYLE = (
        "cinematic realistic documentary still, photorealistic, atmospheric depth, "
        "subtle film grain, dramatic but natural lighting, rich natural textures, "
        "high visual clarity, strong central subject, vertical 9:16 composition, "
        "subject kept inside the center safe zone, clean space near the top and bottom for captions"
    )

    NEGATIVE_PROMPT = (
        "text, logo, watermark, subtitles, deformed hands, extra fingers, duplicate people, "
        "cropped head, blurry face, cartoon, anime"
    )

    DEFAULT_MODEL = "flux"

    def __init__(self):
        print("Utilisation du generateur d'images Pollinations.ai (sans token requis)")

    def _stable_seed(self, prompt_text, visual_identity=None, variant="base"):
        raw = f"{prompt_text}|{visual_identity or ''}|{variant}|{self.DEFAULT_MODEL}"
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 999999 + 1

    def _build_prompt(self, prompt_text, visual_identity=None, variant=None):
        fixed_parts = [
            prompt_text.strip().rstrip(",."),
            self.BASE_STYLE
        ]

        if visual_identity:
            fixed_parts.append(f"visual continuity: {visual_identity.strip().rstrip(',.')}")

        if variant == "a":
            fixed_parts.append(
                "wider establishing composition, environment clearly visible, stable cinematic framing"
            )
        elif variant == "b":
            fixed_parts.append(
                "closer cinematic framing, more subject detail, same scene continuity, same visual world"
            )

        fixed_parts.append(f"avoid: {self.NEGATIVE_PROMPT}")
        return ", ".join(fixed_parts)

    def _file_is_valid(self, output_path, min_bytes=5000):
        return os.path.exists(output_path) and os.path.getsize(output_path) >= min_bytes

    def _build_url(self, enhanced_prompt, seed):
        encoded_prompt = requests.utils.quote(enhanced_prompt, safe="")
        return (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width=1080&height=1920"
            f"&seed={seed}"
            f"&model={self.DEFAULT_MODEL}"
            f"&nologo=true&enhance=true"
        )

    def _try_generate(self, prompt_text, output_path, visual_identity=None, seed=None, variant=None):
        enhanced_prompt = self._build_prompt(
            prompt_text,
            visual_identity=visual_identity,
            variant=variant
        )

        if seed is None:
            seed = self._stable_seed(prompt_text, visual_identity=visual_identity, variant=variant or "base")

        api_url = self._build_url(enhanced_prompt, seed)

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

    def generate_image(
        self,
        prompt_text,
        output_path,
        visual_identity=None,
        retries=4,
        seed=None,
        variant=None
    ):
        print(f"Generation d'une image pour : {prompt_text}")

        if self._file_is_valid(output_path):
            print(f"    Image deja presente : {output_path}")
            return True

        base_seed = seed or self._stable_seed(
            prompt_text,
            visual_identity=visual_identity,
            variant=variant or "base"
        )

        for attempt in range(retries + 1):
            if attempt > 0:
                wait_time = min(4 * (2 ** (attempt - 1)) + random.uniform(0, 1.5), 20)
                print(f"    Tentative {attempt + 1}/{retries + 1} (pause {wait_time:.1f}s)...")
                time.sleep(wait_time)

            current_seed = base_seed + attempt

            success = self._try_generate(
                prompt_text=prompt_text,
                output_path=output_path,
                visual_identity=visual_identity,
                seed=current_seed,
                variant=variant,
            )

            if success and self._file_is_valid(output_path):
                print(f"    Image sauvegardee : {output_path} (seed={current_seed})")
                return True

        print(f"    Echec definitif pour : {output_path}")
        return False
