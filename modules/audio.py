import os
import asyncio
import edge_tts
from mutagen.mp3 import MP3


class AudioEngine:
    def __init__(self):
        self.audio_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.audio_dir, exist_ok=True)
        # Voix française forcée — NE PAS laisser en anglais
        self.voice = "fr-FR-VivienneMultilingualNeural"
        # Alternatives si celle-ci échoue : "fr-FR-HenriNeural" ou "fr-FR-DeniseNeural"
        # Ralentit le débit pour une diction plus posée (ajuste entre -10% et -20%)
        self.rate = "-15%"

    async def generate_audio(self, text, output_path):
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        await communicate.save(output_path)

    def get_duration(self, filepath):
        try:
            audio = MP3(filepath)
            return audio.info.length
        except Exception as e:
            print(f"    Erreur durée audio: {e}")
            return 5.0

    async def process_script(self, script_data):
        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
            output_path = os.path.join(self.audio_dir, f"scene_{scene_id}.mp3")

            print(f"Voix off scène {scene_id} en français ({self.voice}, rate={self.rate})...")
            await self.generate_audio(text, output_path)

            scene["audio_path"] = output_path
            duration = self.get_duration(output_path)

            # Sécurité : impose une durée minimale pour éviter les scènes flash
            if duration < 3.5:
                print(f"    Scène {scene_id} trop courte ({duration:.1f}s), durée forcée à 3.5s")
                duration = 3.5

            scene["duration"] = duration

        return script_data