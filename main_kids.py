import asyncio
import os
import shutil

from modules.kids_scriptwriter import KidsScriptwriter
from modules.kids_tts import KidsAudioEngine
from modules.character_engine import CharacterEngine
from modules.scene_animator import SceneAnimator
from modules.composer_kids import ComposerKids

# Si upload_to_huggingface est dans un sous dossier infra :
from modules.infra.database.hugging_face import upload_to_huggingface

async def main():
    print("🚀 DÉMARRAGE DU PIPELINE MIMOLUNE...")
    
    # Dossier de base pour Mimolune
    mimolune_dir = os.path.join("assets", "mimolune")
    topic = os.getenv("VIDEO_TOPIC", "Les couleurs magiques")

    # 1. Écriture
    writer = KidsScriptwriter(config={}) # Pense au dummy_config si ContentBrain l'exige
    data = writer.generate_comptine(topic, scene_count=8)
    if not data:
        return
    scenes = data["scenes"]

    # 2. Audio (Voix & Enveloppes)
    tts_engine = KidsAudioEngine()
    scenes = await tts_engine.process_script(scenes)

    # 3. Récupération des Assets (Personnages et Décors)
    char_engine = CharacterEngine()
    char_engine.prepare_assets() # Télécharge/Génère les bonhommes
    scenes = char_engine.generate_backgrounds(scenes) # Génère les décors

    # 4. Animation
    animator = SceneAnimator()
    scenes = animator.animate_all_scenes(scenes)

    # 5. Composition Finale
    composer = ComposerKids()
    final_path = composer.assemble_final_video(scenes)

    # 6. Sauvegarde et Upload
    if final_path:
        final_dir = os.path.join(mimolune_dir, "final")
        os.makedirs(final_dir, exist_ok=True)
        final_dest = os.path.join(final_dir, "final_short.mp4")
        shutil.copy(final_path, final_dest)
        
        upload_to_huggingface(final_dest, data["theme"])
        print("🎉 PIPELINE TERMINÉ AVEC SUCCÈS.")

if __name__ == "__main__":
    asyncio.run(main())