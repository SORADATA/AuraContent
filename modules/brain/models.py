from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class BrainChannelConfig:
    name: str
    default_scene_count: int = 11
    providers_order: tuple[str, ...] = ("groq", "gemini")
    strict_accents: bool = True

    topic_system_prompt: str = ""
    topic_user_prompt: str = ""
    angle_system_prompt: str = ""

    hook_prompt_builder: Optional[Callable[[str, int], str]] = None
    script_prompt_builder: Optional[Callable[[str, int, Optional[str]], str]] = None