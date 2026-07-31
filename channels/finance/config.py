# channels/minute_mystere/config.py
from modules.brain.models import BrainChannelConfig
from channels.minute_mystere.prompts.script_prompt import build_script_prompt
# importe tes autres builders...

minute_mystere_config = BrainChannelConfig(
    name="minute_mystere",
    default_scene_count=10,
    providers_order=("groq", "gemini"),
    script_prompt_builder=build_script_prompt, # Injection directe de la fonction !
    # hook_prompt_builder=build_hook_prompt,
)

FINANCE_HF_REPO = "https://huggingface.co/datasets/soradata/ai_videos_Finance"