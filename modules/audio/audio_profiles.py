from dataclasses import dataclass


@dataclass
class AudioProfile:
    gemini_model: str = "gemini-2.5-flash-preview-tts"
    gemini_style_prompt: str = (
        "French professional narrator. Calm, elegant, warm, premium, natural. "
        "Clear diction, slightly deep tone, controlled pacing, short pauses, "
        "cinematic but not theatrical."
    )

    edge_fallback_voice: str = "fr-FR-HenriNeural"
    edge_fallback_rate: str = "-8%"
    edge_fallback_pitch: str = "-1Hz"
    edge_fallback_volume: str = "+0%"

    kokoro_french_voice: str = "ff_siwis"

    min_scene_duration: float = 3.0