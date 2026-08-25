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

    # ============================================================
    # CONFIGURATION
    # ============================================================

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

    # ------------------------------------------------------------
    # Pollinations
    # ------------------------------------------------------------

    POLLINATIONS_MODEL = os.getenv(
        "POLLINATIONS_IMAGE_MODEL",
        ""
    )

    POLLINATIONS_TIMEOUT = int(
        os.getenv(
            "POLLINATIONS_TIMEOUT",
            "45"
        )
    )

    # ------------------------------------------------------------
    # Hugging Face
    # ------------------------------------------------------------

    HF_MODEL = os.getenv(
        "HF_IMAGE_MODEL",
        "black-forest-labs/FLUX.1-dev"
    )

    HF_TIMEOUT = int(
        os.getenv(
            "HF_IMAGE_TIMEOUT",
            "120"
        )
    )

    # ------------------------------------------------------------
    # Image dimensions
    # ------------------------------------------------------------

    IMAGE_WIDTH = int(
        os.getenv(
            "AI_IMAGE_WIDTH",
            "1080"
        )
    )

    IMAGE_HEIGHT = int(
        os.getenv(
            "AI_IMAGE_HEIGHT",
            "1920"
        )
    )

    # ============================================================
    # INIT
    # ============================================================

    def __init__(self):

        self.hf_token = os.getenv("HF_TOKEN")

        contact = os.getenv(
            "WIKIMEDIA_CONTACT",
            "https://github.com/tonuser"
        )

        self.headers = {
            "User-Agent": (
                f"AuraContentPipeline/3.0 ({contact})"
            )
        }

        self.hf_client = None

        if HF_AVAILABLE and self.hf_token:

            try:
                self.hf_client = InferenceClient(
                    api_key=self.hf_token
                )

            except Exception as exc:

                print(
                    f"⚠️ Hugging Face client indisponible : "
                    f"{exc}"
                )

        print(
            "🤖 AI Image Generator V4 initialisé | "
            f"Pollinations="
            f"{self.POLLINATIONS_MODEL or 'défaut'} | "
            f"HF={self.HF_MODEL} | "
            f"{self.IMAGE_WIDTH}x{self.IMAGE_HEIGHT}"
        )

    # ============================================================
    # SEED
    # ============================================================

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

        return (
            int(digest[:8], 16) % 999999
        ) + 1

    # ============================================================
    # PROMPT
    # ============================================================

    def _variant_instruction(
        self,
        variant
    ):

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

    # ============================================================
    # BUILD PROMPT
    # ============================================================

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
                self._variant_instruction(
                    variant
                )
            )

        parts.append(
            "leave clean visual space near the lower third "
            "for mobile subtitles"
        )

        return ", ".join(parts)

    # ============================================================
    # VALIDATION
    # ============================================================

    def _file_is_valid(
        self,
        output_path,
        min_bytes=5000
    ):

        try:

            return (
                os.path.isfile(output_path)
                and os.path.getsize(output_path)
                >= min_bytes
            )

        except OSError:

            return False

    # ============================================================
    # POLLINATIONS URL
    # ============================================================

    def _build_pollinations_url(
        self,
        enhanced_prompt,
        seed
    ):

        encoded_prompt = requests.utils.quote(
            enhanced_prompt,
            safe=""
        )

        url = (
            "https://image.pollinations.ai/prompt/"
            f"{encoded_prompt}"
            f"?width={self.IMAGE_WIDTH}"
            f"&height={self.IMAGE_HEIGHT}"
            f"&seed={seed}"
            "&nologo=true"
        )

        # IMPORTANT :
        # On n'impose plus FLUX.1-dev par défaut.
        # On ajoute le modèle uniquement s'il est explicitement
        # configuré.

        if self.POLLINATIONS_MODEL:

            url += (
                "&model="
                + requests.utils.quote(
                    self.POLLINATIONS_MODEL,
                    safe=""
                )
            )

        return url

    # ============================================================
    # POLLINATIONS
    # ============================================================

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

        print(
            f"    🟣 Pollinations "
            f"(seed={seed})..."
        )

        temporary_path = (
            output_path + ".part"
        )

        try:

            response = requests.get(
                api_url,
                timeout=self.POLLINATIONS_TIMEOUT,
                headers=self.headers,
                stream=True
            )

            print(
                f"    🟣 Pollinations HTTP "
                f"{response.status_code}"
            )

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
            )

            if (
                response.status_code != 200
                or not content_type.startswith("image/")
            ):

                print(
                    "    ❌ Pollinations réponse invalide : "
                    f"{content_type}"
                )

                return False

            os.makedirs(
                os.path.dirname(
                    output_path
                ) or ".",
                exist_ok=True
            )

            total_bytes = 0

            with open(
                temporary_path,
                "wb"
            ) as file:

                for chunk in response.iter_content(
                    chunk_size=1024 * 64
                ):

                    if chunk:

                        file.write(chunk)
                        total_bytes += len(chunk)

            if total_bytes < 5000:

                print(
                    f"    ❌ Image trop petite : "
                    f"{total_bytes} octets"
                )

                try:
                    os.remove(
                        temporary_path
                    )
                except OSError:
                    pass

                return False

            os.replace(
                temporary_path,
                output_path
            )

            print(
                f"    ✅ Pollinations image reçue "
                f"({total_bytes / 1024:.0f} Ko)"
            )

            return self._file_is_valid(
                output_path
            )

        except requests.Timeout:

            print(
                "    ⏱️ Pollinations timeout "
                f"({self.POLLINATIONS_TIMEOUT}s)"
            )

            return False

        except requests.RequestException as error:

            print(
                f"    ❌ Pollinations réseau : "
                f"{error}"
            )

            return False

        except Exception as error:

            print(
                f"    ❌ Pollinations erreur : "
                f"{error}"
            )

            return False

        finally:

            if os.path.exists(
                temporary_path
            ):

                try:
                    os.remove(
                        temporary_path
                    )
                except OSError:
                    pass

    # ============================================================
    # HUGGING FACE
    # ============================================================

    def _try_huggingface(
        self,
        prompt_text,
        output_path,
        visual_identity=None,
        variant=None,
        seed=None
    ):

        if not self.hf_client:

            print(
                "    ⚠️ Hugging Face non configuré"
            )

            return False

        prompt = self._build_prompt(
            prompt_text,
            visual_identity=visual_identity,
            variant=variant
        )

        print(
            f"    🟢 Hugging Face "
            f"({self.HF_MODEL})..."
        )

        try:

            image = self.hf_client.text_to_image(
                prompt=prompt,
                model=self.HF_MODEL,
                negative_prompt=self.NEGATIVE_PROMPT,
                width=self.IMAGE_WIDTH,
                height=self.IMAGE_HEIGHT,
                seed=seed or 42,
            )

            os.makedirs(
                os.path.dirname(
                    output_path
                ) or ".",
                exist_ok=True
            )

            image.save(
                output_path
            )

            if self._file_is_valid(
                output_path
            ):

                print(
                    "    ✅ Hugging Face image générée"
                )

                return True

            print(
                "    ❌ Hugging Face fichier invalide"
            )

            return False

        except Exception as error:

            print(
                f"    ❌ Hugging Face image error : "
                f"{error}"
            )

            return False

    # ============================================================
    # PUBLIC
    # ============================================================

    def generate_image(
        self,
        prompt_text,
        output_path,
        visual_identity=None,
        retries=1,
        seed=None,
        variant=None,
        scene_id=None
    ):

        print(
            f"\n🎨 IA image "
            f"scene={scene_id or '?'} : "
            f"{prompt_text[:120]}"
        )

        # --------------------------------------------------------
        # CACHE
        # --------------------------------------------------------

        if self._file_is_valid(
            output_path
        ):

            print(
                f"    ♻️ Image déjà présente : "
                f"{output_path}"
            )

            return True

        # --------------------------------------------------------
        # SEED STABLE
        # --------------------------------------------------------

        base_seed = seed or self._stable_seed(
            prompt_text,
            visual_identity,
            variant or "base",
            scene_id
        )

        # --------------------------------------------------------
        # RETRIES
        # --------------------------------------------------------

        for attempt in range(
            retries + 1
        ):

            current_seed = (
                base_seed + attempt
            )

            print(
                f"    🔁 Tentative "
                f"{attempt + 1}/{retries + 1} "
                f"(seed={current_seed})"
            )

            # ====================================================
            # 1. POLLINATIONS
            # ====================================================

            success = self._try_pollinations(
                prompt_text,
                output_path,
                visual_identity,
                current_seed,
                variant
            )

            if (
                success
                and self._file_is_valid(
                    output_path
                )
            ):

                print(
                    "    ✅ Image finale = Pollinations"
                )

                return True

            # ====================================================
            # 2. HUGGING FACE
            # ====================================================

            success = self._try_huggingface(
                prompt_text,
                output_path,
                visual_identity,
                variant,
                current_seed
            )

            if (
                success
                and self._file_is_valid(
                    output_path
                )
            ):

                print(
                    "    ✅ Image finale = Hugging Face"
                )

                return True

            # ====================================================
            # RETRY
            # ====================================================

            if attempt < retries:

                print(
                    "    ⏳ Nouvelle tentative dans 2s..."
                )

                time.sleep(2)

        print(
            f"    ❌ Génération impossible : "
            f"{output_path}"
        )

        return False
