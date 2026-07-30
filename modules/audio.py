
import os
import asyncio
import requests
import edge_tts
from mutagen.wave import WAVE
from mutagen.mp3 import MP3
import ffmpeg


class AudioEngine:
    """
    Moteur audio hybride :
    1) Essaie d'abord Bark via le tunnel Colab/ngrok (voix plus expressive).
    2) Si le tunnel est down, timeout, 404 ou erreur serveur -> fallback
       automatique sur Edge-TTS (gratuit, local, tres fiable) pour ne
       jamais bloquer la pipeline a cause d'un ngrok expire.
    """

    EDGE_FALLBACK_VOICES = [
        "fr-FR-VivienneMultilingualNeural",
        "fr-FR-RemyMultilingualNeural",
        "fr-FR-HenriNeural",
        "fr-FR-DeniseNeural",
    ]

    def __init__(self, bark_url=None):
        raw_url = bark_url or os.getenv("BARK_NGROK_URL", "")
        self.base_url = raw_url.strip().rstrip("/")
        if self.base_url.endswith("/generate"):
            self.base_url = self.base_url[:-9]

        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

        self.edge_rate = "-15%"
        self.edge_volume = "-15%"

    def clean_text(self, text):
        clean = text.replace("...", " ").replace("\u2014", " ").replace("\u2013", " ")
        return clean.strip()

    def trim_silence(self, file_path):
        temp_path = file_path.replace(".wav", "_temp.wav")
        try:
            (
                ffmpeg
                .input(file_path)
                .filter("areverse")
                .filter("silenceremove", start_periods=1, start_silence=0.1, start_threshold="-50dB")
                .filter("areverse")
                .filter("volume", 1.5)
                .output(temp_path)
                .overwrite_output()
                .run(quiet=True)
            )
            if os.path.exists(temp_path):
                os.replace(temp_path, file_path)
        except Exception as e:
            print(f"      Echec du trim silence: {e}")

    def _try_bark(self, text, output_path):
        if not self.base_url:
            return False

        api_url = f"{self.base_url}/generate"
        cleaned_text = self.clean_text(text)
        payload = {
            "text": cleaned_text,
            "voice_preset": "v2/en_speaker_9",
            "text_temp": 0.7,
        }

        print(f"      Bark (Colab): {cleaned_text[:25]}...")

        try:
            response = requests.post(api_url, json=payload, timeout=60)
            if response.status_code == 200 and len(response.content) > 2000:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                self.trim_silence(output_path)
                return True

            print(f"      Bark indisponible (status {response.status_code}), fallback Edge-TTS")
            return False

        except Exception as e:
            print(f"      Bark injoignable ({e}), fallback Edge-TTS")
            return False

    async def _try_edge(self, text, output_path_mp3):
        last_error = None
        for voice in self.EDGE_FALLBACK_VOICES:
            try:
                communicate = edge_tts.Communicate(
                    text, voice, rate=self.edge_rate, volume=self.edge_volume
                )
                await communicate.save(output_path_mp3)
                if os.path.exists(output_path_mp3) and os.path.getsize(output_path_mp3) > 0:
                    print(f"      Voix Edge-TTS utilisee : {voice}")
                    return True
                raise RuntimeError("Fichier audio vide")
            except Exception as e:
                print(f"      Echec {voice}: {e}")
                last_error = e
                continue
        raise RuntimeError(f"Toutes les voix Edge-TTS ont echoue: {last_error}")

    async def generate_audio(self, text, output_filename):
        wav_path = os.path.join(self.output_dir, output_filename.rsplit(".", 1)[0] + ".wav")

        bark_ok = self._try_bark(text, wav_path)
        if bark_ok:
            return wav_path, "bark"

        mp3_path = os.path.join(self.output_dir, output_filename.rsplit(".", 1)[0] + ".mp3")
        await self._try_edge(text, mp3_path)
        return mp3_path, "edge-tts"

    def get_audio_duration(self, file_path):
        try:
            if file_path.endswith(".wav"):
                audio = WAVE(file_path)
            else:
                audio = MP3(file_path)
            return audio.info.length
        except Exception as e:
            print(f"Erreur lecture duree audio: {e}")
            return 0.0

    async def process_script(self, script_data):
        print("Generation audio (Bark cloud avec fallback Edge-TTS)...")

        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
            filename = f"voice_{scene_id}.wav"

            try:
                file_path, engine_used = await self.generate_audio(text, filename)
                duration = self.get_audio_duration(file_path)
                if duration < 3.5:
                    duration = 3.5
                scene["audio_path"] = file_path
                scene["duration"] = duration
                scene["voice_engine"] = engine_used
                print(f"   Scene {scene_id}: {duration:.2f}s ({engine_used})")
            except Exception as e:
                print(f"   Echec total Scene {scene_id}: {e}")
                scene["audio_path"] = None
                scene["duration"] = 3.5

        return script_data

