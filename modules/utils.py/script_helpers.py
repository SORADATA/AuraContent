def estimate_scene_count(duration_target: int) -> int:
    return max(6, min(14, round(duration_target / 5)))


def validate_script_payload(script_payload: dict) -> bool:
    if not isinstance(script_payload, dict):
        raise ValueError("script_payload doit etre un dict.")

    scenes = script_payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("script_payload['scenes'] est vide ou invalide.")

    for scene in scenes:
        if "id" not in scene or "text" not in scene or "image_prompt" not in scene:
            raise ValueError(f"Scene invalide : {scene}")

    return True