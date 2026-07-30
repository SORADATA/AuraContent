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
    Moteur audio hybride :
    1) Essaie d'abord Bark via le tunnel Colab/ngrok (voix plus expressive).
    2) Si le tunnel est down, timeout, 404 ou erreur serveur -> fallback
       automatique sur Edge-TTS (gratuit, local, tres fiable) pour ne
       jamais bloquer la pipeline a cause d'un ngrok expire.
    Moteur audio hybride en cascade :
    1) Bark via tunnel Colab/ngrok (voix expressive, mais fragile).
    2) Kokoro TTS en local (gratuit, illimite, sans cle API, plus naturel
       qu'Edge-TTS, tourne sur CPU du runner).
    3) Edge-TTS en dernier recours (tres fiable mais son plus "IA").
    """

    EDGE_FALLBACK_VOICES = [
@@ -24,7 +31,9 @@ class AudioEngine:
        "fr-FR-DeniseNeural",
    ]

    def __init__(self, bark_url=None):
    KOKORO_FRENCH_VOICES = ["ff_siwis"]

    def __init__(self, bark_url=None, use_kokoro=True):
        raw_url = bark_url or os.getenv("BARK_NGROK_URL", "")
        self.base_url = raw_url.strip().rstrip("/")
        if self.base_url.endswith("/generate"):
@@ -33,29 +42,27 @@ def __init__(self, bark_url=None):
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

        # Debit ralenti et pitch abaisse pour un ton de confession/mystere.
        # -15% etait trop subtil, -27% donne un rythme nettement plus pose
        # sans devenir robotique ou trop lent a l'oreille.
        self.edge_rate = "-27%"
        self.edge_volume = "+0%"
        self.edge_pitch = "-3Hz"

        # Duree plancher minimale d'une scene, et duree de silence ajoutee
        # (au fichier audio lui-meme, pas seulement a la video) pour eviter
        # tout desynchro audio/video quand une phrase est courte.
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
        """
        Insere de courtes pauses (virgules) apres les points pour ralentir
        le phrase, en complement du rate global. Edge-TTS ne supporte pas
        le SSML <break> arbitraire via Communicate(), donc on joue sur la
        ponctuation qui influence naturellement le moteur prosodique.
        """
        text = text.replace(". ", "... ")
        text = text.replace("? ", "?... ")
        text = text.replace("! ", "!... ")
@@ -81,11 +88,6 @@ def trim_silence(self, file_path):
            print(f"      Echec du trim silence: {e}")

    def pad_to_min_duration(self, file_path, min_duration):
        """
        Ajoute du vrai silence a la fin du fichier audio (pas seulement a
        la video) si sa duree est inferieure au minimum souhaite. Evite
        toute impression de precipitation due a un mismatch audio/video.
        """
        current_duration = self.get_audio_duration(file_path)
        if current_duration <= 0 or current_duration >= min_duration:
            return current_duration
@@ -129,11 +131,35 @@ def _try_bark(self, text, output_path):
                self.trim_silence(output_path)
                return True

            print(f"      Bark indisponible (status {response.status_code}), fallback Edge-TTS")
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
            print(f"      Bark injoignable ({e}), fallback Edge-TTS")
            print(f"      Echec Kokoro: {e}, fallback Edge-TTS")
            return False

    async def _try_edge(self, text, output_path_mp3):
@@ -162,10 +188,12 @@ async def _try_edge(self, text, output_path_mp3):
    async def generate_audio(self, text, output_filename):
        wav_path = os.path.join(self.output_dir, output_filename.rsplit(".", 1)[0] + ".wav")

        bark_ok = self._try_bark(text, wav_path)
        if bark_ok:
        if self._try_bark(text, wav_path):
            return wav_path, "bark"

        if self._try_kokoro(text, wav_path):
            return wav_path, "kokoro"

        mp3_path = os.path.join(self.output_dir, output_filename.rsplit(".", 1)[0] + ".mp3")
        await self._try_edge(text, mp3_path)
        return mp3_path, "edge-tts"
@@ -182,7 +210,7 @@ def get_audio_duration(self, file_path):
            return 0.0

    async def process_script(self, script_data):
        print("Generation audio (Bark cloud avec fallback Edge-TTS)...")
        print("Generation audio (Bark cloud, fallback Kokoro local, puis Edge-TTS)...")

        for scene in script_data:
            scene_id = scene["id"]
