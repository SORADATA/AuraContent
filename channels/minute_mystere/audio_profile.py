from modules.audio.audio_profiles import AudioProfile


MINUTE_MYSTERE_AUDIO_PROFILE = AudioProfile(
    gemini_style_prompt=(
        "French professional narrator. Calm, elegant, warm, premium, natural. "
        "Clear diction, slightly deep tone, controlled pacing, short pauses, "
        "cinematic but not theatrical."
    ),
    edge_fallback_voice="fr-FR-HenriNeural",
    edge_fallback_rate="-8%",
    edge_fallback_pitch="-1Hz",
    edge_fallback_volume="+0%",
    kokoro_french_voice="ff_siwis",
    min_scene_duration=3.0,
)