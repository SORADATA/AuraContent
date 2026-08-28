import asyncio
import os
import random
import traceback

from modules.brain import ContentBrain
from modules.retention import RetentionPlanner
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer
from modules.sound_design import SoundDesigner
from modules.quality_control import QualityControl
from modules.performance_learner import PerformanceLearner
from modules.utils.caption_generator import generate_caption, save_caption
from modules.utils.subtitles import generate_grouped_srt
from modules.utils.database.uploader import upload_to_huggingface

# Import conditionnel du client Zernio
try:
    from modules.utils.client_http.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Feedback loop désactivée pour cette exécution.")
    def get_latest_videos_stats():
        return None

def clean_cache():
    temp_dir = os.path.join(os.getcwd(), "assets", "temp")
    if not os.path.exists(temp_dir):
        return
    for f in os.listdir(temp_dir):
        path = os.path.join(temp_dir, f)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception as exc:
            print(f"⚠️ Impossible de supprimer {path}: {exc}")

async def main():
    print("🚀 Démarrage du pipeline AuraContent V3 (Minute Mystère)")
    try:
        # ============================================================
        # 1. INITIALISATION
        # ============================================================
        brain = ContentBrain()
        planner = RetentionPlanner()
        assets = AssetManager()
        audio = AudioEngine()
        composer = Composer()
        sfx_designer = SoundDesigner()
        qc = QualityControl()
        learner = PerformanceLearner()
        print("✅ Modules initialisés")

        # ============================================================
        # 1.5. STATISTIQUES ZERNIO (FEEDBACK LOOP)
        # ============================================================
        print("📡 Récupération des statistiques Zernio pour l'Agent IA...")
        try:
            stats_historique = get_latest_videos_stats()
            if stats_historique:
                print("✅ Statistiques Zernio récupérées avec succès.")
        except Exception as e:
            print(f"⚠️ Impossible de récupérer les stats Zernio : {e}")
            stats_historique = None

        # ============================================================
        # 2. TOPIC + HOOK (INFLUENCÉS PAR ZERNIO)
        # ============================================================
        print("🧠 Recherche du sujet...")
        
        # On passe stats_historique à get_trending_topic pour guider le choix du LLM
        raw_topic = brain.get_trending_topic(previous_stats_list=stats_historique)
        if not raw_topic:
            raise RuntimeError("Aucun sujet n'a été retourné par ContentBrain.")

        topic = brain.refine_topic_angle(raw_topic)
        if not topic:
            raise RuntimeError("Impossible de raffiner l'angle du sujet.")
        print(f"🎯 Sujet retenu : {topic}")

        # On passe également stats_historique pour générer les hooks
        hooks = brain.generate_hook_variants(topic, n=3, previous_stats_list=stats_historique)
        if not hooks:
            raise RuntimeError("Aucun hook généré.")

        # Sélection du meilleur hook via PerformanceLearner
        best_patterns = learner.get_best_patterns()
        chosen_hook = next(
            (h for h in hooks if h.get("pattern") in best_patterns),
            hooks[0]
        )
        print(f"🪝 Hook choisi : {chosen_hook.get('pattern', 'unknown')}")

        # ============================================================
        # 3. SCRIPT
        # ============================================================
        print("📝 Génération du script...")
        raw_script_data = brain.generate_script(topic, chosen_hook["text"])

        if not raw_script_data or not raw_script_data.get("scenes"):
            raise RuntimeError("Le script est vide ou invalide.")
        print(f"🎬 Script généré : {len(raw_script_data['scenes'])} scènes")

        script_data = raw_script_data.copy()
        script_data["scenes"] = planner.plan(raw_script_data["scenes"])
        video_title = raw_script_data.get("title", topic)

        # ============================================================
        # 4. LÉGENDE, AUDIO & SOUS-TITRES
        # ============================================================
        print("📝 Demande de légende à l'IA...")
        full_text = " ".join(scene.get("text", "") for scene in script_data["scenes"])
        
        try:
            legende_finale = generate_caption(full_text, video_title)
            save_caption(legende_finale)
        except Exception as e:
            print(f"⚠️ Erreur lors de la génération de la légende : {e}")

        print("🎙️ Génération audio...")
        script_data = await audio.process_script_audio(script_data)
        print("✅ Audio généré")

        print("📝 Génération des sous-titres (.srt)...")
        subs_dir = os.path.join(os.getcwd(), "assets", "temp", "subs")
        os.makedirs(subs_dir, exist_ok=True)

        for i, scene in enumerate(script_data["scenes"]):
            if scene.get("text") and scene.get("audio_path"):
                audio_duration = composer.get_duration(scene["audio_path"])
                srt_path = os.path.join(subs_dir, f"scene_{scene.get('id', i)}.srt")
                
                generate_grouped_srt(
                    text=scene["text"],
                    duration=audio_duration,
                    output_path=srt_path,
                    max_words_per_caption=3,
                    min_caption_dur=0.45,
                )
                scene["srt_path"] = srt_path
        print("✅ Sous-titres générés")

        # ============================================================
        # 5. ASSETS VISUELS
        # ============================================================
        print("🎨 Génération/récupération des assets visuels...")
        video_asset_lists = []

        for i, scene in enumerate(script_data["scenes"], start=1):
            print(f"🎨 Scène {i}/{len(script_data['scenes'])}")
            variants = assets.get_scene_variants(scene, composer.temp_dir)
            if not variants:
                raise RuntimeError(f"Aucun asset généré pour la scène {i}.")
            video_asset_lists.append(variants)
            print(f"✅ Assets scène {i} terminés")

        # ============================================================
        # 6. MUSIQUE
        # ============================================================
        available_moods = ["intriguing", "ominous", "investigation", "scientific", "tense"]
        dominant_mood = script_data["scenes"][0].get("mood")
        
        if not dominant_mood or dominant_mood not in available_moods:
            dominant_mood = random.choice(available_moods)

        print(f"🎵 Ambiance dominante : {dominant_mood}")
        composer.set_background_music(dominant_mood)

        # ============================================================
        # 7. RENDU
        # ============================================================
        print("🎞️ Rendu des scènes...")
        rendered_paths = composer.render_all_scenes(script_data["scenes"], video_asset_lists)
        if not rendered_paths:
            raise RuntimeError("Aucune scène rendue.")
        print(f"✅ {len(rendered_paths)} scènes rendues")

        # ============================================================
        # 8. EFFETS SONORES
        # ============================================================
        print("🔊 Application des effets sonores...")
        for i, path in enumerate(rendered_paths):
            scene = script_data["scenes"][i]
            if scene.get("sound_effect"):
                sfx_output = os.path.join(composer.temp_dir, f"sfx_applied_{i}.mp4")
                print(f"🔊 SFX scène {i + 1}: {scene['sound_effect']}")
                success = sfx_designer.apply_effect(path, sfx_output, scene["sound_effect"])
                if success:
                    rendered_paths[i] = sfx_output

        # ============================================================
        # 9. ASSEMBLAGE
        # ============================================================
        print("🎬 Assemblage final de la vidéo...")
        final_path = composer.concatenate_with_transitions(
            rendered_paths,
            output_filename="minute_mystere_final.mp4"
        )

        if not final_path or not os.path.exists(final_path):
            raise RuntimeError("L'assemblage n'a retourné aucun fichier valide.")
        print(f"✅ Vidéo assemblée : {final_path}")

        # ============================================================
        # 10. QUALITY GATE
        # ============================================================
        print("🔎 Contrôle qualité...")
        if not qc.validate(final_path):
            raise RuntimeError("Vidéo rejetée par le Quality Control.")
        print("✅ Contrôle qualité validé")

        # ============================================================
        # 11. UPLOAD HUGGING FACE
        # ============================================================
        print("🚀 Envoi de la vidéo vers Hugging Face...")
        try:
            upload_to_huggingface(final_path, video_title)
            print("✅ Upload HF terminé")
        except Exception as e:
            print(f"⚠️ Échec de l'upload vers Hugging Face : {e}")

        # ============================================================
        # 12. APPRENTISSAGE
        # ============================================================
        print("📈 Enregistrement des données de performance...")
        duration = composer.get_duration(final_path)
        learner.record(
            title=topic,
            topic=raw_topic,
            hook_pattern=chosen_hook.get("pattern"),
            duration=duration
        )

        # ============================================================
        # 13. NETTOYAGE
        # ============================================================
        clean_cache()
        print("✅ PIPELINE V3 TERMINÉ AVEC SUCCÈS.")
        print(f"📁 Fichier disponible : {final_path}")
        return True

    except asyncio.CancelledError:
        print("🛑 PIPELINE ANNULÉ : asyncio.CancelledError")
        raise
    except Exception as exc:
        print("\n" + "=" * 70)
        print("❌ ERREUR CRITIQUE DU PIPELINE")
        print("=" * 70)
        print(f"Type : {type(exc).__name__}\nMessage : {exc}\n")
        print("TRACEBACK COMPLET :")
        traceback.print_exc()
        print("=" * 70)
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        if not result:
            raise SystemExit(1)
    except KeyboardInterrupt:
        print("🛑 Pipeline interrompu manuellement.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"❌ Erreur fatale hors pipeline : {type(exc).__name__}: {exc}")
        traceback.print_exc()
        raise SystemExit(1)