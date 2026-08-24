import asyncio
import os
from modules.brain import ContentBrain
from modules.retention import RetentionPlanner
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer
from modules.sound_design import SoundDesigner
from modules.quality_control import QualityControl
from modules.performance_learner import PerformanceLearner # Correction du nom d'import ici


def clean_cache():
    temp_dir = os.path.join(os.getcwd(), "assets", "temp")
    if os.path.exists(temp_dir):
        for f in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, f))
            except:
                pass


async def main():
    print("🚀 Démarrage du pipeline AuraContent V3 (Minute Mystère)")
    
    # 1. Initialisation des modules
    brain = ContentBrain()
    planner = RetentionPlanner()
    assets = AssetManager()
    audio = AudioEngine()
    composer = Composer()
    sfx_designer = SoundDesigner()
    qc = QualityControl()
    learner = PerformanceLearner()

    # 2. Topic & Hook basés sur l'apprentissage
    best_patterns = learner.get_best_patterns()
    
    # --- INJECTION DU CONTEXTE D'APPRENTISSAGE ---
    learning_context = learner.build_brain_context()
    raw_topic = brain.get_trending_topic(learning_context=learning_context)
    # ---------------------------------------------
    
    topic = brain.refine_topic_angle(raw_topic)
    
    print(f"🎯 Sujet retenu : {topic}")
    
    hooks = brain.generate_hook_variants(topic, n=3)
    # On privilégie un hook qui a déjà fait ses preuves, sinon on prend le premier
    chosen_hook = next((h for h in hooks if h.get("pattern") in best_patterns), hooks[0])
    
    # 3. Script & Planification de Rétention (Micro-plans, SFX)
    raw_script_data = brain.generate_script(topic, chosen_hook["text"])
    script_data = raw_script_data.copy()
    script_data["scenes"] = planner.plan(raw_script_data["scenes"])
    
    # 4. Génération Audio (Stricte 2 voix)
    script_data = await audio.process_script_audio(script_data)
    
    # 5. Génération Visuelle (Micro-plans variants)
    video_asset_lists = []
    for scene in script_data["scenes"]:
        variants = assets.get_scene_variants(scene, composer.temp_dir)
        video_asset_lists.append(variants)

    # 6. Choix de la musique de fond selon l'ambiance dominante
    dominant_mood = script_data["scenes"][0].get("mood", "intriguing")
    composer.set_background_music(dominant_mood)

    # 7. Rendu des scènes
    rendered_paths = composer.render_all_scenes(script_data["scenes"], video_asset_lists)
    
    # 8. Application des effets sonores (Impacts)
    for i, path in enumerate(rendered_paths):
        scene = script_data["scenes"][i]
        if scene.get("sound_effect"):
            sfx_output = os.path.join(composer.temp_dir, f"sfx_applied_{i}.mp4")
            if sfx_designer.apply_effect(path, sfx_output, scene["sound_effect"]):
                rendered_paths[i] = sfx_output

    # 9. Assemblage final et Mixage
    print("🎬 Assemblage final de la vidéo...")
    try:
        final_path = composer.concatenate_with_transitions(rendered_paths, output_filename="minute_mystere_final.mp4")
    except Exception as exc:
        print(f"❌ Erreur critique lors de l'assemblage : {exc}")
        return

    if not final_path:
        print("❌ Vidéo finale absente.")
        return

    # 10. Contrôle Qualité (Quality Gate)
    print("🔎 Contrôle qualité...")
    if not qc.validate(final_path):
        print("❌ Action bloquée : vidéo non conforme (durée, résolution, ou audio manquant).")
        return

    # 11. Apprentissage & Historisation
    print("📈 Enregistrement des données de performance...")
    learner.record(
        title=topic,
        topic=raw_topic,
        hook_pattern=chosen_hook.get("pattern"),
        duration=composer.get_duration(final_path)
    )

    clean_cache()
    print(f"✅ PIPELINE V3 TERMINÉ AVEC SUCCÈS. Fichier disponible : {final_path}")

if __name__ == "__main__":
    asyncio.run(main())
