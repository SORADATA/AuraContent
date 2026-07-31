from modules.visuals.image_profile import ImageProfile


MIMOLUNE_IMAGE_PROFILE = ImageProfile(
    base_style=(
        "cinematic realistic children illustration, gentle lighting, soft textures, "
        "strong central subject, vertical 9:16 composition, clean space near the top and bottom for captions"
    ),
    negative_prompt=(
        "text, logo, watermark, subtitles, deformed hands, extra fingers, duplicate characters, "
        "cropped face, blurry face, horror, gore"
    ),
    default_model="flux"
)