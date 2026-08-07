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

try:
    from modules.utils.client_http.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Feedback loop desactive pour cette execution.")

    def get_latest_videos_stats():
        return None


# =====================================================================
# --- PIPELINE PRINCIPAL ---
# =====================================================================

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

    # --- 2. GÉNÉRATION DU SCRIPT ET HOOKS ---
    try:
        chosen_hook = None
        if use_hooks_ab_test:
            try:
                hooks = brain.generate_hook_variants(
                    topic,
                    n=5,
                    previous_stats_list=stats_historique,
                )
                chosen_hook = hooks[0]["text"]
                print(f"🧠 Hook retenu ({hooks[0]['pattern']}): {chosen_hook}")
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

    except Exception as e:
        print(f"❌ Brain Error (Script): {e}")
        return

    if not script:
        print("❌ Script generation failed.")
        return

    # --- 3. MODE HYBRIDE : VIDÉOS D'ILLUSTRATION ET IMAGES IA PAR SCÈNE ---
    temp_dir = os.path.join(os.getcwd(), "assets", "temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    bg_video_path = None
    video_pairs = []

    print("🔄 Génération du mix hybride dynamique (Vidéos de stock prioritaires + Images IA)...")
    visual_id = script_payload.get("visual_identity", "Cinematic documentary")

    for index, scene in enumerate(script):
        role = scene.get("role", "value")
        scene_id = scene['id']
        
        asset_path = None

        # On force l'image IA pour le CTA final OU pour une scène sur deux (index impair)
        force_ai_image = (role == "cta") or (index % 2 != 0)

        # Si on ne force pas l'IA, on cherche une vidéo de stock
        if not force_ai_image:
            scene_query = scene.get("stock_search", dynamic_query) + " vertical 9:16"
            video_path = os.path.join(temp_dir, f"scene_video_{scene_id}.mp4")
            print(f"   🎬 Scène {scene_id} ({role}) : Recherche vidéo stock pour '{scene_query}'...")
            
            try:
                if asset_manager.fetch_background_video(scene_query, video_path):
                    asset_path = video_path
            except Exception as e:
                print(f"   ⚠️ Erreur stock vidéo scène {scene_id} : {e}")

        # Si on a forcé l'IA, OU si la recherche de vidéo a échoué (fallback)
        if not asset_path:
            label = "Génération" if force_ai_image else "Fallback"
            print(f"   🎨 Scène {scene_id} ({role}) : {label} image IA contextuelle...")
            img_path = os.path.join(temp_dir, f"scene_{scene_id}.jpg")
            asset_manager.generate_image(scene["image_prompt"], img_path, visual_id)
            asset_path = img_path

        video_pairs.append(asset_path)

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
        clean_cache()
    else:
        print("❌ L'assemblage final a échoué, upload annulé.")


if __name__ == "__main__":
    asyncio.run(main())
