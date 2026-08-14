import os
import wave
import base64
import asyncio
import re
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
    # Profil principal Gemini : documentaire mystère premium.
    # Le prompt reste descriptif et naturel : on évite "very slow" / "high suspense"
    # qui peuvent produire une diction trop théâtrale ou artificiellement lente.
    GEMINI_NARRATOR_STYLE = (
        "French documentary narrator. Calm, deep, warm and authoritative. "
        "Premium mystery-documentary style, intimate and cinematic but realistic. "
        "Clear French diction, natural breathing, measured pacing, subtle suspense, "
        "controlled emotion, understated dramatic pauses. Never theatrical, never rushed."
    )

    GEMINI_WITNESS_STYLE = (
        "French documentary witness. Natural, credible and human. "
        "Slightly tense and intimate, as if recounting a disturbing event from memory. "
        "Clear diction, restrained emotion, conversational pacing. "
        "Do not sound like an actor or a news presenter."
    )

    # Fallback Edge : profils distincts et cohérents avec Gemini.
    EDGE_NARRATOR_VOICE = "fr-FR-ClaudeNeural"
    EDGE_NARRATOR_RATE = "-12%"
    EDGE_NARRATOR_PITCH = "-4Hz"
    EDGE_NARRATOR_VOLUME = "+0%"

    EDGE_WITNESS_VOICE = "fr-FR-JeromeNeural"
    EDGE_WITNESS_RATE = "-8%"
    EDGE_WITNESS_PITCH = "-2Hz"
    EDGE_WITNESS_VOLUME = "+0%"

    # Dernier recours local.
    KOKORO_FRENCH_VOICE = "ff_siwis"
    KOKORO_WITNESS_SPEED = 0.94
    KOKORO_NARRATOR_SPEED = 0.90

    # Voix Gemini TTS. Gemini 2.5 Flash TTS accepte les voix prédéfinies.
    GEMINI_NARRATOR_VOICE = "Charon"
    GEMINI_WITNESS_VOICE = "Orus"

    # Dictionnaire de correction phonétique pour la prononciation française
    PRONUNCIATION_DICT = {
        r"\bmythe\b": "mite",
        r"\bmythes\b": "mites",
        r"\bmythique\b": "mitique",
        r"\bmythiques\b": "mitiques",
        r"\bchâteau\b": "châto",
        r"\bchâteaux\b": "châtos",
        r"\bchaos\b": "kao",
        r"\bclimax\b": "climax",
        r"\bchœur\b": "keur",
        r"\bchœurs\b": "keurs",
        r"\barchéologue\b": "arkéologue",
        r"\barchéologues\b": "arkéologues",
        r"\barchéologie\b": "arkéologie",
        r"\barchéologique\b": "arkéologique",
        r"\barchéologiques\b": "arkéologiques",
        r"\barchétype\b": "arkétype",
        r"\barchétypes\b": "arkétypes",
        r"\bpsychose\b": "psycose",
        r"\bah\b": "ah",
    }

    # Remplacement des siècles et chiffres romains résiduels en toutes lettres
    ROMAN_NUMERALS_MAP = {
        r"\bXXI(?:e|ème|eme)?\s+siècle\b": "vingt et unième siècle",
        r"\bXX(?:e|ème|eme)?\s+siècle\b": "vingtième siècle",
        r"\bXIX(?:e|ème|eme)?\s+siècle\b": "dix-neuvième siècle",
        r"\bXVIII(?:e|ème|eme)?\s+siècle\b": "dix-huitième siècle",
        r"\bXVII(?:e|ème|eme)?\s+siècle\b": "dix-septième siècle",
        r"\bXVI(?:e|ème|eme)?\s+siècle\b": "seizième siècle",
        r"\bXV(?:e|ème|eme)?\s+siècle\b": "quinzième siècle",
        r"\bXIV(?:e|ème|eme)?\s+siècle\b": "quatorze",
        r"\bXIII(?:e|ème|eme)?\s+siècle\b": "treizième siècle",
        r"\bXII(?:e|ème|eme)?\s+siècle\b": "douzième siècle",
        r"\bXI(?:e|ème|eme)?\s+siècle\b": "onzième siècle",
        r"\bX(?:e|ème|eme)?\s+siècle\b": "dixième siècle",
        r"\bIX(?:e|ème|eme)?\s+siècle\b": "neuvième siècle",
        r"\bVIII(?:e|ème|eme)?\s+siècle\b": "huitième siècle",
        r"\bVII(?:e|ème|eme)?\s+siècle\b": "septième siècle",
        r"\bVI(?:e|ème|eme)?\s+siècle\b": "sixième siècle",
        r"\bV(?:e|ème|eme)?\s+siècle\b": "cinquième siècle",
        r"\bIV(?:e|ème|eme)?\s+siècle\b": "quatrième siècle",
        r"\bIII(?:e|ème|eme)?\s+siècle\b": "troisième siècle",
        r"\bII(?:e|ème|eme)?\s+siècle\b": "deuxième siècle",
        r"\bI(?:er|er|er)?\s+siècle\b": "premier siècle",
        r"\bLouis\s+XIV\b": "Louis quatorze",
        r"\bLouis\s+XV\b": "Louis quinze",
        r"\bLouis\s+XVI\b": "Louis seize",
        r"\bLouis\s+XIII\b": "Louis treize",
        r"\bNapoléon\s+Ier\b": "Napoléon premier",
        r"\bNapoléon\s+III\b": "Napoléon trois",
    }

    def __init__(self, bark_url=None, use_kokoro=True, use_gemini=True):
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

        self.min_scene_duration = 3.0
        self.use_gemini = use_gemini and bool(os.getenv("GEMINI_API_KEY"))
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        print(
            "      Gemini TTS: "
            + ("activé" if self.use_gemini else "désactivé")
            + f" | modèle={self.GEMINI_MODEL}"
        )

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
        # Nettoyage léger : la ponctuation doit rester disponible pour guider
        # naturellement le rythme du moteur TTS.
        text = text.replace("\u2014", ", ").replace("\u2013", ", ")
        text = re.sub(r"\.{4,}", "...", text)
        text = re.sub(r"\s+([,;:!?])", r"\1", text)
        text = re.sub(r"([,;:!?])(?=\S)", r"\1 ", text)
        return " ".join(text.split()).strip()

    def sanitize_for_phonetics(self, text):
        """
        Applique un dictionnaire de remplacement phonétique strict
        dédié uniquement au moteur audio (sans impacter les sous-titres visuels).
        """
        sanitized = self.clean_text(text)

        # 1. Remplacement des chiffres romains & siècles résiduels
        for pattern, replacement in self.ROMAN_NUMERALS_MAP.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        # 2. Remplacement des mots trompeurs pour la synthèse FR (ex: mythe -> mite)
        for pattern, replacement in self.PRONUNCIATION_DICT.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        # 3. Lissage des abréviations
        sanitized = re.sub(r"\bav\.\s*J\.-C\.\b", "avant Jésus-Christ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bap\.\s*J\.-C\.\b", "après Jésus-Christ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\benv\.\b", "environ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bkm\b", "kilomètres", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bm\b", "mètres", sanitized, flags=re.IGNORECASE)

        return sanitized

    def stylize_for_gemini(self, text, voice_type="narrator"):
        cleaned = self.sanitize_for_phonetics(text)

        if voice_type == "witness":
            style = self.GEMINI_WITNESS_STYLE
        else:
            style = self.GEMINI_NARRATOR_STYLE

        # Une instruction explicite mais courte. On évite les marqueurs [pause]
        # dans le texte, car le modèle gère mieux les pauses via la ponctuation
        # et le style vocal.
        return f"{style}\nRead this French text naturally:\n{cleaned}"

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

        speed = self.KOKORO_WITNESS_SPEED if voice_type == "witness" else self.KOKORO_NARRATOR_SPEED
        phonetic_text = self.sanitize_for_phonetics(text)

        try:
            generator = self._kokoro_pipeline(
                phonetic_text,
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
        """
        Gemini TTS principal.
        Retourne False proprement en cas de quota, modèle indisponible,
        réponse sans audio ou format inattendu afin de permettre le fallback.
        """
        if not self.use_gemini:
            print("      Gemini TTS désactivé (GEMINI_API_KEY absente ou use_gemini=False)")
            return False

        voice_name = (
            self.GEMINI_WITNESS_VOICE
            if voice_type == "witness"
            else self.GEMINI_NARRATOR_VOICE
        )

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.GEMINI_MODEL}:generateContent?key={self.gemini_api_key}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": self.stylize_for_gemini(
                                text, voice_type=voice_type
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }

        try:
            response = requests.post(url, json=payload, timeout=90)

            if response.status_code != 200:
                # On affiche le statut sans exposer la clé API.
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                except Exception:
                    error_msg = response.text[:300]

                print(
                    f"      Gemini TTS indisponible "
                    f"(HTTP {response.status_code}): {error_msg}"
                )
                return False

            data = response.json()
            parts = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )

            inline_data = None
            for part in parts:
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    break

            if not inline_data or not inline_data.get("data"):
                print("      Gemini TTS : aucune donnée audio dans la réponse")
                return False

            audio_bytes = base64.b64decode(inline_data["data"])
            mime_type = inline_data.get("mimeType", "").lower()

            # Gemini peut retourner du PCM brut ou un WAV.
            if "wav" in mime_type:
                with open(output_path_wav, "wb") as f:
                    f.write(audio_bytes)
            else:
                self._save_pcm_wav(
                    audio_bytes,
                    output_path_wav,
                    sample_rate=24000,
                    channels=1,
                    sampwidth=2,
                )

            if self._file_ready(output_path_wav):
                print(
                    f"      Voix Gemini TTS utilisée "
                    f"({voice_type}, voice={voice_name})"
                )
                return True

            print("      Gemini TTS : fichier audio invalide")
            return False

        except requests.RequestException as e:
            print(f"      Gemini TTS réseau indisponible: {e}")
            return False
        except Exception as e:
            print(f"      Gemini TTS erreur: {e}")
            return False

    async def _try_edge(self, text, output_path_mp3, voice_type="narrator"):
        if not EDGE_AVAILABLE:
            raise RuntimeError("edge_tts non installe")

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

        phonetic_text = self.sanitize_for_phonetics(text)

        communicate = edge_tts.Communicate(
            text=phonetic_text,
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

        # Priorité qualité :
        # 1. Gemini TTS : moteur principal premium
        # 2. Edge TTS : fallback très fiable et profils vocaux distincts
        # 3. Kokoro : dernier recours local
        #
        # Important : Gemini est tenté AVANT Kokoro. Le pipeline ne retombera
        # donc plus silencieusement sur Kokoro dès que celui-ci est disponible.

        if self._try_gemini(text, wav_path, voice_type=voice_type):
            return wav_path, "gemini-tts"

        try:
            await self._try_edge(text, mp3_path, voice_type=voice_type)
            if self._file_ready(mp3_path):
                print(f"      Fallback Edge TTS utilisé ({voice_type})")
                return mp3_path, "edge-tts"
        except Exception as e:
            print(f"      Edge TTS indisponible: {e}")

        if self._try_kokoro(text, wav_path, voice_type=voice_type):
            print(f"      Fallback Kokoro utilisé ({voice_type})")
            return wav_path, "kokoro"

        raise RuntimeError(
            f"Aucun moteur TTS disponible pour voice_type={voice_type}"
        )

    async def process_script(self, script_data):
        print("Génération audio documentaire (Gemini → Edge → Kokoro)...")

        for scene in script_data:
            scene_id = scene["id"]
            text = scene["text"]
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