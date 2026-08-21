import os
import time
import hashlib
import requests


try:
    from huggingface_hub import InferenceClient
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False


class AIImageGenerator:

    BASE_STYLE = (
        "cinematic realistic documentary still, "
        "photorealistic real-world photography, "
        "natural physical materials, "
        "realistic human anatomy, "
        "subtle 35mm film grain, "
        "documentary cinematography, "
        "atmospheric depth, "
        "natural dramatic lighting, "
        "high micro-detail, "
        "muted desaturated cinematic color palette, "
        "vertical 9:16 composition, "
        "strong readable central subject, "
        "safe composition for mobile captions"
    )

    NEGATIVE_PROMPT = (
        "text, subtitles, captions, logo, watermark, "
        "UI, typography, poster, illustration, cartoon, anime, "
        "3d render, CGI, plastic skin, artificial face, "
        "deformed hands, extra fingers, duplicate people, "
        "cropped head, distorted anatomy, blurry face, "
        "oversaturated colors"
    )

    DEFAULT_MODEL = os.getenv(
        "AI_IMAGE_MODEL",
        "black-forest-labs/FLUX.1-dev"
    )

    HF_MODEL = os.getenv(
        "HF_IMAGE_MODEL",
        "black-forest-labs/FLUX.1-dev"
    )

    def __init__(self):
        self.hf_token = os.getenv("HF_TOKEN")

        contact = os.getenv(
            "WIKIMEDIA_CONTACT",
            "https://github.com/tonuser"
        )

        self.headers = {
            "User-Agent": f"AuraContentPipeline/3.0 ({contact})"
        }

        self.hf_client = None

        if HF_AVAILABLE and self.hf_token:
            try:
                self.hf_client = InferenceClient(
                    api_key=self.hf_token
                )
            except Exception as exc:
                print(
                    f"⚠️ Hugging Face client indisponible: {exc}"
                )

        print(
            "🤖 AI Image Generator V3 initialisé | "
            f"Pollinations={self.DEFAULT_MODEL} | "
            f"HF={self.HF_MODEL}"
        )

    # ---------------------------------------------------------------
    # SEED
    # ---------------------------------------------------------------

    def _stable_seed(
        self,
        prompt_text,
        visual_identity=None,
        variant="base",
        scene_id=None
    ):
        raw = (
            f"{prompt_text}|"
            f"{visual_identity or ''}|"
            f"{variant}|"
            f"{scene_id or ''}"
        )

        digest = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

        return int(digest[:8], 16) % 999999 + 1

    # ---------------------------------------------------------------
    # PROMPT
    # ---------------------------------------------------------------

    def _variant_instruction(self, variant):
        variants = {
            "a": (
                "wide establishing shot, "
                "environment clearly readable, "
                "cinematic spatial depth"
            ),

            "b": (
                "medium cinematic shot, "
                "subject and surrounding evidence visible, "
                "stronger visual storytelling"
            ),

            "c": (
                "tight documentary close-up, "
                "important physical detail, "
                "shallow depth of field"
            ),

            "establishing": (
                "wide establishing composition, "
                "location immediately recognizable"
            ),

            "detail": (
                "close documentary detail shot, "
                "important texture or object emphasized"
            ),

            "evidence": (
                "forensic documentary composition, "
                "physical evidence clearly visible, "
                "realistic investigative atmosphere"
            ),

            "reveal": (
                "dramatic reveal composition, "
                "the important discovery visually dominant"
            ),

            "payoff": (
                "powerful final documentary image, "
                "strong emotional and narrative composition"
            ),
        }

        return variants.get(
            variant,
            variants["b"]
        )

    def _build_prompt(
        self,
        prompt_text,
        visual_identity=None,
        variant=None
    ):
        parts = [
            prompt_text.strip().rstrip(",."),
            self.BASE_STYLE,
        ]

        if visual_identity:
            parts.append(
                "visual continuity: "
                + visual_identity.strip().rstrip(",.")
            )

        if variant:
            parts.append(
                self._variant_instruction(variant)
            )

        parts.append(
            "leave clean visual space near the lower third "
            "for mobile subtitles"
        )

        return ", ".join(parts)

    # ---------------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------------

    def _file_is_valid(
        self,
        output_path,
        min_bytes=5000
    ):
        return (
            os.path.exists(output_path)
            and os.path.getsize(output_path) >= min_bytes
        )

    # ---------------------------------------------------------------
    # POLLINATIONS
    # ---------------------------------------------------------------

    def _build_pollinations_url(
        self,
        enhanced_prompt,
        seed
    ):
        encoded_prompt = requests.utils.quote(
            enhanced_prompt,
            safe=""
        )

        return (
            "https://image.pollinations.ai/prompt/"
            f"{encoded_prompt}"
            "?width=1080"
            "&height=1920"
            f"&seed={seed}"
            f"&model={self.DEFAULT_MODEL}"
            "&nologo=true"
            "&enhance=true"
        )

    def _try_pollinations(
        self,
        prompt_text,
        output_path,
        visual_identity=None,
        seed=None,
        variant=None
    ):
        enhanced_prompt = self._build_prompt(
            prompt_text,
            visual_identity=visual_identity,
            variant=variant
        )

        if seed is None:
            seed = self._stable_seed(
                prompt_text,
                visual_identity,
                variant or "base"
            )

        api_url = self._build_pollinations_url(
            enhanced_prompt,
            seed
        )

        try:
            response = requests.get(
                api_url,
                timeout=60,
                headers=self.headers
            )

            content_type = response.headers.get(
                "Content-Type",
                ""
            )

            if (
                response.status_code == 200
                and content_type.startswith("image/")
                and len(response.content) > 5000
            ):
                os.makedirs(
                    os.path.dirname(output_path) or ".",
                    exist_ok=True
                )

                with open(
                    output_path,
                    "wb"
                ) as file:
                    file.write(response.content)

                return True

            print(
                "    ❌ Pollinations : "
                f"HTTP {response.status_code}"
            )

            return False

        except requests.RequestException as error:
            print(
                f"    ❌ Pollinations réseau : {error}"
            )
            return False

    # ---------------------------------------------------------------
    # HUGGING FACE
    # ---------------------------------------------------------------

    def _try_huggingface(
        self,
        prompt_text,
        output_path,
        visual_identity=None,
        variant=None,
        seed=None
    ):
        if not self.hf_client:
            return False

        prompt = self._build_prompt(
            prompt_text,
            visual_identity=visual_identity,
            variant=variant
        )

        try:
            image = self.hf_client.text_to_image(
                prompt=prompt,
                model=self.HF_MODEL,
                negative_prompt=self.NEGATIVE_PROMPT,
                width=1080,
                height=1920,
                seed=seed or 42,
            )

            image.save(output_path)

            return self._file_is_valid(
                output_path
            )

        except Exception as error:
            print(
                f"    ❌ Hugging Face image error: {error}"
            )
            return False

    # ---------------------------------------------------------------
    # PUBLIC
    # ---------------------------------------------------------------

    def generate_image(
        self,
        prompt_text,
        output_path,
        visual_identity=None,
        retries=2,
        seed=None,
        variant=None,
        scene_id=None
    ):
        print(
            f"🎨 IA image : {prompt_text[:120]}"
        )

        if self._file_is_valid(output_path):
            print(
                f"    ♻️ Image déjà présente : "
                f"{output_path}"
            )
            return True

        base_seed = seed or self._stable_seed(
            prompt_text,
            visual_identity,
            variant or "base",
            scene_id
        )

        for attempt in range(retries + 1):

            if attempt > 0:
                time.sleep(2)

            current_seed = base_seed + attempt

            # -------------------------------------------------------
            # 1. Pollinations
            # -------------------------------------------------------

            success = self._try_pollinations(
                prompt_text,
                output_path,
                visual_identity,
                current_seed,
                variant
            )

            if success and self._file_is_valid(
                output_path
            ):
                print(
                    f"    ✅ Pollinations "
                    f"(seed={current_seed})"
                )
                return True

            # -------------------------------------------------------
            # 2. Hugging Face
            # -------------------------------------------------------

            success = self._try_huggingface(
                prompt_text,
                output_path,
                visual_identity,
                variant,
                current_seed
            )

            if success and self._file_is_valid(
                output_path
            ):
                print(
                    "    ✅ Hugging Face image"
                )
                return True

            if attempt < retries:
                print(
                    "    🔄 Nouvelle tentative..."
                )

        print(
            f"    ❌ Génération impossible : "
            f"{output_path}"
        )

        return False