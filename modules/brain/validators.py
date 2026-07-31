import re


ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc). Exemples obligatoires : 'découvert' "
    "(jamais 'decouvert'), 'secrètes' (jamais 'secretes'), 'exploré' "
    "(jamais 'explore'), 'phénomène' (jamais 'phenomene'), 'révélation' "
    "(jamais 'revelation'), 'étrange' (jamais 'etrange'), 'théorie' "
    "(jamais 'theorie'). Verifie chaque mot avant de repondre."
)


def has_missing_accents(text: str, min_hits: int = 3) -> bool:
    suspicious_patterns = [
        r"\bdecouv", r"\bmyster", r"\bsecret", r"\bexplor",
        r"\btheori", r"\bphenomen", r"\bhistoi", r"\bevenem",
        r"\bepoque", r"\betrang", r"\brevel", r"\bdifferen",
        r"\ba ete\b", r"\bpeut etre\b", r"\binteresse",
    ]
    text_lower = text.lower()
    hits = sum(1 for pattern in suspicious_patterns if re.search(pattern, text_lower))
    has_any_accent = any(char in text_lower for char in ACCENTED_CHARS)
    return hits >= min_hits and not has_any_accent


def script_missing_accents(script_data: dict) -> bool:
    scenes = script_data.get("scenes", [])
    if not scenes:
        return False
    full_text = " ".join(scene.get("text", "") for scene in scenes)
    return has_missing_accents(full_text)


def validate_script_payload(data: dict, scene_count: int) -> None:
    scenes = data.get("scenes")

    if not isinstance(scenes, list):
        raise ValueError("La reponse ne contient pas de tableau scenes.")

    if len(scenes) != scene_count:
        raise ValueError(f"Nombre de scenes invalide : {len(scenes)} au lieu de {scene_count}.")

    expected_ids = list(range(1, scene_count + 1))
    actual_ids = [scene.get("id") for scene in scenes]
    if actual_ids != expected_ids:
        raise ValueError(f"IDs de scenes invalides : {actual_ids}")

    allowed_roles = {"hook", "tension", "context", "value", "escalation", "reveal", "cta"}
    allowed_moods = {"ominous", "intriguing", "tense", "awe", "scientific", "melancholic", "revelatory"}

    for scene in scenes:
        text = scene.get("text", "").strip()
        voice_direction = scene.get("voice_direction", "").strip()
        pause_after_ms = scene.get("pause_after_ms")
        emphasis = scene.get("tts_emphasis_word")
        role = scene.get("role")
        mood = scene.get("mood")
        stock_search = scene.get("stock_search", "").strip()
        image_prompt = scene.get("image_prompt", "").strip()

        if not text:
            raise ValueError(f"Scene {scene.get('id')} : text manquant.")
        if not voice_direction:
            raise ValueError(f"Scene {scene.get('id')} : voice_direction manquant.")
        if not isinstance(pause_after_ms, int) or not (180 <= pause_after_ms <= 450):
            raise ValueError(f"Scene {scene.get('id')} : pause_after_ms invalide ({pause_after_ms}).")
        if role not in allowed_roles:
            raise ValueError(f"Scene {scene.get('id')} : role invalide ({role}).")
        if mood not in allowed_moods:
            raise ValueError(f"Scene {scene.get('id')} : mood invalide ({mood}).")
        if not stock_search:
            raise ValueError(f"Scene {scene.get('id')} : stock_search manquant.")
        if not image_prompt:
            raise ValueError(f"Scene {scene.get('id')} : image_prompt manquant.")

        if emphasis:
            normalized_text = text.lower()
            normalized_emphasis = str(emphasis).strip().lower()
            words = re.findall(r"[\wÀ-ÿœŒ'-]+", normalized_text)

            if normalized_emphasis not in words:
                print(
                    f"⚠️ Scene {scene.get('id')} : "
                    f"tts_emphasis_word='{emphasis}' absent du text. Emphase ignorée."
                )
                scene["tts_emphasis_word"] = None

    if "title" not in data or not str(data["title"]).strip():
        raise ValueError("Titre manquant.")
    if "visual_identity" not in data or not str(data["visual_identity"]).strip():
        raise ValueError("visual_identity manquant.")
    if "audio_profile" not in data or not str(data["audio_profile"]).strip():
        raise ValueError("audio_profile manquant.")