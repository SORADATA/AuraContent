import os
import wave
import audioop
import asyncio
import subprocess
import edge_tts
from mutagen.mp3 import MP3

# Une voix / vitesse / hauteur par type de personnage.
# fr-FR-DeniseNeural : voix chaleureuse et posee, utilisee pour Mimolune.
# fr-FR-EloiseNeural : voix plus aigue et enjouee, utilisee pour les fruits.
VOICE_CONFIG = {
    "mimolune": {"voice": "fr-FR-DeniseNeural", "rate": "-5%", "pitch": "+0Hz"},
    "fruit_fraise": {"voice": "fr-FR-EloiseNeural", "rate": "+5%", "pitch": "+20Hz"},
    "fruit_banane": {"voice": "fr-FR-EloiseNeural", "rate": "+10%", "pitch": "-10Hz"},
}
DEFAULT_SPEAKER = "mimolune"

# Duree d'une tranche d'analyse audio, en millisecondes.
# Plus la valeur est basse, plus la bouche reagit finement, mais plus il y a
# de changements d'image a generer par scene_animator.py.
CHUNK_MS = 120


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

    def _mp3_to_wav(self, mp3_path, wav_path):
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    def compute_mouth_envelope(self, audio_path, chunk_ms=CHUNK_MS):
        """
        Convertit le mp3 en wav mono via ffmpeg, puis calcule le volume (RMS)
        sur des tranches de chunk_ms millisecondes. Retourne une liste de
        valeurs normalisees entre 0.0 (silence) et 1.0 (volume max de la ligne).
        scene_animator.py se sert de cette liste pour choisir la forme de
        bouche a afficher a chaque instant.
        """
        wav_path = audio_path.replace(".mp3", "_tmp.wav")
        try:
            self._mp3_to_wav(audio_path, wav_path)
            with wave.open(wav_path, "rb") as wf:
                framerate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                chunk_frames = max(1, int(framerate * chunk_ms / 1000))

                envelope = []
                while True:
                    frames = wf.readframes(chunk_frames)
                    if not frames:
                        break
                    envelope.append(audioop.rms(frames, sampwidth))
        except Exception as e:
            print(f"    ⚠️ Impossible de calculer l'enveloppe audio : {e}")
            return []
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

        if not envelope:
            return []

        max_rms = max(envelope) or 1
        return [round(v / max_rms, 3) for v in envelope]

    @staticmethod
    def mouth_shape_for_value(value):
        """Traduit une valeur d'amplitude (0.0-1.0) en forme de bouche."""
        if value < 0.15:
            return "fermee"
        if value < 0.55:
            return "mi_ouverte"
        return "ouverte"

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

            scene["mouth_envelope"] = self.compute_mouth_envelope(output_path)
            scene["mouth_chunk_ms"] = CHUNK_MS

        return scenes


if __name__ == "__main__":
    async def _test():
        engine = KidsAudioEngine()
        fake_scenes = [
            {"id": 1, "speaker": "mimolune", "text": "Bonjour les amis, aujourd'hui c'est tres joli !"},
            {"id": 2, "speaker": "fruit_fraise", "text": "Regarde comme je suis rouge et sucree !"},
        ]
        result = await engine.process_script(fake_scenes)
        for scene in result:
            print(scene["id"], scene["duration"], len(scene["mouth_envelope"]), "tranches")

    asyncio.run(_test())