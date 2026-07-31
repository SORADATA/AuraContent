import os
import edge_tts
from mutagen.mp3 import MP3


VOICE_CONFIG = {
    "mimolune": {"voice": "fr-FR-DeniseNeural", "rate": "-5%", "pitch": "+0Hz"},
    "fruit_fraise": {"voice": "fr-FR-EloiseNeural", "rate": "+5%", "pitch": "+20Hz"},
    "fruit_banane": {"voice": "fr-FR-EloiseNeural", "rate": "+10%", "pitch": "-10Hz"},
}
DEFAULT_SPEAKER = "mimolune"


class KidsAudioEngine:
    def __init__(self):
        self.audio_dir = os.path.join(os.getcwd(), "assets", "mimolune", "audio_clips")
        os.makedirs(self.audio_dir, exist_ok=True)

    def _voice_config_for(self, speaker):
        return VOICE_CONFIG.get(speaker, VOICE_CONFIG[DEFAULT_SPEAKER])

    async def generate_audio(self, text, speaker, output_path):
        config = self._voice_config_for(speaker)
        communicate = edge_tts.Communicate(
            text, config["voice"], rate=config["rate"], pitch=config["pitch"]
        )
        await communicate.save(output_path)

    def get_duration(self, filepath):
        try:
            audio = MP3(filepath)
            return audio.info.length
        except Exception as e:
            print(f"    Erreur duree audio: {e}")
            return 3.5

    async def process_script(self, scenes):
        for scene in scenes:
            scene_id = scene["id"]
            speaker = scene.get("speaker", DEFAULT_SPEAKER)
            text = scene["text"]
            output_path = os.path.join(self.audio_dir, f"scene_{scene_id}.mp3")

            voice = self._voice_config_for(speaker)["voice"]
            print(f"🗣️ Scene {scene_id} ({speaker}, {voice})...")
            await self.generate_audio(text, speaker, output_path)

            scene["audio_path"] = output_path
            duration = self.get_duration(output_path)
            if duration < 3.0:
                print(f"    Scene {scene_id} trop courte ({duration:.1f}s), duree forcee a 3.0s")
                duration = 3.0
            scene["duration"] = duration

        return scenes


if __name__ == "__main__":
    import asyncio

    async def _test():
        engine = KidsAudioEngine()
        fake_scenes = [
            {"id": 1, "speaker": "mimolune", "text": "Bonjour les amis, aujourd'hui c'est tres joli !"},
            {"id": 2, "speaker": "fruit_fraise", "text": "Regarde comme je suis rouge et sucree !"},
        ]
        result = await engine.process_script(fake_scenes)
        for scene in result:
            print(scene["id"], scene["duration"])

    asyncio.run(_test())