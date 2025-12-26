import asyncio
import os
from notneededaudio import AudioEngine

async def run_tests():
    print("\n🧪 --- STARTING AUDIO CONNECTION TEST ---")
    
    # Initialize the engine
    try:
        engine = AudioEngine()
    except Exception as e:
        print(f"❌ CRITICAL: Could not initialize AudioEngine. Check your imports. Error: {e}")
        return

    print(f"ℹ️  Target URL configured in audio.py: {engine.base_url}")
    print(f"ℹ️  Full Endpoint being hit: {engine.base_url}/generate")
    
    # ---------------------------------------------------------
    # TEST 1: REAL GENERATION
    # ---------------------------------------------------------
    print("\n👉 TEST 1: Attempting to generate 'Hello World' audio...")
    test_text = "This is a test of the emergency broadcast system."
    test_filename = "test_connection.wav"
    
    # Clean up previous test file if it exists
    full_path = os.path.join(engine.output_dir, test_filename)
    if os.path.exists(full_path):
        os.remove(full_path)

    start_time = asyncio.get_event_loop().time()
    result = await engine.generate_audio(test_text, test_filename)
    end_time = asyncio.get_event_loop().time()

    if result and os.path.exists(result):
        file_size = os.path.getsize(result)
        print(f"   ✅ SUCCESS! Audio received.")
        print(f"   📂 Saved to: {result}")
        print(f"   📊 Size: {file_size/1024:.2f} KB")
        print(f"   ⏱️  Time taken: {end_time - start_time:.2f} seconds")
    else:
        print("   ❌ FAILED: No file was generated.")
        print("   💡 TIP: Check the error message above. If it says '404', your URL is wrong.")
        print("   💡 TIP: If it says 'Connection refused', check if Colab is still running.")

    # ---------------------------------------------------------
    # TEST 2: ERROR HANDLING (Intentional Failure)
    # ---------------------------------------------------------
    print("\n👉 TEST 2: Testing Error Handling (Using a fake URL)...")
    
    # Temporarily break the URL
    original_url = engine.base_url
    engine.base_url = "https://ec6217c811db.ngrok-free.app/"
    
    result = await engine.generate_audio("This should fail", "fail_test.wav")
    
    if result is None:
        print("   ✅ SUCCESS! The system correctly identified the connection failure.")
    else:
        print("   ⚠️  WARNING: Something weird happened. It shouldn't have succeeded.")

    # Restore URL just in case
    engine.base_url = original_url

    print("\n🧪 --- TEST COMPLETE ---")

if __name__ == "__main__":
    # Windows loop policy fix (just in case)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(run_tests())