from modules.visuals.image_profile import ImageProfile


FINANCE_IMAGE_PROFILE = ImageProfile(
    base_style=(
        "bright modern economics and finance editorial still, clean professional composition, "
        "realistic business and institutional environments, high clarity, soft natural daylight, "
        "neutral bright tones, white and light gray surfaces, subtle blue and teal accents, "
        "clear analytical visual hierarchy, polished financial media aesthetic, "
        "credible economy-focused storytelling, vertical 9:16 composition, "
        "subject kept inside the center safe zone, clean space near the top and bottom for captions"
    ),
    negative_prompt=(
        "dark scene, moody lighting, noir, thriller, horror, mystery, conspiracy aesthetic, "
        "neon cyberpunk, dramatic darkness, grunge, text, logo, watermark, subtitles, "
        "deformed hands, extra fingers, duplicate people, cropped head, blurry face, cartoon, anime"
    ),
    default_model="flux",
    global_visual_rules=(
        "Vertical 9:16 editorial frame, bright clean composition, readable subject, "
        "professional economy and finance atmosphere, no text, no logo, no watermark, "
        "no interface, no subtitles, space preserved at top and bottom for captions."
    ),
    variant_a_suffix=(
        "Establishing shot, wider composition, clear economic or business context, "
        "subject readable instantly, stable professional framing."
    ),
    variant_b_suffix=(
        "Closer editorial shot, tighter framing, more analytical or human detail, "
        "same subject and same scene continuity."
    ),
)