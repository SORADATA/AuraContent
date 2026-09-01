import asyncio
import os

from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer
from modules.utils.database.uploader import upload_to_huggingface
from modules.utils.cache import clean_cache
from modules.utils.subtitles import generate_grouped_srt
from modules.utils.caption_generator import generate_caption, save_caption
from modules.utils.helpers import estimate_scene_count, validate_script_payload
from modules.utils.hook_tracker import (
    load_hook_history,
    record_hook_usage,
    compute_pattern_scores,
    select_hook,
)
from modules.utils.topic_tracker import record_topic_usage

try:
    from modules.utils.client_http.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Feedback loop desactive pour cette execution.")

    def get_latest_videos_stats():
        return None

async def main():
    print("🚀 STARTING AUTOMATION...")

    topic_input = os.getenv("VIDEO_TOPIC", "").strip()
    duration_target = int(os.getenv("VIDEO_DURATION", "45"))
    refine_angle = os.getenv("REFINE_ANGLE", "true").lower() == "true"
    use_hooks_ab_test = os.getenv("USE_HOOK_VARIANTS", "true").lower() == "true"

    brain = ContentBrain()
    asset_manager = AssetManager()

    print("📡 Récupération des statistiques Zernio pour l'Agent IA...")
    try:
        stats_historique = get_latest_videos_stats()
    except Exception as e:
        print(f"⚠️ Impossible de recuperer les stats Zernio : {e}")
        stats_historique = None

    # --- 1. GÉNÉRATION DU SUJET ET DE LA REQUÊTE ---
    try:
        if topic_input:
            topic = topic_input
            print(f"📌 Sujet fourni manuellement : {topic}")
            if refine_angle and hasattr(brain, "refine_topic_angle"):
                topic = brain.refine_topic_angle(topic)
                print(f"🎯 Angle affine : {topic}")
        else:
            topic = brain.get_trending_topic(previous_stats_list=stats_historique)
            print(f"🔥 Sujet selectionne automatiquement : {topic}")

        print("🔍 Génération du mot-clé de recherche visuelle par l'IA...")
        dynamic_query = brain.generate_video_search_query(topic)
        print(f"🎯 Requête vidéo générée : '{dynamic_query}'")

    except Exception as e:
        print(f"❌ Brain Error (Sujet/Requête): {e}")
        return

    # --- 2. GÉNÉRATION DU SCRIPT ET HOOKS (SCORING PAR BANDIT) ---
    try:
        chosen_hook = None
        chosen_hook_pattern = None

        if use_hooks_ab_test:
            try:
                hooks = brain.generate_hook_variants(
                    topic,
                    n=5,
                    previous_stats_list=stats_historique,
                )

                hook_history = load_hook_history()
                pattern_scores = compute_pattern_scores(stats_historique, hook_history)

                if pattern_scores:
                    print(f"📈 Scores de patterns connus : {pattern_scores}")

                selected = select_hook(hooks, pattern_scores=pattern_scores)
                if selected:
                    chosen_hook = selected["text"]
                    chosen_hook_pattern = selected.get("pattern", "?")
                    print(f"🧠 Hook retenu ({chosen_hook_pattern}): {chosen_hook}")

            except Exception as e:
                print(f"⚠️ Generation des hooks alternatifs echouee : {e}")

        scene_count = estimate_scene_count(duration_target)
        print(f"⏱️ Duree cible: {duration_target}s -> {scene_count} scenes")

        script_payload = brain.generate_script_with_target(
            topic,
            scene_count,
            chosen_hook=chosen_hook,
        )

        validate_script_payload(script_payload)
        script = script_payload["scenes"]
        video_title = script_payload.get("title", topic)
        script_payload["hook_pattern_used"] = chosen_hook_pattern

    except Exception as e:
        print(f"❌ Brain Error (Script): {e}")
        return

    if not script:
        print("❌ Script generation failed.")
        return

    # --- 3. RECHERCHE D'ASSETS (LOGIQUE V2.1 : ROUTAGE CORRIGÉ) ---
    temp_dir = os.path.join(os.getcwd(), "assets", "temp")
    os.makedirs(temp_dir, exist_ok=True)

    bg_video_path = None
    video_pairs = []

    print("🔄 Recherche des meilleurs assets (Archives / Vidéos / IA)...")

    for index, scene in enumerate(script):
        scene_id = scene['id']
        scene_type = scene.get("scene_type", "generic")

        location_name = (scene.get("location_name") or "").strip()
        stock_search = (scene.get("stock_search") or "").strip()
        image_prompt = (scene.get("image_prompt") or "").strip()

        if scene_type == "specific":
            search_query = location_name or dynamic_query
        else:
            search_query = stock_search or dynamic_query

        event_context = scene.get("event_context") or None

        temp_asset_path = os.path.join(temp_dir, f"temp_media_{scene_id}.mp4")

        log_query = search_query if not event_context else f"{search_query} (contexte: {event_context})"
        print(f"  🎬 Scène {scene_id} [{scene_type}] : Recherche de l'asset pour '{log_query}'...")

        success, source_type = asset_manager.get_best_asset(
            query=search_query,
            output_path=temp_asset_path,
            scene_type=scene_type,
            event_context=event_context,
            image_prompt=image_prompt,
        )

        if success and os.path.exists(temp_asset_path):
            final_asset_path = os.path.join(temp_dir, f"scene_{source_type}_{scene_id}.mp4")
            os.rename(temp_asset_path, final_asset_path)
            video_pairs.append(final_asset_path)
        else:
            print(f"  ❌ Impossible de trouver un asset pour la scène {scene_id}. La vidéo pourrait être tronquée.")

    # --- 4. LÉGENDE, AUDIO ET SOUS-TITRES ---
    print("📝 Demande de légende à l'IA basée sur le script complet...")
    full_text = " ".join(scene["text"] for scene in script)
    legende_finale = generate_caption(full_text, video_title)
    save_caption(legende_finale)

    audio_engine = AudioEngine()

    try:
        print("🎙️ Generation audio...")
        script = await audio_engine.process_script(script)
    except Exception as e:
        print(f"❌ Audio Error: {e}")
        return

    subs_dir = os.path.join(os.getcwd(), "assets", "temp", "subs")
    os.makedirs(subs_dir, exist_ok=True)

    print("📝 Generation des sous-titres...")
    for scene in script:
        srt_path = os.path.join(subs_dir, f"scene_{scene['id']}.srt")
        scene["srt_path"] = generate_grouped_srt(
            text=scene["text"],
            duration=scene["duration"],
            output_path=srt_path,
            max_words_per_caption=3,
            min_caption_dur=0.45,
        )

    # --- 5. ASSEMBLAGE ET MONTAGE ---
    try:
        print("🎞️ Composition video...")
        composer = Composer()
        final_scene_paths = composer.render_all_scenes(
            script_data=script,
            video_pairs=video_pairs,
            bg_video_path=bg_video_path
        )
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

    # --- 6. UPLOAD & NETTOYAGE ---
    if final_path:
        print(f"✅ Video finale prête : {final_path}")
        upload_to_huggingface(final_path, video_title)

        if chosen_hook_pattern:
            record_hook_usage(video_title, chosen_hook_pattern)
            
        record_topic_usage(topic)

        clean_cache()
    else:
        print("❌ L'assemblage final a échoué, upload annulé.")

if __name__ == "__main__":
    asyncio.run(main())