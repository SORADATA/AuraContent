import os
import asyncio
import base64
import wave
import requests
import re
import ffmpeg
from mutagen.mp3 import MP3

try:
    import edge_tts
    EDGE_AVAILABLE = True
except ImportError:
    EDGE_AVAILABLE = False

try:
    import soundfile as sf
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False


class AudioEngine:
    GEMINI_MODEL = "gemini-2.5-flash-preview-tts"
    GEMINI_STYLE_PROMPT = (
        "French male professional narrator. Calm, poised, authoritative, rhetorical, persuasive. "
        "Measured pacing, deep tone, clear diction, confident business-finance delivery."
    )

    EDGE_VOICE = "fr-FR-HenriNeural"
    EDGE_RATE = "-8%"
    EDGE_PITCH = "+0Hz"
    EDGE_VOLUME = "+0%"

    KOKORO_FRENCH_VOICE = "ff_siwis"

    # --- Cible de normalisation par scène ---
    # On vise un peu SOUS le -16 LUFS final (appliqué globalement par le
    # Composer) pour laisser de la marge : chaque scène est ainsi
    # homogène en amont, et le loudnorm final du Composer n'a plus qu'à
    # ajuster finement plutôt que rattraper de gros écarts entre moteurs.
    SCENE_TARGET_LUFS = -19.0
    SCENE_TRUE_PEAK = -1.5
    SCENE_LRA = 11
    # Limiteur de sécurité (marge sous 0 dBFS) pour absorber tout pic
    # résiduel que loudnorm n'aurait pas totalement lissé — c'est
    # généralement la cause des "craquements" entendus en aval.
    SAFETY_LIMITER_LEVEL = 0.97

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
                self._kokoro_pipeline = KPipeline(lang_code="f", repo_id="hexgrad/Kokoro-82M")
                print("     Kokoro initialise")
            except Exception as e:
                print(f"     Kokoro indisponible: {e}")
                self.use_kokoro = False

    def clean_text(self, text):
        text = str(text)
        text = text.replace("\u2014", ", ").replace("\u2013", ", ")
        text = text.replace("...", ". ")
        text = text.replace(";", ", ")
        text = text.replace("(", ", ").replace(")", "")
        text = text.replace("[", "").replace("]", "")
        text = re.sub(r"[“”«»]", '"', text)
        text = re.sub(r"[•·]", ", ", text)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r",\s*,+", ", ", text)
        text = re.sub(r"\.\s*\.", ".", text)
        return text.strip()

    def get_audio_duration(self, file_path):
        """Mesure de durée fiable pour n'importe quel format audio.

        Le bug initial utilisait mutagen.mp3.MP3, qui ne sait lire QUE du
        MP3 : sur les fichiers .wav produits par Gemini/Kokoro, ça
        renvoyait silencieusement 0.0, forçant ensuite la scène à durer
        min_scene_duration au lieu de sa durée réelle (voix coupée en
        plein milieu, ou silences en trop côté vidéo).

        On utilise ffprobe (via ffmpeg-python) en priorité car il gère
        tous les formats de façon fiable ; mutagen sert de filet de
        secours pour les .mp3 si ffprobe n'est pas disponible.
        """
        try:
            probe = ffmpeg.probe(file_path)
            return float(probe["format"]["duration"])
        except Exception:
            pass

        if file_path.lower().endswith(".mp3"):
            try:
                return MP3(file_path).info.length
            except Exception:
                pass

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

    def _normalize_scene_audio(self, audio_path):
        """Normalise un clip TTS individuel (loudnorm) et lui applique un
        limiteur de sécurité pour éviter tout écrêtage/craquement, quel
        que soit le moteur TTS d'origine (Edge / Gemini / Kokoro ont des
        niveaux de sortie naturels très différents).

        Écrit dans un fichier temporaire puis remplace l'original en
        place, pour que le reste du pipeline (Composer) n'ait rien à
        changer.
        """
        ext = os.path.splitext(audio_path)[1].lower()
        base, _ = os.path.splitext(audio_path)
        tmp_path = f"{base}__norm{ext}"

        output_kwargs = {}
        if ext == ".wav":
            output_kwargs["acodec"] = "pcm_s16le"
        elif ext == ".mp3":
            output_kwargs["acodec"] = "libmp3lame"
            output_kwargs["audio_bitrate"] = "192k"

        try:
            (
                ffmpeg
                .input(audio_path)
                .filter("loudnorm", I=self.SCENE_TARGET_LUFS, TP=self.SCENE_TRUE_PEAK, LRA=self.SCENE_LRA)
                .filter("alimiter", limit=self.SAFETY_LIMITER_LEVEL)
                .output(tmp_path, **output_kwargs)
                .run(overwrite_output=True, quiet=True)
            )

            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                os.replace(tmp_path, audio_path)
                return True

            return False

        except ffmpeg.Error as e:
            error_log = e.stderr.decode("utf8") if e.stderr else str(e)
            print(f"     ⚠️ Normalisation scène échouée ({audio_path}): {error_log}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    def _try_gemini(self, text, output_path_wav):
        if not self.use_gemini:
            return False

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.GEMINI_MODEL}:generateContent?key={self.gemini_api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": f"{self.GEMINI_STYLE_PROMPT}\n\nText: {self.clean_text(text)}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"]}
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
                print("     Gemini TTS: aucune donnee audio")
                return False

            audio_bytes = base64.b64decode(inline_data["data"])
            mime_type = inline_data.get("mimeType", "").lower()

            if "wav" in mime_type:
                with open(output_path_wav, "wb") as f:
                    f.write(audio_bytes)
            else:
                self._save_pcm_wav(audio_bytes, output_path_wav)

            if os.path.exists(output_path_wav) and os.path.getsize(output_path_wav) > 0:
                print("     Voix Gemini TTS utilisee")
                return True
            return False

        except Exception as e:
            print(f"     Gemini TTS indisponible: {e}")
            return False

    def _try_kokoro(self, text, output_path_wav):
        if not self.use_kokoro or self._kokoro_pipeline is None:
            return False

        try:
            generator = self._kokoro_pipeline(self.clean_text(text), voice=self.KOKORO_FRENCH_VOICE)
            for _, _, audio in generator:
                sf.write(output_path_wav, audio, 24000)
                break

            if os.path.exists(output_path_wav) and os.path.getsize(output_path_wav) > 0:
                print("     Voix Kokoro utilisee")
                return True

            return False

        except Exception as e:
            print(f"     Kokoro indisponible: {e}")
            return False

    async def _try_edge(self, text, output_path_mp3):
        if not EDGE_AVAILABLE:
            raise RuntimeError("Le module edge_tts n'est pas installé.")

        communicate = edge_tts.Communicate(
            text=self.clean_text(text),
            voice=self.EDGE_VOICE,
            rate=self.EDGE_RATE,
            volume=self.EDGE_VOLUME,
            pitch=self.EDGE_PITCH,
        )
        await communicate.save(output_path_mp3)

    async def generate_audio(self, text, output_filename):
        base_name = output_filename.rsplit(".", 1)[0]
        wav_path = os.path.join(self.output_dir, base_name + ".wav")
        mp3_path = os.path.join(self.output_dir, base_name + ".mp3")

        try:
            await self._try_edge(text, mp3_path)
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                self._normalize_scene_audio(mp3_path)
                return mp3_path, "edge-tts"
        except Exception as e:
            print(f"     Edge indisponible: {e}")

        if self._try_gemini(text, wav_path):
            self._normalize_scene_audio(wav_path)
            return wav_path, "gemini-tts"

        if self._try_kokoro(text, wav_path):
            self._normalize_scene_audio(wav_path)
            return wav_path, "kokoro"

        raise RuntimeError("Aucun moteur TTS disponible")

    async def process_script(self, script_data):
        print("Generation audio (Edge-TTS male, fallback Gemini, puis Kokoro)...")

        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
            output_filename = f"scene_{scene_id}.mp3"

            audio_path, engine_used = await self.generate_audio(text, output_filename)
            scene["audio_path"] = audio_path
            scene["tts_engine"] = engine_used

            duration = self.get_audio_duration(audio_path)
            scene["duration"] = max(duration, self.min_scene_duration)

            print(f"     Scene {scene_id}: audio genere via {engine_used} ({scene['duration']:.2f}s)")

        return script_data
