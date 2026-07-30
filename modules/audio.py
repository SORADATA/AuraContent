
import os
import asyncio
import requests
import edge_tts
from mutagen.wave import WAVE
from mutagen.mp3 import MP3
import ffmpeg

try:
    from kokoro import KPipeline
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False


class AudioEngine:
    """
    Moteur audio hybride en cascade :
    1) Bark via tunnel Colab/ngrok (voix expressive, mais fragile).
    2) Kokoro TTS en local (gratuit, illimite, sans cle API, plus naturel
       qu'Edge-TTS, tourne sur CPU du runner).
    3) Edge-TTS en dernier recours (tres fiable mais son plus "IA").
    """

    EDGE_FALLBACK_VOICES = [
        "fr-FR-VivienneMultilingualNeural",
        "fr-FR-RemyMultilingualNeural",
        "fr-FR-HenriNeural",
        "fr-FR-DeniseNeural",
    ]

    KOKORO_FRENCH_VOICES = ["ff_siwis"]

    def __init__(self, bark_url=None, use_kokoro=True):
        raw_url = bark_url or os.getenv("BARK_NGROK_URL", "")
        self.base_url = raw_url.strip().rstrip("/")
        if self.base_url.endswith("/generate"):
            self.base_url = self.base_url[:-9]

        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

        self.edge_rate = "-27%"
        self.edge_volume = "+0%"
        self.edge_pitch = "-3Hz"

        self.min_scene_duration = 3.5

        self.use_kokoro = use_kokoro and KOKORO_AVAILABLE
        self._kokoro_pipeline = None
        if self.use_kokoro:
            try:
                self._kokoro_pipeline = KPipeline(lang_code="f")
                print("      Kokoro TTS initialise (voix francaise locale)")
            except Exception as e:
                print(f"      Impossible d'initialiser Kokoro: {e}")
                self.use_kokoro = False

    def clean_text(self, text):
        clean = text.replace("...", " ").replace("\u2014", " ").replace("\u2013", " ")
        return clean.strip()

    def add_dramatic_pauses(self, text):
        text = text.replace(". ", "... ")
        text = text.replace("? ", "?... ")
        text = text.replace("! ", "!... ")
        return text

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

    def pad_to_min_duration(self, file_path, min_duration):
        current_duration = self.get_audio_duration(file_path)
        if current_duration <= 0 or current_duration >= min_duration:
            return current_duration

        temp_path = file_path + ".pad.tmp" + os.path.splitext(file_path)[1]
        try:
            (
                ffmpeg
                .input(file_path)
                .filter("apad", whole_dur=min_duration)
                .output(temp_path)
                .overwrite_output()
                .run(quiet=True)
            )
            if os.path.exists(temp_path):
                os.replace(temp_path, file_path)
                return min_duration
        except Exception as e:
            print(f"      Echec apad: {e}")
        return current_duration

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

            print(f"      Bark indisponible (status {response.status_code}), on tente Kokoro/Edge-TTS")
            return False

        except Exception as e:
            print(f"      Bark injoignable ({e}), on tente Kokoro/Edge-TTS")
            return False

    def _try_kokoro(self, text, output_path_wav):
        """
        Genere la voix localement avec Kokoro TTS (gratuit, illimite,
        aucune cle API, tourne sur CPU). Plus naturel qu'Edge-TTS.
        """
        if not self.use_kokoro or self._kokoro_pipeline is None:
            return False

        cleaned_text = self.add_dramatic_pauses(self.clean_text(text))

        try:
            generator = self._kokoro_pipeline(cleaned_text, voice=self.KOKORO_FRENCH_VOICES[0])
            for _, _, audio in generator:
                sf.write(output_path_wav, audio, 24000)
                break
            if os.path.exists(output_path_wav) and os.path.getsize(output_path_wav) > 0:
                print(f"      Voix Kokoro TTS utilisee (locale, gratuite)")
                self.trim_silence(output_path_wav)
                return True
            return False
        except Exception as e:
            print(f"      Echec Kokoro: {e}, fallback Edge-TTS")
            return False

    async def _try_edge(self, text, output_path_mp3):
        cleaned_text = self.add_dramatic_pauses(self.clean_text(text))
        last_error = None
        for voice in self.EDGE_FALLBACK_VOICES:
            try:
                communicate = edge_tts.Communicate(
                    cleaned_text,
                    voice,
                    rate=self.edge_rate,
                    volume=self.edge_volume,
                    pitch=self.edge_pitch,
                )
                await communicate.save(output_path_mp3)
                if os.path.exists(output_path_mp3) and os.path.getsize(output_path_mp3) > 0:
                    print(f"      Voix Edge-TTS utilisee : {voice} (rate={self.edge_rate}, pitch={self.edge_pitch})")
                    return True
                raise RuntimeError("Fichier audio vide")
            except Exception as e:
                print(f"      Echec {voice}: {e}")
                last_error = e
                continue
        raise RuntimeError(f"Toutes les voix Edge-TTS ont echoue: {last_error}")

    async def generate_audio(self, text, output_filename):
        wav_path = os.path.join(self.output_dir, output_filename.rsplit(".", 1)[0] + ".wav")

        if self._try_bark(text, wav_path):
            return wav_path, "bark"

        if self._try_kokoro(text, wav_path):
            return wav_path, "kokoro"

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
        print("Generation audio (Bark cloud, fallback Kokoro local, puis Edge-TTS)...")

        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
            filename = f"voice_{scene_id}.wav"

            try:
                file_path, engine_used = await self.generate_audio(text, filename)
                duration = self.get_audio_duration(file_path)

                if duration < self.min_scene_duration:
                    duration = self.pad_to_min_duration(file_path, self.min_scene_duration)
                    if duration < self.min_scene_duration:
                        duration = self.min_scene_duration

                scene["audio_path"] = file_path
                scene["duration"] = duration
                scene["voice_engine"] = engine_used
                print(f"   Scene {scene_id}: {duration:.2f}s ({engine_used})")
            except Exception as e:
                print(f"   Echec total Scene {scene_id}: {e}")
                scene["audio_path"] = None
                scene["duration"] = self.min_scene_duration

        return script_data

