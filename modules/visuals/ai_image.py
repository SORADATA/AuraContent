import os
import time
import hashlib
import random
import requests

from modules.visuals.image_profile import ImageProfile


class AIImageGenerator:
    def __init__(self, image_profile=None):
        self.image_profile = image_profile or ImageProfile()

        self.BASE_STYLE = self.image_profile.base_style
        self.NEGATIVE_PROMPT = self.image_profile.negative_prompt
        self.DEFAULT_MODEL = self.image_profile.default_model

        self.WIDTH = self.image_profile.width
        self.HEIGHT = self.image_profile.height
        self.REQUEST_TIMEOUT = self.image_profile.request_timeout
        self.MIN_FILE_SIZE_BYTES = self.image_profile.min_file_size_bytes
        self.DEFAULT_RETRIES = self.image_profile.default_retries
        self.USER_AGENT = self.image_profile.user_agent

        self.ADD_NOLOGO = self.image_profile.add_nologo
        self.ADD_ENHANCE = self.image_profile.add_enhance

        self.VISUAL_CONTINUITY_LABEL = self.image_profile.visual_continuity_label
        self.VARIANT_A_SUFFIX = self.image_profile.variant_a_suffix
        self.VARIANT_B_SUFFIX = self.image_profile.variant_b_suffix

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
            fixed_parts.append(
                f"{self.VISUAL_CONTINUITY_LABEL}: {visual_identity.strip().rstrip(',.')}"
            )

        if variant == "a":
            fixed_parts.append(self.VARIANT_A_SUFFIX)
        elif variant == "b":
            fixed_parts.append(self.VARIANT_B_SUFFIX)

        fixed_parts.append(f"avoid: {self.NEGATIVE_PROMPT}")
        return ", ".join(fixed_parts)

    def _file_is_valid(self, output_path, min_bytes=None):
        min_bytes = min_bytes or self.MIN_FILE_SIZE_BYTES
        return os.path.exists(output_path) and os.path.getsize(output_path) >= min_bytes

    def _build_url(self, enhanced_prompt, seed):
        encoded_prompt = requests.utils.quote(enhanced_prompt, safe="")

        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={self.WIDTH}&height={self.HEIGHT}"
            f"&seed={seed}"
            f"&model={self.DEFAULT_MODEL}"
        )

        if self.ADD_NOLOGO:
            url += "&nologo=true"

        if self.ADD_ENHANCE:
            url += "&enhance=true"

        return url

    def _try_generate(self, prompt_text, output_path, visual_identity=None, seed=None, variant=None):
        enhanced_prompt = self._build_prompt(
            prompt_text,
            visual_identity=visual_identity,
            variant=variant
        )

        if seed is None:
            seed = self._stable_seed(
                prompt_text,
                visual_identity=visual_identity,
                variant=variant or "base"
            )

        api_url = self._build_url(enhanced_prompt, seed)

        try:
            response = requests.get(
                api_url,
                timeout=self.REQUEST_TIMEOUT,
                headers={"User-Agent": self.USER_AGENT},
            )

            content_type = response.headers.get("Content-Type", "")

            if (
                response.status_code == 200
                and content_type.startswith("image/")
                and len(response.content) > self.MIN_FILE_SIZE_BYTES
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
        retries=None,
        seed=None,
        variant=None
    ):
        print(f"Generation d'une image pour : {prompt_text}")

        retries = self.DEFAULT_RETRIES if retries is None else retries

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