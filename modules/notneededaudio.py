import os
import requests
import asyncio
import ffmpeg # ✅ Added for silence trimming
from mutagen.wave import WAVE

class AudioEngine:
    def __init__(self):
        # ---------------------------------------------------------
        # 🔗 YOUR NGROK URL
        # ---------------------------------------------------------
        raw_url = "https://60c92b3aa1f8.ngrok-free.app/"

        # 🛠️ AUTO-FIX: Removes trailing slash and ensures correct format
        self.base_url = raw_url.strip().rstrip("/")
        if self.base_url.endswith("/generate"):
            self.base_url = self.base_url[:-9] 

        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

    def clean_text(self, text):
        """
        Removes punctuation that causes Bark to gasp or hesitate.
        """
        # Replace hesitation markers with simple spaces
        clean = text.replace("...", " ").replace("—", " ").replace("–", " ")
        return clean.strip()

    def trim_silence(self, file_path):
        """
        Uses FFmpeg to remove silence from the end of the clip.
        This fixes the 'Big Gap' issue at the end of Bark generations.
        """
        temp_path = file_path.replace(".wav", "_temp.wav")
        
        try:
            # 1. Reverse audio
            # 2. Trim silence from beginning (which is actually the end)
            # 3. Reverse back
            (
                ffmpeg
                .input(file_path)
                .filter('areverse')
                .filter('silenceremove', start_periods=1, start_silence=0.1, start_threshold='-50dB')
                .filter('areverse')
                .filter('volume', 1.5)
                .output(temp_path)
                .overwrite_output()
                .run(quiet=True)
            )
            
            # If successful, replace original with trimmed version
            if os.path.exists(temp_path):
                os.replace(temp_path, file_path)
                
        except Exception as e:
            print(f"      ⚠️ Failed to trim silence: {e}")

    async def generate_audio(self, text, output_filename):
        # Bark outputs .wav
        filename_wav = output_filename.rsplit('.', 1)[0] + ".wav"
        output_path = os.path.join(self.output_dir, filename_wav)
        
        # Construct the full API endpoint
        api_url = f"{self.base_url}/generate"
        
        # 🧹 STEP 1: CLEAN THE TEXT
        cleaned_text = self.clean_text(text)
        
        payload = {
            "text": cleaned_text,
            "voice_preset": "v2/en_speaker_9",
            # 🎛️ CONFIDENCE SETTINGS
            # text_temp=0.5 reduces random gasps/stuttering
            "text_temp": 0.7,
        }

        print(f"      📡 Sending to Colab: {cleaned_text[:25]}...")
        
        try:
            # Sync request with 2 minute timeout (Deep generation takes time)
            response = requests.post(api_url, json=payload, timeout=120)
            
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                # ✂️ STEP 2: TRIM THE SILENCE GAP
                self.trim_silence(output_path)
                
                return output_path
            elif response.status_code == 404:
                print(f"❌ 404 NOT FOUND. Check URL in audio.py.")
                print(f"   Target: {api_url}")
                return None
            else:
                print(f"❌ Server Error ({response.status_code}): {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            return None

    def get_audio_duration(self, file_path):
        try:
            audio = WAVE(file_path)
            return audio.info.length
        except Exception as e:
            print(f"❌ Error reading audio duration: {e}")
            return 0.0

    async def process_script(self, script_data):
        print(f"🎙️ Starting Audio Generation (Bark via Cloud GPU)...")
        
        for scene in script_data:
            scene_id = scene['id']
            text = scene['text']
            
            # Using .wav for high quality
            filename = f"voice_{scene_id}.wav"
            
            file_path = await self.generate_audio(text, filename)
            
            if file_path:
                duration = self.get_audio_duration(file_path)
                scene['audio_path'] = file_path
                scene['duration'] = duration
                print(f"   ✅ Scene {scene_id}: {duration:.2f}s generated (Trimmed).")
            else:
                print(f"   ❌ Failed Scene {scene_id}")

        return script_data