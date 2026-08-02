import os
import wave
import base64
import asyncio
import requests
from mutagen.mp3 import MP3

try:
    import edge_tts
    EDGE_AVAILABLE = True
except ImportError:
    EDGE_AVAILABLE = False

try:
    from kokoro import KPipeline
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False


class AudioEngine:
    GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
    GEMINI_STYLE_PROMPT = (
        "French male professional narrator. Calm, elegant, warm, premium, natural. "
        "Clear diction, slightly deep tone, controlled pacing, short pauses, "
        "cinematic but not theatrical."
    )

    EDGE_FALLBACK_VOICE = "fr-FR-HenriNeural"
    EDGE_FALLBACK_RATE = "-8%"
    EDGE_FALLBACK_PITCH = "-1Hz"
    EDGE_FALLBACK_VOLUME = "+0%"

    KOKORO_FRENCH_VOICE = "ff_siwis"

    # Modification ici: use_kokoro passe sur False par défaut pour éviter la seule voix (féminine) dispo sur Kokoro en français.
    def __init__(self, bark_url=None, use_kokoro=False, use_gemini=True):
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

        self.min_scene_duration = 3.0

        self.use_gemini = use_gemini and bool(os.getenv("GEMINI_API_KEY"))
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")

        self.use_kokoro = use_kokoro and KOKORO_AVAILABLE
        self._kokoro_pipeline = None
        if self.use_kokoro:
            try:
                self._kokoro_pipeline = KPipeline(
                    lang_code="f",
                    repo_id="hexgrad/Kokoro-82M"
                )
                print("      Kokoro initialise")
            except Exception as e:
                print(f"      Kokoro indisponible: {e}")
                self.use_kokoro = False

    def clean_text(self, text):
        text = text.replace("\u2014", ", ").replace("\u2013", ", ")
        text = text.replace("...", ". ")
        return " ".join(text.split()).strip()

    def stylize_for_gemini(self, text):
        cleaned = self.clean_text(text)
        return f"{self.GEMINI_STYLE_PROMPT} [short pause] {cleaned}"

    def get_audio_duration(self, file_path):
        try:
            if file_path.endswith(".mp3"):
                return MP3(file_path).info.length
            info = sf.info(file_path)
            return float(info.duration)
        except Exception:
            return 0.0

    def trim_silence(self, file_path):
        return

    def pad_to_min_duration(self, file_path, min_duration):
        current_duration = self.get_audio_duration(file_path)
        return max(current_duration, min_duration)

    def _save_pcm_wav(self, pcm_bytes, output_path, sample_rate=24000, channels=1, sampwidth=2):
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

    def _try_gemini(self, text, output_path_wav):
        if not self.use_gemini:
            return False

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.GEMINI_MODEL}:generateContent?key={self.gemini_api_key}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": self.stylize_for_gemini(text)
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"]
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=90)
            response.raise_for_status()
            data = response.json()

            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            inline_data = None

            for part in parts:
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    break

            if not inline_data:
                print("      Gemini TTS: aucune donnee audio")
                return False

            audio_bytes = base64.b64decode(inline_data["data"])
            mime_type = inline_data.get("mimeType", "")

            if "wav" in mime_type:
                with open(output_path_wav, "wb") as f:
                    f.write(audio_bytes)
            else:
                self._save_pcm_wav(audio_bytes, output_path_wav)

            if os.path.exists(output_path_wav) and os.path.getsize(output_path_wav) > 0:
                print("      Voix Gemini TTS utilisee")
                return True

            return False

        except Exception as e:
            print(f"      Gemini TTS indisponible: {e}")
            return False

    def _try_kokoro(self, text, output_path_wav):
        if not self.use_kokoro or self._kokoro_pipeline is None:
            return False

        try:
            generator = self._kokoro_pipeline(
                self.clean_text(text),
                voice=self.KOKORO_FRENCH_VOICE
            )
            for _, _, audio in generator:
                sf.write(output_path_wav, audio, 24000)
                break

            if os.path.exists(output_path_wav) and os.path.getsize(output_path_wav) > 0:
                print("      Voix Kokoro utilisee")
                return True

            return False

        except Exception as e:
            print(f"      Kokoro indisponible: {e}")
            return False

    async def _try_edge(self, text, output_path_mp3):
        if not EDGE_AVAILABLE:
            raise RuntimeError("edge_tts non installe")

        communicate = edge_tts.Communicate(
            text=self.clean_text(text),
            voice=self.EDGE_FALLBACK_VOICE,
            rate=self.EDGE_FALLBACK_RATE,
            volume=self.EDGE_FALLBACK_VOLUME,
            pitch=self.EDGE_FALLBACK_PITCH,
        )
        await communicate.save(output_path_mp3)

    async def generate_audio(self, text, output_filename):
        base_name = output_filename.rsplit(".", 1)[0]
        wav_path = os.path.join(self.output_dir, base_name + ".wav")
        mp3_path = os.path.join(self.output_dir, base_name + ".mp3")

        if self._try_gemini(text, wav_path):
            return wav_path, "gemini-tts"

        if self._try_kokoro(text, wav_path):
            return wav_path, "kokoro"

        try:
            await self._try_edge(text, mp3_path)
            return mp3_path, "edge-tts"
        except Exception as e:
            print(f"      Edge indisponible: {e}")

        raise RuntimeError("Aucun moteur TTS disponible")

    async def process_script(self, script_data):
        print("Generation audio (Gemini TTS, fallback Kokoro, puis Edge-TTS)...")

        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
            output_filename = f"scene_{scene_id}.wav"

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
