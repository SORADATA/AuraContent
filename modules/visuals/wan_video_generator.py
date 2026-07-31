import os
from gradio_client import Client, handle_file

SPACES = [
    {"id": "zerogpu-aoti/wan2-2-fp8da-aoti-faster", "extra": {}},
    {"id": "r3gm/wan2-2-fp8da-aoti-preview", "extra": {
        "last_image": None,
        "quality": 6,
        "scheduler": "UniPCMultistep",
        "flow_shift": 3,
        "frame_multiplier": "16",
        "video_component": True,
        "safe_mode": True,
        "enable_safety_checker": True,
    }},
    {"id": "cinderholm/wan2-2-i2v-v3", "extra": {}},
]

NEG_PROMPT = ("色调艳丽, 过曝, 静态, 细节模糊不清, 字幕, 风格, 画面, 静止, "
              "最差质量, 低质量, 丑陋的, 畸形的, 手指融合")


def generate_animated_scene(image_path, prompt, duration=3.5):
    """
    Essaie d'animer une image via plusieurs Spaces Wan 2.2 Lightning (gratuits).
    Retourne le chemin de la vidéo générée, ou None si tous échouent.
    """
    for space in SPACES:
        try:
            client = Client(space["id"], hf_token=os.environ.get("HF_TOKEN"))
            params = dict(
                input_image=handle_file(image_path),
                prompt=prompt,
                steps=6,
                negative_prompt=NEG_PROMPT,
                duration_seconds=duration,
                guidance_scale=1,
                guidance_scale_2=1,
                seed=42,
                randomize_seed=True,
                api_name="/generate_video",
            )
            params.update(space["extra"])
            result = client.predict(**params)
            video_path = result[0] if isinstance(result, (list, tuple)) else result
            if video_path and os.path.exists(video_path):
                return video_path
        except Exception as e:
            print(f"   ⚠️ {space['id']} indisponible ({e}), essai suivant")
            continue

    print("   ❌ Tous les Spaces Wan 2.2 indisponibles.")
    return None