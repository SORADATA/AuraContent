import os
import asyncio
from mutagen.mp3 import MP3

try:
    import edge_tts
    EDGE_AVAILABLE = True
except ImportError:
    EDGE_AVAILABLE = False


class AudioEngine:
    # --- VOIX MASCULINE UNIQUE (Henri) ---
    EDGE_VOICE = "fr-FR-HenriNeural" 
    EDGE_RATE = "+5%"    # Rythme un peu plus dynamique pour TikTok
    EDGE_PITCH = "-2Hz"  # Voix légèrement plus grave et posée
    EDGE_VOLUME = "+0%"

    def __init__(self, **kwargs):
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)
        self.min_scene_duration = 3.0

    def clean_text(self, text):
        text = text.replace("\u2014", ", ").replace("\u2013", ", ")
        text = text.replace("...", ". ")
        return " ".join(text.split()).strip()

    def get_audio_duration(self, file_path):
        try:
            return MP3(file_path).info.length
        except Exception:
            return 0.0

    async def generate_audio(self, text, output_filename):
        if not EDGE_AVAILABLE:
            raise RuntimeError("Le module edge_tts n'est pas installé.")

        base_name = output_filename.rsplit(".", 1)[0]
        mp3_path = os.path.join(self.output_dir, base_name + ".mp3")
        
        communicate = edge_tts.Communicate(
            text=self.clean_text(text),
            voice=self.EDGE_VOICE,
            rate=self.EDGE_RATE,
            volume=self.EDGE_VOLUME,
            pitch=self.EDGE_PITCH,
        )
        await communicate.save(mp3_path)
        
        return mp3_path, "edge-tts (Henri)"

    async def process_script(self, script_data):
        print("🎙️ Generation audio (Voix Unique : Edge Henri)...")

        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
            output_filename = f"scene_{scene_id}.mp3"

            audio_path, engine_used = await self.generate_audio(text, output_filename)

            scene["audio_path"] = audio_path
            scene["tts_engine"] = engine_used

            duration = self.get_audio_duration(audio_path)
            scene["duration"] = max(duration, self.min_scene_duration)

            print(
                f"      Scene {scene_id}: audio genere via {engine_used} "
                f"({scene['duration']:.2f}s)"
            )

        return script_data
