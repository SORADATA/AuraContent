import asyncio
import time
import os
import shutil
from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer

def clean_cache():
    """
    Safely deletes temporary files.
    Includes a Safety Lock to prevent deleting anything outside the project.
    """
    print("🧹 Cleaning up temporary files...")
    
    # 1. Define the specific target folders
    folders_to_clean = [
        os.path.join(os.getcwd(), "assets", "audio_clips"),
        os.path.join(os.getcwd(), "assets", "video_clips"),
        os.path.join(os.getcwd(), "assets", "temp")
    ]

    for folder in folders_to_clean:
        # SAFETY CHECK 1: Ensure folder actually exists
        if not os.path.exists(folder):
            continue
            
        # SAFETY CHECK 2: Double check we are inside our project "assets" folder
        if "assets" not in folder:
            print(f"    🚨 SECURITY ALERT: Skipping {folder} because it looks unsafe!")
            continue

        # Loop through files inside the folder
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path) # Delete the file
                    print(f"       Deleted: {filename}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path) # Delete subfolders if any
            except Exception as e:
                print(f"    ❌ Failed to delete {file_path}. Reason: {e}")
    
    print("✨ Workspace clean!")

async def main():
    print("🚀 STARTING AUTOMATION...")
    
    # 1. BRAIN: Get Script
    brain = ContentBrain()
    try:
        # Récupère automatiquement un sujet tendance (ou utilise une variable si définie)
        topic = brain.get_trending_topic()
        
        # ⏳ Pause de sécurité de 15 secondes pour laisser souffler l'API et éviter l'erreur 429 (Quota)
        print("⏳ Pause de sécurité pour l'API (15s)...")
        time.sleep(15)
        
        script = brain.generate_script(topic)
    except Exception as e:
        print(f"❌ Brain Error: {e}")
        return
    
    if not script:
        print("❌ Script generation failed.")
        return

    # 2. AUDIO: Generate Voice
    audio_engine = AudioEngine() 
    try:
        script = await audio_engine.process_script(script)
    except Exception as e:
        print(f"❌ Audio Error: {e}")
        return

    # 3. ASSETS: Get Stock Video
    asset_manager = AssetManager()
    assets_map = asset_manager.get_videos(script)

    # 4. COMPOSER: Merge Video + Audio
    composer = Composer()

    final_scene_paths = composer.render_all_scenes(script, assets_map)

    # 5. STITCH WITH TRANSITIONS
    if final_scene_paths:
        composer.concatenate_with_transitions(final_scene_paths)
        clean_cache()
    else:
        print("❌ Failed to generate any scenes.")

if __name__ == "__main__":
    asyncio.run(main())
