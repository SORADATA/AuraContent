from pathlib import Path

from modules.ai_image import AIImageGenerator


class SceneImageService:
    def __init__(self, generator: AIImageGenerator | None = None):
        self.generator = generator or AIImageGenerator()
        self.image_profile = self.generator.image_profile
        self.global_visual_rules = self.image_profile.global_visual_rules

    def compose_prompt(self, base_prompt: str, visual_identity: str | None = None, variant: str = "a") -> str:
        identity_block = f"{visual_identity}. " if visual_identity else ""

        if variant == "a":
            shot_block = self.image_profile.variant_a_suffix
        else:
            shot_block = self.image_profile.variant_b_suffix

        return f"{identity_block}{base_prompt}. {shot_block} {self.global_visual_rules}"

    def generate_with_retry(
        self,
        prompt: str,
        output_path: Path,
        visual_identity: str | None = None,
        retries: int = 2,
    ) -> bool:
        for attempt in range(1, retries + 1):
            try:
                ok = self.generator.generate_image(
                    prompt,
                    str(output_path),
                    visual_identity=visual_identity,
                )
                if ok and output_path.exists() and output_path.stat().st_size > 0:
                    return True
                print(f"      Tentative {attempt}/{retries} échouée pour {output_path.name}")
            except Exception as exc:
                print(f"      Erreur tentative {attempt}/{retries} : {exc}")

        return False