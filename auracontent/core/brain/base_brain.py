from config.settings import (
    GROQ_MODEL,
    OPENROUTER_FALLBACK_MODEL_1,
    OPENROUTER_FALLBACK_MODEL_2
)


class ContentBrain:
    def __init__(self):
        pass

    def _extract_context(self, response):
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            