import os
import json
import subprocess
import re

WHISPER_CPP_BIN = os.path.join(os.getcwd(), "whisper.cpp", "main")
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


def _run_whisper_cpp(audio_wav_path, output_json_prefix):
    """Transcrit l'audio avec whisper.cpp et force des segments courts
    (max_len=1) pour obtenir des timestamps quasi au niveau du mot."""
    cmd = [
        WHISPER_CPP_BIN,
        "-m", WHISPER_MODEL,
        "-f", audio_wav_path,
        "-l", "fr",
        "-oj",                     # output JSON
        "-ojf",                    # nom de fichier JSON explicite
        "-of", output_json_prefix,
        "-ml", "1",                # max_len=1 mot par segment -> quasi word-level
        "--no-prints",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return f"{output_json_prefix}.json"


def _parse_whisper_json(json_path):
    """Retourne une liste de mots avec timestamps en secondes."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    words = []
    for segment in data.get("transcription", []):
        text = segment["text"].strip()
        if not text:
            continue
        start_ms = _timestamp_to_ms(segment["timestamps"]["from"])
        end_ms = _timestamp_to_ms(segment["timestamps"]["to"])
        words.append({"word": text, "start_ms": start_ms, "end_ms": end_ms})
    return words


def _timestamp_to_ms(ts_str):
    """Convertit '00:00:01,234' en millisecondes."""
    h, m, s_ms = ts_str.split(":")
    s, ms = s_ms.split(",")
    total = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    return total


def _ms_to_ass_time(ms):
    """Convertit des millisecondes au format ASS: H:MM:SS.CC"""
    total_seconds = ms / 1000
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = total_seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_karaoke_ass(words, output_ass_path, words_per_line=4, highlight_color="&H0000FFFF"):
    """Construit un fichier ASS karaoke, en regroupant les mots par
    petites lignes pour un effet TikTok/Reels (3-5 mots visibles a la fois,
    le mot en cours colore differemment)."""
    lines = []
    i = 0
    while i < len(words):
        chunk = words[i:i + words_per_line]
        line_start_ms = chunk[0]["start_ms"]
        line_end_ms = chunk[-1]["end_ms"]

        for highlighted_idx, w in enumerate(chunk):
            seg_start = w["start_ms"] if highlighted_idx == 0 else chunk[highlighted_idx]["start_ms"]
            seg_end = chunk[highlighted_idx + 1]["start_ms"] if highlighted_idx + 1 < len(chunk) else line_end_ms

            text_parts = []
            for j, ww in enumerate(chunk):
                clean_word = ww["word"].replace("{", "").replace("}", "")
                if j == highlighted_idx:
                    text_parts.append(f"{{\\c{highlight_color}}}{clean_word}{{\\c&H00FFFFFF&}}")
                else:
                    text_parts.append(clean_word)
            line_text = " ".join(text_parts)

            start_str = _ms_to_ass_time(seg_start)
            end_str = _ms_to_ass_time(seg_end)
            lines.append(f"Dialogue: 0,{start_str},{end_str},Default,{line_text}")

        i += words_per_line

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ASS_HEADER)
        f.write("\n".join(lines))

    return output_ass_path


def generate_karaoke_subtitles(audio_wav_path, scene_id, temp_dir):
    """Point d'entree unique: audio -> fichier .ass karaoke pret a etre
    burne avec le filtre ffmpeg 'ass'."""
    json_prefix = os.path.join(temp_dir, f"whisper_{scene_id}")
    ass_path = os.path.join(temp_dir, f"karaoke_{scene_id}.ass")

    try:
        json_path = _run_whisper_cpp(audio_wav_path, json_prefix)
        words = _parse_whisper_json(json_path)
        if not words:
            print(f"⚠️ Scene {scene_id}: aucun mot transcrit, sous-titres karaoke ignores.")
            return None
        build_karaoke_ass(words, ass_path)
        return ass_path
    except subprocess.CalledProcessError as e:
        print(f"❌ whisper.cpp a echoue pour la scene {scene_id}: {e.stderr}")
        return None
    except Exception as e:
        print(f"❌ Erreur generation karaoke scene {scene_id}: {e}")
        return None
