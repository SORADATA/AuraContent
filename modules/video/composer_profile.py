from dataclasses import dataclass, field


@dataclass
class ComposerProfile:
    transitions: list[str] = field(default_factory=lambda: ["fade", "diagbr", "diagtl"])
    bg_track_filename: str = "bg_track.mp3"

    video_width: int = 1080
    video_height: int = 1920
    fps: int = 30

    voice_gain: float = 1.15
    music_gain: float = 0.12
    music_fade_duration: float = 1.5
    transition_duration: float = 0.45

    subtitle_style: str = (
        "FontName=Arial Black,"
        "FontSize=18,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H66000000,"
        "BorderStyle=3,"
        "Outline=2.2,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=115"
    )