from dataclasses import dataclass


@dataclass
class ImageProfile:
    base_style: str = (
        "cinematic realistic documentary still, photorealistic, atmospheric depth, "
        "subtle film grain, dramatic but natural lighting, rich natural textures, "
        "high visual clarity, strong central subject, vertical 9:16 composition, "
        "subject kept inside the center safe zone, clean space near the top and bottom for captions"
    )

    negative_prompt: str = (
        "text, logo, watermark, subtitles, deformed hands, extra fingers, duplicate people, "
        "cropped head, blurry face, cartoon, anime"
    )

    default_model: str = "flux"

    width: int = 1080
    height: int = 1920
    request_timeout: int = 120
    min_file_size_bytes: int = 5000
    default_retries: int = 4
    user_agent: str = "TikTokMysteryGenerator/1.0"

    add_nologo: bool = True
    add_enhance: bool = True

    visual_continuity_label: str = "visual continuity"

    variant_a_suffix: str = (
        "wider establishing composition, environment clearly visible, stable cinematic framing"
    )

    variant_b_suffix: str = (
        "closer cinematic framing, more subject detail, same scene continuity, same visual world"
    )

    global_visual_rules: str = (
        "Vertical 9:16 frame, strong central subject, clean composition, natural anatomy, "
        "no text, no logo, no watermark, no interface, no subtitles, "
        "space preserved at top and bottom for captions."
    )