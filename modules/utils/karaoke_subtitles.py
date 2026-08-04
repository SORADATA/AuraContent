import os
import json
import wave
import subprocess


def _resolve_whisper_bin():
    """FIX : le binaire 'main' de whisper.cpp est deprecie depuis
    decembre 2024, renomme 'whisper-cli'. On detecte dynamiquement
    lequel existe reellement plutot que de supposer 'main'."""
    base = os.path.join(os.getcwd(), "whisper.cpp")
    for name in ("whisper-cli", "main"):
        candidate = os.path.join(base, name)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(base, "whisper-cli")


WHISPER_CPP_BIN = _resolve_whisper_bin()
WHISPER_MODEL = os.path.join(os.getcwd(), "whisper.cpp", "models", "ggml-base.bin")

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,60,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,1,3,1,2,60,60,140,1

[Events]
Format: Layer, Start, End, Style, Text
"""


def _is_wav_16k_mono(path):
    """FIX : verifie reellement le sample rate/canaux au lieu de se
    fier a l'extension .wav. Gemini TTS et Kokoro produisent du WAV
    a 24000 Hz -- whisper.cpp attend strictement du 16000 Hz mono."""
    try:
        with wave.open(path, "rb") as wf:
            return wf.getframerate() == 16000 and wf.getnchannels() == 1
    except Exception:
        return False


def _ensure_wav_16k(audio_path, temp_dir, scene_id):
    """Convertit systematiquement si le fichier n'est pas deja en
    16kHz mono exact, quel que soit le moteur TTS d'origine."""
    if audio_path.lower().endswith(".wav") and _is_wav_16k_mono(audio_path):
        return audio_path

    os.makedirs(temp_dir, exist_ok=True)
    converted_path = os.path.join(temp_dir, f"converted_{scene_id}.wav")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_path,
                "-ar", "16000", "-ac", "1",
                converted_path,
            ],
            check=True,
            capture_output=True,
        )
        return converted_path
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        print(f"❌ Conversion audio->wav echouee pour scene {scene_id}: {stderr}")
        return None
    except Exception as e:
        print(f"❌ Erreur inattendue conversion audio scene {scene_id}: {e}")
        return None


def _run_whisper_cpp(audio_wav_path, output_json_prefix):
    cmd = [
        WHISPER_CPP_BIN, "-m", WHISPER_MODEL, "-f", audio_wav_path,
        "-l", "fr", "-oj", "-ojf", "-of", output_json_prefix,
        "-ml", "1", "--no-prints",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return f"{output_json_prefix}.json"


def _timestamp_to_ms(ts_str):
    h, m, s_ms = ts_str.split(":")
    s, ms = s_ms.split(",")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def _ms_to_ass_time(ms):
    total_seconds = ms / 1000
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = total_seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _parse_whisper_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    words = []
    for segment in data.get("transcription", []):
        text = segment["text"].strip()
        if not text:
            continue
        words.append({
            "word": text,
            "start_ms": _timestamp_to_ms(segment["timestamps"]["from"]),
            "end_ms": _timestamp_to_ms(segment["timestamps"]["to"]),
        })
    return words


def build_karaoke_ass(words, output_ass_path, words_per_line=4, highlight_color="&H0000FFFF"):
    lines = []
    i = 0
    while i < len(words):
        chunk = words[i:i + words_per_line]
        line_end_ms = chunk[-1]["end_ms"]

        for idx, w in enumerate(chunk):
            seg_start = chunk[idx]["start_ms"]
            seg_end = chunk[idx + 1]["start_ms"] if idx + 1 < len(chunk) else line_end_ms

            text_parts = []
            for j, ww in enumerate(chunk):
                clean_word = ww["word"].replace("{", "").replace("}", "")
                if j == idx:
                    text_parts.append(f"{{\\c{highlight_color}}}{clean_word}{{\\c&H00FFFFFF&}}")
                else:
                    text_parts.append(clean_word)
            line_text = " ".join(text_parts)

            lines.append(
                f"Dialogue: 0,{_ms_to_ass_time(seg_start)},{_ms_to_ass_time(seg_end)},Default,{line_text}"
            )
        i += words_per_line

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ASS_HEADER)
        f.write("\n".join(lines))
    return output_ass_path


def generate_karaoke_subtitles(audio_path, scene_id, temp_dir):
    """Point d'entree unique : audio (wav ou mp3, quel que soit le
    sample rate d'origine) -> fichier .ass karaoke."""
    wav_path = _ensure_wav_16k(audio_path, temp_dir, scene_id)
    if not wav_path:
        return None

    json_prefix = os.path.join(temp_dir, f"whisper_{scene_id}")
    ass_path = os.path.join(temp_dir, f"karaoke_{scene_id}.ass")

    try:
        json_path = _run_whisper_cpp(wav_path, json_prefix)
        words = _parse_whisper_json(json_path)
        if not words:
            print(f"⚠️ Scene {scene_id}: aucun mot transcrit, karaoke ignore.")
            return None
        return build_karaoke_ass(words, ass_path)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        print(f"❌ whisper.cpp echec scene {scene_id}: {stderr}")
        return None
    except Exception as e:
        print(f"❌ Erreur karaoke scene {scene_id}: {e}")
        return None
