import asyncio
import os
import shutil
from datetime import datetime
from huggingface_hub import HfApi
from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer


def upload_to_huggingface(video_path, topic):
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token or not video_path or not os.path.exists(video_path):
        print("⚠️ Upload HF ignoré (token manquant ou fichier introuvable)")
        return

    api = HfApi(token=hf_token)
    repo_id = "soradata/AIShortvideos"

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() else "_" for c in topic)[:50]
    remote_filename = f"videos/{timestamp}_{safe_topic}.mp4"

    try:
        api.upload_file(
            path_or_fileobj=video_path,
            path_in_repo=remote_filename,
            repo_id=repo_id,
            repo_type="dataset",
        )
        print(f"✅ Video uploadee sur Hugging Face : {repo_id}/{remote_filename}")
    except Exception as e:
        print(f"❌ Echec upload Hugging Face : {e}")


def clean_cache():
    print("🧹 Cleaning up temporary files...")

    folders_to_clean = [
        os.path.join(os.getcwd(), "assets", "audio_clips"),
        os.path.join(os.getcwd(), "assets", "video_clips"),
        os.path.join(os.getcwd(), "assets", "temp")
    ]

    for folder in folders_to_clean:
        if not os.path.exists(folder):
            continue

        if "assets" not in folder:
            print(f"    🚨 SECURITY ALERT: Skipping {folder} because it looks unsafe!")
            continue

        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                    print(f"        Deleted: {filename}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"    ❌ Failed to delete {file_path}. Reason: {e}")

    print("✨ Workspace clean!")


def generate_word_by_word_srt(text, duration, output_path):
    words = text.split()
    if not words:
        return None

    per_word = duration / len(words)
    lines = []
    for i, word in enumerate(words):
        start = i * per_word
        end = start + per_word

        def fmt(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = t % 60
            return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

        lines.append(f"{i + 1}\n{fmt(start)} --> {fmt(end)}\n{word}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


async def main():
    print("🚀 STARTING AUTOMATION...")

    brain = ContentBrain()
    try:
        topic = brain.get_trending_topic()
        print(f"🎯 Sujet selectionne : {topic}")
        script = brain.generate_script(topic)
    except Exception as e:
        print(f"❌ Brain Error: {e}")
        return

    if not script:
        print("❌ Script generation failed.")
        return

    audio_engine = AudioEngine()
    try:
        script = await audio_engine.process_script(script)
    except Exception as e:
        print(f"❌ Audio Error: {e}")
        return

    subs_dir = os.path.join(os.getcwd(), "assets", "temp", "subs")
    os.makedirs(subs_dir, exist_ok=True)

    for scene in script:
        srt_path = os.path.join(subs_dir, f"scene_{scene['id']}.srt")
        result = generate_word_by_word_srt(scene["text"], scene["duration"], srt_path)
        scene["srt_path"] = result

    asset_manager = AssetManager()
    assets_map = asset_manager.get_videos(script)

    composer = Composer()
    final_scene_paths = composer.render_all_scenes(script, assets_map)

    if final_scene_paths:
        final_path = composer.concatenate_with_transitions(final_scene_paths)

        if final_path:
            upload_to_huggingface(final_path, topic)
        else:
            print("❌ L'assemblage final a echoue, upload annule.")

        clean_cache()
    else:
        print("❌ Failed to generate any scenes.")


if __name__ == "__main__":
    asyncio.run(main())
