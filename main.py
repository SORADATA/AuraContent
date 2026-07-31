import argparse
import asyncio
import os
import shutil
import math
from datetime import datetime
from pathlib import Path
from huggingface_hub import HfApi

from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer

from modules.utils.huggingface import upload_to_huggingface
from modules.utils.filesystem import clean_cache
from modules.utils.subtitles import generate_grouped_srt
from modules.utils.script_helpers import estimate_scene_count, validate_script_payload

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

    topic_input = os.getenv("VIDEO_TOPIC", "").strip()
    duration_target = int(os.getenv("VIDEO_DURATION", "45"))
    refine_angle = os.getenv("REFINE_ANGLE", "true").lower() == "true"
    use_hooks_ab_test = os.getenv("USE_HOOK_VARIANTS", "true").lower() == "true"

    brain = ContentBrain(channel_config=channel_config["brain"])

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
        srt_path = str(subs_dir / f"scene_{scene['id']}.srt")
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
        composer = Composer(root_dir=channel_dir)
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
        upload_to_huggingface(
            video_path=final_path, 
            topic=video_title, 
            repo_id=channel_config["hf_repo"]
        )
        clean_cache()
    else:
        print("❌ L'assemblage final a echoue, upload annule.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Générateur de Shorts Multi-Chaînes")
    parser.add_argument("--channel", type=str, required=True, help="Nom de la chaîne (ex: minute_mystere, finance)")
    args = parser.parse_args()

    asyncio.run(generate_video(args.channel))