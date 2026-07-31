from modules.audio.audio_profiles import AudioProfile

FINANCE_AUDIO_PROFILE = AudioProfile(
    gemini_style_prompt=(
        "French professional financial narrator. Sharp, confident, analytical, "
        "authoritative, professional. Clear diction, steady pacing, objective tone."
    ),
    edge_fallback_voice="fr-FR-HenriNeural",
    edge_fallback_rate="-4%",  # Un poil plus dynamique
    edge_fallback_pitch="+0Hz",
    edge_fallback_volume="+0%",
    kokoro_french_voice="ff_siwis",
    min_scene_duration=3.0,
)