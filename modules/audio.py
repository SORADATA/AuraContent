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
    Générateur audio strict à 2 voix (Narrateur / Témoin).
    Garantit une cohérence vocale totale sur toute la vidéo.
    """
    
    # Dictionnaires de prononciation conservés de l'ancienne version
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

    ROMAN_NUMERALS_MAP = {
        r"\bXXI(?:e|ème|eme)?\s+siècle\b": "vingt et unième siècle",
        r"\bXX(?:e|ème|eme)?\s+siècle\b": "vingtième siècle",
        r"\bXIX(?:e|ème|eme)?\s+siècle\b": "dix-neuvième siècle",
        r"\bXVIII(?:e|ème|eme)?\s+siècle\b": "dix-huitième siècle",
        r"\bXVII(?:e|ème|eme)?\s+siècle\b": "dix-septième siècle",
        r"\bXVI(?:e|ème|eme)?\s+siècle\b": "seizième siècle",
        r"\bXV(?:e|ème|eme)?\s+siècle\b": "quinzième siècle",
        r"\bXIV(?:e|ème|eme)?\s+siècle\b": "quatorzième siècle",
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

    def __init__(self):
        self.audio_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.audio_dir, exist_ok=True)
        self.min_scene_duration = 3.0

        # 📌 SIGNATURE VOCALE STRICTE
        # Henri : Voix principale (grave, posée, documentaire)
        self.VOICE_NARRATOR = "fr-FR-HenriNeural"
        self.RATE_NARRATOR = "-12%"
        self.PITCH_NARRATOR = "-4Hz"

        # Claude : Voix secondaire (pour les citations, témoins)
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

        sanitized = re.sub(r"\bav\.\s*J\.-C\.\b", "avant Jésus-Christ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bap\.\s*J\.-C\.\b", "après Jésus-Christ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\benv\.\b", "environ", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bkm\b", "kilomètres", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"\bm\b", "mètres", sanitized, flags=re.IGNORECASE)

        return sanitized

    def get_audio_duration(self, file_path):
        try:
            return MP3(file_path).info.length
        except Exception:
            return 0.0

    async def _generate_tts(self, text, output_path, voice, rate, pitch):
        phonetic_text = self.sanitize_for_phonetics(text)
        communicate = edge_tts.Communicate(
            text=phonetic_text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume="+0%"
        )
        await communicate.save(output_path)

    def process_script_audio(self, script_data, retries=2):
        print("🎙️ Génération audio (Signature 2 voix strictes)...")
        
        scenes = script_data.get("scenes", []) if isinstance(script_data, dict) else script_data
        
        for scene in scenes:
            scene_id = scene["id"]
            text = scene.get("text", "")
            voice_type = scene.get("voice_type", "narrator")
            
            # Routage strict de la voix et des paramètres
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
                    asyncio.run(self._generate_tts(text, output_path, chosen_voice, chosen_rate, chosen_pitch))
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                        scene["audio_path"] = output_path
                        scene["tts_engine"] = "edge-tts"
                        
                        duration = self.get_audio_duration(output_path)
                        scene["duration"] = max(duration, self.min_scene_duration)
                        
                        print(f"      ✅ Audio {scene_id} ({voice_type}) généré ({scene['duration']:.2f}s).")
                        success = True
                        break
                        
                except Exception as e:
                    if attempt < retries:
                        print(f"      ⚠️ Erreur TTS, nouvelle tentative ({attempt+1}/{retries})...")
                        time.sleep(2)
                    else:
                        print(f"      ❌ Échec définitif TTS pour la scène {scene_id} : {e}")
            
            if not success:
                scene["audio_path"] = None
                scene["duration"] = self.min_scene_duration

        return script_data