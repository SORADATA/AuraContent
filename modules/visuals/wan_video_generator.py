import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from gradio_client import Client, handle_file


WAN_SPACES = [
    "zerogpu-aoti/wan2-2-fp8da-aoti-faster",
    "r3gm/wan2-2-fp8da-aoti-preview",
    "cinderholm/wan2-2-i2v-v3",
]


def _build_client(space_name, hf_token=None):
    hf_token = hf_token or os.getenv("HF_TOKEN")

    if hf_token:
        try:
            return Client(space_name, token=hf_token)
        except TypeError:
            pass

    return Client(space_name)


def _extract_video_path(result):
    if isinstance(result, str) and result.endswith(".mp4"):
        return result

    if isinstance(result, dict):
        for key in ("video", "value", "path", "url"):
            value = result.get(key)
            if isinstance(value, str) and value.endswith(".mp4"):
                return value

    if isinstance(result, (list, tuple)):
        for item in result:
            path = _extract_video_path(item)
            if path:
                return path

    return None


def _default_output_path(image_path):
    image_path = Path(image_path)
    out_dir = image_path.parent.parent / "animated"
    out_dir.mkdir(parents=True, exist_ok=True)
    return str(out_dir / f"{image_path.stem}_animated.mp4")


def _make_zoompan_fallback(image_path, output_path, duration=4):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf",
        (
            "scale=720:1280:force_original_aspect_ratio=increase,"
            "crop=720:1280,"
            "zoompan=z='min(zoom+0.0008,1.08)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={duration * 25}:s=720x1280:fps=25"
        ),
        "-t", str(duration),
        "-r", "25",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path


def generate_animated_scene(
    image_path,
    scene_prompt,
    output_path=None,
    hf_token=None,
    duration=4,
):
    """
    Génère une scène animée via plusieurs Spaces Wan 2.2.
    Compatible avec les anciens appels qui ne fournissent pas output_path.
    Si aucun Space ne répond, fallback vidéo zoompan à partir de l'image.
    """
    if output_path is None:
        output_path = _default_output_path(image_path)

    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    last_error = None

    for space_name in WAN_SPACES:
        try:
            client = _build_client(space_name, hf_token=hf_token)

            print(f"   🔁 Tentative Wan 2.2 via {space_name}...")

            result = client.predict(
                image=handle_file(str(image_path)),
                prompt=scene_prompt,
                api_name="/predict",
            )

            video_path = _extract_video_path(result)
            if not video_path:
                raise RuntimeError(f"Aucune vidéo exploitable retournée par {space_name}: {result}")

            if video_path.startswith("http://") or video_path.startswith("https://"):
                tmp_dir = tempfile.mkdtemp(prefix="wan_video_")
                tmp_file = os.path.join(tmp_dir, "scene.mp4")
                subprocess.run(
                    ["curl", "-L", video_path, "-o", tmp_file],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                shutil.copy(tmp_file, output_path)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                shutil.copy(video_path, output_path)

            print(f"   ✅ Wan 2.2 OK via {space_name}")
            return output_path

        except Exception as e:
            print(f"   ⚠️ {space_name} indisponible ({e}), essai suivant")
            last_error = e
            time.sleep(1)

    print("   ❌ Tous les Spaces Wan 2.2 indisponibles.")
    print("   ↪️ Fallback zoompan")
    return _make_zoompan_fallback(image_path, output_path, duration=duration)
