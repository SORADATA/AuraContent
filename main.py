import asyncio
import os
import traceback

from modules.brain import ContentBrain
from modules.retention import RetentionPlanner
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer
from modules.sound_design import SoundDesigner
from modules.quality_control import QualityControl
from modules.performance_learner import PerformanceLearner


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
        # 2. TOPIC + HOOK
        # ============================================================

        print("🧠 Recherche du sujet...")

        best_patterns = learner.get_best_patterns()

        learning_context = learner.build_brain_context()

        raw_topic = brain.get_trending_topic(
            learning_context=learning_context
        )

        if not raw_topic:
            raise RuntimeError(
                "Aucun sujet n'a été retourné par ContentBrain."
            )

        topic = brain.refine_topic_angle(raw_topic)

        if not topic:
            raise RuntimeError(
                "Impossible de raffiner l'angle du sujet."
            )

        print(f"🎯 Sujet retenu : {topic}")

        hooks = brain.generate_hook_variants(
            topic,
            n=3
        )

        if not hooks:
            raise RuntimeError(
                "Aucun hook généré."
            )

        chosen_hook = next(
            (
                h for h in hooks
                if h.get("pattern") in best_patterns
            ),
            hooks[0]
        )

        print(
            f"🪝 Hook choisi : "
            f"{chosen_hook.get('pattern', 'unknown')}"
        )

        # ============================================================
        # 3. SCRIPT
        # ============================================================

        print("📝 Génération du script...")

        raw_script_data = brain.generate_script(
            topic,
            chosen_hook["text"]
        )

        if not raw_script_data:
            raise RuntimeError(
                "Le générateur de script n'a retourné aucune donnée."
            )

        if not raw_script_data.get("scenes"):
            raise RuntimeError(
                "Le script ne contient aucune scène."
            )

        print(
            f"🎬 Script généré : "
            f"{len(raw_script_data['scenes'])} scènes"
        )

        script_data = raw_script_data.copy()

        script_data["scenes"] = planner.plan(
            raw_script_data["scenes"]
        )

        # ============================================================
        # 4. AUDIO
        # ============================================================

        print("🎙️ Génération audio...")

        script_data = await audio.process_script_audio(
            script_data
        )

        print("✅ Audio généré")

        # ============================================================
        # 5. ASSETS VISUELS
        # ============================================================

        print("🎨 Génération/récupération des assets visuels...")

        video_asset_lists = []

        for i, scene in enumerate(script_data["scenes"], start=1):

            print(
                f"🎨 Scène {i}/{len(script_data['scenes'])}"
            )

            variants = assets.get_scene_variants(
                scene,
                composer.temp_dir
            )

            if not variants:
                raise RuntimeError(
                    f"Aucun asset généré pour la scène {i}."
                )

            video_asset_lists.append(variants)

            print(
                f"✅ Assets scène {i} terminés"
            )

        # ============================================================
        # 6. MUSIQUE
        # ============================================================

        dominant_mood = (
            script_data["scenes"][0].get(
                "mood",
                "intriguing"
            )
        )

        print(
            f"🎵 Ambiance dominante : {dominant_mood}"
        )

        composer.set_background_music(
            dominant_mood
        )

        # ============================================================
        # 7. RENDU
        # ============================================================

        print("🎞️ Rendu des scènes...")

        rendered_paths = composer.render_all_scenes(
            script_data["scenes"],
            video_asset_lists
        )

        if not rendered_paths:
            raise RuntimeError(
                "Aucune scène rendue."
            )

        print(
            f"✅ {len(rendered_paths)} scènes rendues"
        )

        # ============================================================
        # 8. EFFETS SONORES
        # ============================================================

        print("🔊 Application des effets sonores...")

        for i, path in enumerate(rendered_paths):

            scene = script_data["scenes"][i]

            if scene.get("sound_effect"):

                sfx_output = os.path.join(
                    composer.temp_dir,
                    f"sfx_applied_{i}.mp4"
                )

                print(
                    f"🔊 SFX scène {i + 1}: "
                    f"{scene['sound_effect']}"
                )

                success = sfx_designer.apply_effect(
                    path,
                    sfx_output,
                    scene["sound_effect"]
                )

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

        if not final_path:
            raise RuntimeError(
                "L'assemblage n'a retourné aucun fichier."
            )

        if not os.path.exists(final_path):
            raise RuntimeError(
                f"Le fichier final est absent : {final_path}"
            )

        print(
            f"✅ Vidéo assemblée : {final_path}"
        )

        # ============================================================
        # 10. QUALITY GATE
        # ============================================================

        print("🔎 Contrôle qualité...")

        if not qc.validate(final_path):

            raise RuntimeError(
                "Vidéo rejetée par le Quality Control "
                "(durée, résolution ou audio)."
            )

        print("✅ Contrôle qualité validé")

        # ============================================================
        # 11. APPRENTISSAGE
        # ============================================================

        print(
            "📈 Enregistrement des données de performance..."
        )

        duration = composer.get_duration(
            final_path
        )

        learner.record(
            title=topic,
            topic=raw_topic,
            hook_pattern=chosen_hook.get("pattern"),
            duration=duration
        )

        # ============================================================
        # 12. NETTOYAGE
        # ============================================================

        clean_cache()

        print(
            "✅ PIPELINE V3 TERMINÉ AVEC SUCCÈS."
        )

        print(
            f"📁 Fichier disponible : {final_path}"
        )

        return True

    except asyncio.CancelledError:

        print(
            "🛑 PIPELINE ANNULÉ : asyncio.CancelledError"
        )

        raise

    except Exception as exc:

        print("")
        print("=" * 70)
        print("❌ ERREUR CRITIQUE DU PIPELINE")
        print("=" * 70)
        print(f"Type : {type(exc).__name__}")
        print(f"Message : {exc}")
        print("")
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

        print(
            f"❌ Erreur fatale hors pipeline : "
            f"{type(exc).__name__}: {exc}"
        )

        traceback.print_exc()

        raise SystemExit(1)
