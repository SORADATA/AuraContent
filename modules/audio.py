import os
import re
import asyncio
import time
from mutagen.mp3 import MP3

try:
    import edge_tts
except ImportError:
    raise RuntimeError("Le module edge_tts est requis. (pip install edge-tts)")

class AudioEngine:
    """
    Generateur audio strict a 2 voix (Narrateur / Temoin).
    Garantit une coherence vocale totale sur toute la video.
    """

    PRONUNCIATION_DICT = {
        r"\bmythe\b": "mite",
        r"\bmythes\b": "mites",
        r"\bmythique\b": "mitique",
        r"\bmythiques\b": "mitiques",
        r"\bch\u00e2teau\b": "ch\u00e2to",
        r"\bch\u00e2teaux\b": "ch\u00e2tos",
        r"\bchaos\b": "kao",
        r"\bclimax\b": "climax",
        r"\bch\u0153ur\b": "keur",
        r"\bch\u0153urs\b": "keurs",
        r"\barch\u00e9ologue\b": "ark\u00e9ologue",
        r"\barch\u00e9ologues\b": "ark\u00e9ologues",
        r"\barch\u00e9ologie\b": "ark\u00e9ologie",
        r"\barch\u00e9ologique\b": "ark\u00e9ologique",
        r"\barch\u00e9ologiques\b": "ark\u00e9ologiques",
        r"\barch\u00e9type\b": "ark\u00e9type",
        r"\barch\u00e9types\b": "ark\u00e9types",
        r"\bpsychose\b": "psycose",
        r"\bah\b": "ah",
    }

    ROMAN_NUMERALS_MAP = {
        r"\bXXI(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "vingt et unieme siecle",
        r"\bXX(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "vingtieme siecle",
        r"\bXIX(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "dix-neuvieme siecle",
        r"\bXVIII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "dix-huitieme siecle",
        r"\bXVII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "dix-septieme siecle",
        r"\bXVI(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "seizieme siecle",
        r"\bXV(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "quinzieme siecle",
        r"\bXIV(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "quatorzieme siecle",
        r"\bXIII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "treizieme siecle",
        r"\bXII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "douzieme siecle",
        r"\bXI(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "onzieme siecle",
        r"\bX(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "dixieme siecle",
        r"\bIX(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "neuvieme siecle",
        r"\bVIII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "huitieme siecle",
        r"\bVII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "septieme siecle",
        r"\bVI(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "sixieme siecle",
        r"\bV(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "cinquieme siecle",
        r"\bIV(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "quatrieme siecle",
        r"\bIII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "troisieme siecle",
        r"\bII(?:e|\u00e8me|eme)?\s+si\u00e8cle\b": "deuxieme siecle",
        r"\bI(?:er|er|er)?\s+si\u00e8cle\b": "premier siecle",
        r"\bLouis\s+XIV\b": "Louis quatorze",
        r"\bLouis\s+XV\b": "Louis quinze",
        r"\bLouis\s+XVI\b": "Louis seize",
        r"\bLouis\s+XIII\b": "Louis treize",
        r"\bNapol\u00e9on\s+Ier\b": "Napoleon premier",
        r"\bNapol\u00e9on\s+III\b": "Napoleon trois",
    }

    def __init__(self):
        self.audio_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.audio_dir, exist_ok=True)
        self.min_scene_duration = 3.0

        # Timeout (secondes) applique a chaque appel edge_tts.Communicate.save().
        # CORRECTIF : edge_tts n'a pas de timeout interne. Si le websocket
        # Microsoft ne repond jamais (latence reseau, throttling silencieux
        # cote CI, etc.), l'await restait bloque INDEFINIMENT sans lever
        # d'exception ni logguer quoi que ce soit -- ce qui provoquait des
        # runs bloques 40+ minutes jusqu'au timeout du job CI. On borne
        # desormais explicitement l'appel avec asyncio.wait_for.
        self.tts_timeout = 30

        self.VOICE_NARRATOR = "fr-FR-HenriNeural"
        self.RATE_NARRATOR = "-12%"
        self.PITCH_NARRATOR = "-4Hz"

        self.VOICE_WITNESS = "fr-FR-ClaudeNeural"
        self.RATE_WITNESS = "-8%"
        self.PITCH_WITNESS = "-2Hz"

    def clean_text(self, text):
        text = text.replace("\u2014", ", ").replace("\u2013", ", ")
        text = re.sub(r"\.{4,}", "...", text)
        text = re.sub(r"\s+([,;:!?])", r"\1", text)
        text = re.sub(r"([,;:!?])(?=\S)", r"\1 ", text)
        return " ".join(text.split()).strip()

    def sanitize_for_phonetics(self, text):
        sanitized = self.clean_text(text)

        for pattern, replacement in self.ROMAN_NUMERALS_MAP.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        for pattern, replacement in self.PRONUNCIATION_DICT.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        sanitized = re.sub(r"\bav\.\s*J\.-C\.\b", "avant Jesus-Christ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bap\.\s*J\.-C\.\b", "apres Jesus-Christ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\benv\.\b", "environ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bkm\b", "kilometres", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bm\b", "metres", sanitized, flags=re.IGNORECASE)

        return sanitized

    def get_audio_duration(self, file_path):
        try:
            return MP3(file_path).info.length
        except Exception:
            return 0.0

    async def _generate_tts(self, text, output_path, voice, rate, pitch):
        """
        CORRECTIF (hang silencieux) :

        edge_tts.Communicate.save() ouvre une connexion websocket vers
        l'endpoint Microsoft et n'a AUCUN timeout interne. En cas de
        connexion qui ne repond jamais (latence reseau du runner CI,
        throttling silencieux cote serveur...), l'await restait bloque
        indefiniment : pas d'exception, pas de log, pas de retry -- juste
        un pipeline fige jusqu'au timeout du job (observe : 42m52s puis
        annulation par GitHub Actions).

        On borne desormais explicitement l'appel avec asyncio.wait_for :
        au-dela de self.tts_timeout secondes, une asyncio.TimeoutError est
        levee. Cette exception est une sous-classe d'Exception standard,
        donc elle est correctement capturee par le try/except existant
        dans process_script_audio(), qui declenche alors le retry normal
        (ou le fallback audio_path=None si tous les essais echouent).
        """
        phonetic_text = self.sanitize_for_phonetics(text)
        communicate = edge_tts.Communicate(
            text=phonetic_text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume="+0%"
        )
        await asyncio.wait_for(
            communicate.save(output_path),
            timeout=self.tts_timeout
        )

    async def process_script_audio(self, script_data, retries=2):
        """
        CORRECTIF (bug asyncio.run dans une boucle deja active) :

        Cette methode etait auparavant synchrone (def) et appelait
        asyncio.run(self._generate_tts(...)) pour chaque scene. Comme
        main.py tourne deja dans une boucle asyncio active (lancee par
        asyncio.run(main()) et propagee via "await audio_engine.process_script(...)"),
        ce second appel a asyncio.run() a l'interieur d'une boucle deja
        active levait systematiquement :
        "RuntimeError: asyncio.run() cannot be called from a running event loop".

        La methode est desormais "async def" et utilise "await" directement
        sur la coroutine _generate_tts(), ce qui la rend compatible avec
        la boucle asyncio deja active de main(). L'appelant (main.py /
        process_script) doit desormais faire :
            script = await audio_engine.process_script_audio(script)
        au lieu de l'appeler comme une fonction synchrone.
        """
        print("\U0001f3a4 Generation audio (Signature 2 voix strictes)...")

        scenes = script_data.get("scenes", []) if isinstance(script_data, dict) else script_data

        for scene in scenes:
            scene_id = scene["id"]
            text = scene.get("text", "")
            voice_type = scene.get("voice_type", "narrator")

            if voice_type == "witness":
                chosen_voice = self.VOICE_WITNESS
                chosen_rate = self.RATE_WITNESS
                chosen_pitch = self.PITCH_WITNESS
            else:
                chosen_voice = self.VOICE_NARRATOR
                chosen_rate = self.RATE_NARRATOR
                chosen_pitch = self.PITCH_NARRATOR

            output_path = os.path.join(self.audio_dir, f"scene_{scene_id}.mp3")

            success = False
            for attempt in range(retries + 1):
                try:
                    await self._generate_tts(text, output_path, chosen_voice, chosen_rate, chosen_pitch)

                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        scene["audio_path"] = output_path
                        scene["tts_engine"] = "edge-tts"

                        duration = self.get_audio_duration(output_path)
                        scene["duration"] = max(duration, self.min_scene_duration)

                        current_duration = scene["duration"]
                        print(f"      \u2705 Audio {scene_id} ({voice_type}) genere ({current_duration:.2f}s).")
                        success = True
                        break

                except asyncio.TimeoutError:
                    print(
                        f"      \u23f1\ufe0f Timeout TTS ({self.tts_timeout}s) scene {scene_id} "
                        f"(tentative {attempt + 1}/{retries + 1})..."
                    )
                    if attempt < retries:
                        await asyncio.sleep(2)
                    else:
                        print(f"      \u274c Echec definitif TTS (timeout) pour la scene {scene_id}.")

                except Exception as e:
                    if attempt < retries:
                        print(f"      \u26a0\ufe0f Erreur TTS, nouvelle tentative ({attempt+1}/{retries})...")
                        await asyncio.sleep(2)
                    else:
                        print(f"      \u274c Echec definitif TTS pour la scene {scene_id} : {e}")

            if not success:
                scene["audio_path"] = None
                scene["duration"] = self.min_scene_duration

        return script_data

    async def process_script(self, script_data, retries=2):
        """
        Alias asynchrone attendu par main.py ("await audio_engine.process_script(script)").
        Delegue simplement a process_script_audio(), qui porte desormais
        la logique reelle (maintenant asynchrone -- voir le correctif ci-dessus).
        """
        return await self.process_script_audio(script_data, retries=retries)
