import asyncio
from modules.brain import ContentBrain
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer

async def main():
    print("🚀 STARTING AUTOMATION (Edge-TTS Mode) 🚀")
    
    # 1. BRAIN: Get Script
    brain = ContentBrain()
    try:
        topic = brain.get_trending_topic()
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
    assets_map = asset_manager.get_stock_for_script(script)

    # 4. COMPOSER: Merge Video + Audio
    composer = Composer()
    final_scene_paths = []

    for scene in script:
        scene_id = scene['id']
        stock_path = assets_map.get(scene_id)
        
        if stock_path:
            scene_video = composer.process_scene(scene, stock_path)
            if scene_video:
                final_scene_paths.append(scene_video)
        else:
            print(f"⚠️ Skipping Scene {scene_id} (No Video Found)")

    # 5. STITCH WITH TRANSITIONS
    if final_scene_paths:
        # CHANGED: Now using the transition function instead of simple concat
        composer.concatenate_with_transitions(final_scene_paths)
    else:
        print("❌ Failed to generate any scenes.")

if __name__ == "__main__":
    asyncio.run(main())