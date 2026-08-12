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
        "French professional narrator. Calm, elegant, warm, premium, natural. "
        "Clear diction, slightly deep tone, controlled pacing, short pauses, "
        "cinematic but not theatrical."
    )

    # === CORRECTIF : deux profils Edge distincts selon le voice_type ===
    # NARRATOR : voix féminine calme, cohérente avec Kokoro (ff_siwis) en repli.
    EDGE_NARRATOR_VOICE = "fr-FR-DeniseNeural"
    EDGE_NARRATOR_RATE = "-8%"
    EDGE_NARRATOR_PITCH = "-1Hz"
    EDGE_NARRATOR_VOLUME = "+0%"

    # WITNESS : voix masculine, un peu plus rythmée/punchy pour dynamiser
    # les citations/phrases choc, en contraste volontaire avec le narrator.
    EDGE_WITNESS_VOICE = "fr-FR-HenriNeural"
    EDGE_WITNESS_RATE = "+4%"
    EDGE_WITNESS_PITCH = "+2Hz"
    EDGE_WITNESS_VOLUME = "+0%"

    KOKORO_FRENCH_VOICE = "ff_siwis"
    # Vitesse Kokoro légèrement augmentée pour les scènes "witness" quand
    # Kokoro est utilisé en dernier recours, afin de garder un minimum
    # de contraste même sans changer de voix.
    KOKORO_WITNESS_SPEED = 1.08
    KOKORO_NARRATOR_SPEED = 1.0

    def __init__(self, bark_url=None, use_kokoro=True, use_gemini=True):
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
                print("      Kokoro initialise avec succès")
            except Exception as e:
                print(f"      Kokoro indisponible: {e}")
                self.use_kokoro = False

    def clean_text(self, text):
        text = text.replace("\u2014", ", ").replace("\u2013", ", ")
        text = text.replace("...", ". ")
        return " ".join(text.split()).strip()

    def stylize_for_gemini(self, text, voice_type="narrator"):
        cleaned = self.clean_text(text)
        # CORRECTIF : on adapte le prompt de style Gemini selon le voice_type
        if voice_type == "witness":
            style = (
                "French voice, punchy, more energetic and expressive, slightly "
                "faster pacing, like a striking quote or testimony."
            )
        else:
            style = self.GEMINI_STYLE_PROMPT
        return f"{style} [short pause] {cleaned}"

    def get_audio_duration(self, file_path):
        try:
            if file_path.endswith(".mp3"):
                return MP3(file_path).info.length
            info = sf.info(file_path)
            return float(info.duration)
        except Exception:
            return 0.0

    def _file_ready(self, path):
        return os.path.exists(path) and os.path.getsize(path) > 0 and self.get_audio_duration(path) > 0

    def _save_pcm_wav(self, pcm_bytes, output_path, sample_rate=24000, channels=1, sampwidth=2):
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

    def _try_kokoro(self, text, output_path_wav, voice_type="narrator"):
        if not self.use_kokoro or self._kokoro_pipeline is None:
            return False

        # CORRECTIF : légère variation de vitesse selon le voice_type,
        # seul levier disponible puisque Kokoro n'a qu'une voix FR.
        speed = self.KOKORO_WITNESS_SPEED if voice_type == "witness" else self.KOKORO_NARRATOR_SPEED

        try:
            generator = self._kokoro_pipeline(
                self.clean_text(text),
                voice=self.KOKORO_FRENCH_VOICE,
                speed=speed
            )
            for _, _, audio in generator:
                sf.write(output_path_wav, audio, 24000)
                break

            if self._file_ready(output_path_wav):
                print(f"      Voix Kokoro utilisée ({voice_type}, speed={speed})")
                return True

            return False

        except Exception as e:
            print(f"      Kokoro erreur: {e}")
            return False

    def _try_gemini(self, text, output_path_wav, voice_type="narrator"):
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
                            "text": self.stylize_for_gemini(text, voice_type=voice_type)
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
                return False

            audio_bytes = base64.b64decode(inline_data["data"])
            mime_type = inline_data.get("mimeType", "")

            if "wav" in mime_type:
                with open(output_path_wav, "wb") as f:
                    f.write(audio_bytes)
            else:
                self._save_pcm_wav(audio_bytes, output_path_wav)

            if self._file_ready(output_path_wav):
                print(f"      Voix Gemini TTS utilisée ({voice_type})")
                return True

            return False

        except Exception as e:
            # On log en simplicitė pour ne pas polluer la console avec les erreurs 429
            return False

    async def _try_edge(self, text, output_path_mp3, voice_type="narrator"):
        if not EDGE_AVAILABLE:
            raise RuntimeError("edge_tts non installe")

        # CORRECTIF : choix de la voix/réglages Edge selon le voice_type
        if voice_type == "witness":
            voice = self.EDGE_WITNESS_VOICE
            rate = self.EDGE_WITNESS_RATE
            pitch = self.EDGE_WITNESS_PITCH
            volume = self.EDGE_WITNESS_VOLUME
        else:
            voice = self.EDGE_NARRATOR_VOICE
            rate = self.EDGE_NARRATOR_RATE
            pitch = self.EDGE_NARRATOR_PITCH
            volume = self.EDGE_NARRATOR_VOLUME

        communicate = edge_tts.Communicate(
            text=self.clean_text(text),
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )
        await communicate.save(output_path_mp3)

    async def generate_audio(self, text, output_filename, voice_type="narrator"):
        base_name = output_filename.rsplit(".", 1)[0]
        wav_path = os.path.join(self.output_dir, base_name + ".wav")
        mp3_path = os.path.join(self.output_dir, base_name + ".mp3")

        # === CORRECTIF : ordre des moteurs adapté selon voice_type ===
        # narrator -> Kokoro (voix dédiée) prioritaire, cohérent avec le style calme.
        # witness  -> Edge-TTS (voix masculine punchy) prioritaire pour un vrai
        #             contraste vocal, Kokoro n'ayant qu'une seule voix FR.
        if voice_type == "witness":
            try:
                await self._try_edge(text, mp3_path, voice_type=voice_type)
                if self._file_ready(mp3_path):
                    return mp3_path, "edge-tts"
            except Exception as e:
                print(f"      Edge indisponible: {e}")

            if self._try_gemini(text, wav_path, voice_type=voice_type):
                return wav_path, "gemini-tts"

            if self._try_kokoro(text, wav_path, voice_type=voice_type):
                return wav_path, "kokoro"

        else:
            if self._try_kokoro(text, wav_path, voice_type=voice_type):
                return wav_path, "kokoro"

            if self._try_gemini(text, wav_path, voice_type=voice_type):
                return wav_path, "gemini-tts"

            try:
                await self._try_edge(text, mp3_path, voice_type=voice_type)
                if self._file_ready(mp3_path):
                    return mp3_path, "edge-tts"
            except Exception as e:
                print(f"      Edge indisponible: {e}")

        raise RuntimeError("Aucun moteur TTS disponible")

    async def process_script(self, script_data):
        print("Génération audio fluide (Priorité Kokoro/Edge selon voice_type)...")

        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
            # CORRECTIF : on lit le voice_type défini par ContentBrain
            voice_type = scene.get("voice_type", "narrator")
            if voice_type not in ("narrator", "witness"):
                voice_type = "narrator"

            output_filename = f"scene_{scene_id}.wav"

            audio_path, engine_used = await self.generate_audio(
                text, output_filename, voice_type=voice_type
            )

            scene["audio_path"] = audio_path
            scene["tts_engine"] = engine_used

            duration = self.get_audio_duration(audio_path)
            scene["duration"] = max(duration, self.min_scene_duration)

            print(
                f"     Scene {scene_id} [{voice_type}]: audio genere via {engine_used} "
                f"({scene['duration']:.2f}s)"
            )

        return script_data
