from modules.audio.audio_profiles import AudioProfile


MIMOLUNE_AUDIO_PROFILE = AudioProfile(
    gemini_style_prompt=(
        "French children storyteller. Gentle, warm, reassuring, expressive, natural. "
        "Clear diction, soft pacing, tender pauses, musical and comforting."
    ),
    edge_fallback_voice="fr-FR-DeniseNeural",
    edge_fallback_rate="-4%",
    edge_fallback_pitch="+2Hz",
    edge_fallback_volume="+0%",
    kokoro_french_voice="ff_siwis",
    min_scene_duration=3.0,
)