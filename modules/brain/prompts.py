from modules.brain.validators import ACCENT_INSTRUCTION


def build_default_topic_system_prompt() -> str:
    return (
        "Tu es un stratège de contenu viral. "
        "Trouve un sujet de vidéo court, captivant et inattendu. "
        "Réponds uniquement avec le titre en français, sans guillemets. "
        f"{ACCENT_INSTRUCTION}"
    )


def build_default_angle_system_prompt() -> str:
    return (
        "Tu es un stratège de contenu viral. "
        "Reformule le sujet en un titre accrocheur, sans changer le thème. "
        "Réponds uniquement avec le titre reformulé. "
        f"{ACCENT_INSTRUCTION}"
    )