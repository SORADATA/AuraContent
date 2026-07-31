import asyncio
import os
import shutil
from datetime import datetime
from huggingface_hub import HfApi

from modules.kids_scriptwriter import KidsScriptwriter
from modules.kids_tts import KidsAudioEngine
from modules.character_engine import CharacterEngine
from modules.scene_animator import SceneAnimator
from modules.composer_kids import ComposerKids


def upload_to_huggingface(video_path, topic):
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token or not video_path or not os.path.exists(video_path):
        print("⚠️ Upload HF ignoré (token manquant ou fichier introuvable)")
        return

    api = HfApi(token=hf_token)
    repo_id = "soradata/MimoluneVideos"

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c if c.isalnum() else "_" for c in topic)[:50]
    remote_filename = f"mimolune_videos/{timestamp}_{safe_topic}.mp4"

    try:
        api.upload_file(
            path_or_fileobj=video_path,
            path_in_repo=remote_filename,
            repo_id=repo_id,
            repo_type="dataset",
        )
        print(f"✅ Vidéo Mimolune uploadée sur Hugging Face : {repo_id}/{remote_filename}")
    except Exception as e:
        print(f"❌ Échec upload Hugging Face : {e}")


def clean_mimolune_cache():
    print("🧹 Nettoyage des fichiers temporaires Mimolune...")
    temp_dir = os.path.join(os.getcwd(), "assets", "mimolune", "temp")
    if os.path.exists(temp_dir):
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"    ❌ Échec suppression {file_path}: {e}")
    print("✨ Cache Mimolune nettoyé !")


async def main():
    print("🚀 DÉMARRAGE DU PIPELINE MIMOLUNE...")

    mimolune_dir = os.path.join("assets", "mimolune")
    topic = os.getenv("VIDEO_TOPIC", "Les couleurs magiques")

    # 1. Écriture du scénario de comptine
    writer = KidsScriptwriter()
    data = writer.generate_comptine(topic, scene_count=8)
    if not data:
        print("❌ Échec de la génération du script.")
        return
    scenes = data["scenes"]
    theme_title = data.get("theme", topic)

    # 2. Audio (Voix + durée par scène)
    tts_engine = KidsAudioEngine()
    try:
        scenes = await tts_engine.process_script(scenes)
    except Exception as e:
        print(f"❌ Erreur Audio TTS : {e}")
        return

    # 3. Récupération des Assets (Personnages et illustrations de scène)
    char_engine = CharacterEngine()
    char_engine.prepare_assets()
    scenes = char_engine.generate_scene_images(scenes)

    # 4. Animation des scènes (Wan 2.2 + fallback FFmpeg zoompan)
    animator = SceneAnimator()
    scenes = animator.animate_all_scenes(scenes)

    # 5. Composition Finale (Assemblage et transitions)
    composer = ComposerKids()
    final_path = composer.assemble_final_video(scenes)

    # 6. Sauvegarde, Upload et Nettoyage
    if final_path:
        final_dir = os.path.join(mimolune_dir, "final")
        os.makedirs(final_dir, exist_ok=True)
        final_dest = os.path.join(final_dir, "final_short.mp4")

        if os.path.abspath(final_path) != os.path.abspath(final_dest):
            shutil.copy(final_path, final_dest)
        else:
            print("✅ Le fichier final est déjà au bon emplacement.")

        print(f"🎉 PIPELINE TERMINÉ AVEC SUCCÈS ! Vidéo sauvée : {final_dest}")

        upload_to_huggingface(final_dest, theme_title)
        clean_mimolune_cache()
    else:
        print("❌ Échec de la génération de la vidéo finale Mimolune.")


if __name__ == "__main__":
    asyncio.run(main())