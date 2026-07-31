<<<<<<< HEAD
import argparse
import asyncio
import os
from pathlib import Path
=======
import asyncio
import os
import shutil
import math
from datetime import datetime
from huggingface_hub import HfApi
>>>>>>> Main

from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer

from modules.utils.huggingface import upload_to_huggingface
from modules.utils.filesystem import clean_cache
from modules.utils.subtitles import generate_grouped_srt
from modules.utils.script_helpers import estimate_scene_count, validate_script_payload

<<<<<<< HEAD
from channels.minute_mystere.config import minute_mystere_brain_config
from channels.finance.config import finance_brain_config

CHANNELS_REGISTRY = {
    "minute_mystere": {
        "brain": minute_mystere_brain_config,
        "dir": Path("channels/minute_mystere"),
        "hf_repo": "soradata/minute-mystere-videos"
    },
    "finance": {
        "brain": finance_brain_config,
        "dir": Path("channels/finance"),
        "hf_repo": "soradata/finance-videos"
    }
}


async def generate_video(channel_name: str):
    print(f"🚀 STARTING AUTOMATION FOR: {channel_name.upper()}")

    if channel_name not in CHANNELS_REGISTRY:
        print(f"❌ Erreur : La chaîne '{channel_name}' n'existe pas dans le registre.")
        return

    channel_config = CHANNELS_REGISTRY[channel_name]
    channel_dir = channel_config["dir"]
=======
def upload_to_huggingface(video_path, topic):
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("Upload HF ignore : token manquant.")
        return False

    if not video_path or not os.path.exists(video_path):
        print("Upload HF ignore : fichier video introuvable.")
        return False

    api = HfApi(token=hf_token)
    repo_id = os.getenv("HF_REPO_ID", "soradata/AIShortvideos")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() else "_" for c in topic)[:50]
    remote_filename = f"videos/{timestamp}_{safe_topic}.mp4"

    try:
        api.upload_file(
            path_or_fileobj=video_path,
            path_in_repo=remote_filename,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Add generated short: {safe_topic}"
        )
        print(f"✅ Video uploadee sur Hugging Face : {repo_id}/{remote_filename}")
        return True
    except Exception as e:
        print(f"❌ Echec upload Hugging Face : {e}")
        return False


def clean_cache():
    print("🧹 Cleaning up temporary files...")

    folders_to_clean = [
        os.path.join(os.getcwd(), "assets", "audio_clips"),
        os.path.join(os.getcwd(), "assets", "video_clips"),
        os.path.join(os.getcwd(), "assets", "temp"),
    ]

    for folder in folders_to_clean:
        if not os.path.exists(folder):
            continue

        normalized = os.path.abspath(folder)
        cwd = os.path.abspath(os.getcwd())

        if not normalized.startswith(os.path.join(cwd, "assets")):
            print(f"    SECURITY ALERT: Skipping unsafe path {folder}")
            continue

        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"    Failed to delete {file_path}. Reason: {e}")

    print("✅ Workspace clean!")


def format_srt_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def chunk_words_for_subtitles(words, max_words=3):
    chunks = []
    current = []

    for word in words:
        current.append(word)
        if len(current) >= max_words:
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)

    return chunks


def generate_grouped_srt(text, duration, output_path, max_words_per_caption=3, min_caption_dur=0.45):
    words = text.split()
    if not words:
        return None

    chunks = chunk_words_for_subtitles(words, max_words=max_words_per_caption)
    total_words = len(words)
    cursor = 0.0
    lines = []

    for idx, chunk in enumerate(chunks, start=1):
        proportion = len(chunk) / total_words
        seg_duration = max(duration * proportion, min_caption_dur)

        start = cursor
        end = min(start + seg_duration, duration)
        cursor = end

        caption_text = " ".join(chunk)
        lines.append(f"{idx}\n{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n{caption_text}\n")

    if lines:
        last_block = lines[-1].split("\n")
        if len(last_block) >= 3:
            start_line = last_block[1].split(" --> ")[0]
            lines[-1] = f"{len(lines)}\n{start_line} --> {format_srt_timestamp(duration)}\n{last_block[2]}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def estimate_scene_count(duration_target):
    return max(6, min(14, round(duration_target / 5)))


def validate_script_payload(script_payload):
    if not isinstance(script_payload, dict):
        raise ValueError("script_payload doit etre un dict.")

    scenes = script_payload.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("script_payload['scenes'] est vide ou invalide.")

    for scene in scenes:
        if "id" not in scene or "text" not in scene or "image_prompt" not in scene:
            raise ValueError(f"Scene invalide : {scene}")

    return True


async def main():
    print("🚀 STARTING AUTOMATION...")
>>>>>>> Main

    topic_input = os.getenv("VIDEO_TOPIC", "").strip()
    duration_target = int(os.getenv("VIDEO_DURATION", "45"))
    refine_angle = os.getenv("REFINE_ANGLE", "true").lower() == "true"
    use_hooks_ab_test = os.getenv("USE_HOOK_VARIANTS", "true").lower() == "true"

<<<<<<< HEAD
    brain = ContentBrain(channel_config=channel_config["brain"])
=======
    brain = ContentBrain()
>>>>>>> Main

    try:
        if topic_input:
            topic = topic_input
            print(f"📌 Sujet fourni manuellement : {topic}")
            if refine_angle:
                topic = brain.refine_topic_angle(topic)
                print(f"🎯 Angle affine : {topic}")
        else:
            topic = brain.get_trending_topic()
            print(f"🔥 Sujet selectionne automatiquement : {topic}")

        chosen_hook = None
        if use_hooks_ab_test:
            try:
                hooks = brain.generate_hook_variants(topic, n=5)
                chosen_hook = hooks[0]["text"]
                print(f"🧠 Hook retenu ({hooks[0]['pattern']}): {chosen_hook}")
            except Exception as e:
                print(f"⚠️ Generation des hooks alternatifs echouee : {e}")

        scene_count = estimate_scene_count(duration_target)
        print(f"⏱️ Duree cible: {duration_target}s -> {scene_count} scenes")

        script_payload = brain.generate_script_with_target(
            topic,
            scene_count,
            chosen_hook=chosen_hook
        )

        validate_script_payload(script_payload)

        script = script_payload["scenes"]
        visual_identity = script_payload.get("visual_identity")
        video_title = script_payload.get("title", topic)

    except Exception as e:
        print(f"❌ Brain Error: {e}")
        return

    if not script:
        print("❌ Script generation failed.")
        return

    audio_engine = AudioEngine()

    try:
        print("🎙️ Generation audio...")
        script = await audio_engine.process_script(script)
    except Exception as e:
        print(f"❌ Audio Error: {e}")
        return

    subs_dir = channel_dir / "assets" / "temp" / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    print("📝 Generation des sous-titres...")
    for scene in script:
<<<<<<< HEAD
        srt_path = str(subs_dir / f"scene_{scene['id']}.srt")
=======
        srt_path = os.path.join(subs_dir, f"scene_{scene['id']}.srt")
>>>>>>> Main
        result = generate_grouped_srt(
            text=scene["text"],
            duration=scene["duration"],
            output_path=srt_path,
            max_words_per_caption=3,
            min_caption_dur=0.45
        )
        scene["srt_path"] = result

    try:
        print("🖼️ Generation des assets visuels...")
        asset_manager = AssetManager()
        assets_map = asset_manager.get_videos(script, visual_identity=visual_identity)
    except Exception as e:
        print(f"❌ Asset Error: {e}")
        return

    try:
        print("🎞️ Composition video...")
<<<<<<< HEAD
        composer = Composer(root_dir=channel_dir)
=======
        composer = Composer()
>>>>>>> Main
        final_scene_paths = composer.render_all_scenes(script, assets_map)
    except Exception as e:
        print(f"❌ Render Error: {e}")
        return

    if not final_scene_paths:
        print("❌ Failed to generate any scenes.")
        return

    try:
        final_path = composer.concatenate_with_transitions(final_scene_paths)
    except Exception as e:
        print(f"❌ Final assembly error: {e}")
        return

    if final_path:
        print(f"✅ Video finale prete : {final_path}")
<<<<<<< HEAD
        upload_to_huggingface(
            video_path=final_path, 
            topic=video_title, 
            repo_id=channel_config["hf_repo"]
        )
=======
        upload_to_huggingface(final_path, video_title)
>>>>>>> Main
        clean_cache()
    else:
        print("❌ L'assemblage final a echoue, upload annule.")


if __name__ == "__main__":
<<<<<<< HEAD
    parser = argparse.ArgumentParser(description="Générateur de Shorts Multi-Chaînes")
    parser.add_argument("--channel", type=str, required=True, help="Nom de la chaîne (ex: minute_mystere, finance)")
    args = parser.parse_args()

    asyncio.run(generate_video(args.channel))
=======
    asyncio.run(main())
>>>>>>> Main
