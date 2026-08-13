import os
import json
import requests
import unicodedata
import re
from PIL import Image, ImageDraw, ImageFont

HISTORY_FILE = "asset_history.json"
_STOPWORDS_FR_EN = {
    "de", "du", "des", "la", "le", "les", "l", "d", "en", "et", "sur",
    "dans", "un", "une", "a", "au", "aux", "pour", "par", "the", "of",
    "in", "on", "at", "and", "category", "categorie", "avec", "with"
}


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"pexels": [], "pixabay": [], "openverse": [], "wikimedia": []}


def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde historique : {e}")


def is_used(history, source, asset_id):
    return str(asset_id) in history.get(source, [])


def mark_used(history, source, asset_id):
    asset_id = str(asset_id)
    if source not in history:
        history[source] = []
    if asset_id not in history[source]:
        history[source].append(asset_id)
        save_history(history)


def calculate_relevance(query, text):
    def _clean(t):
        if not t: return ""
        t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9\s]", " ", t)
    q_words = {w for w in _clean(query).split() if w not in _STOPWORDS_FR_EN and len(w) > 2}
    t_words = {w for w in _clean(text).split() if w not in _STOPWORDS_FR_EN and len(w) > 2}
    if not q_words: return 0.0
    return len(q_words & t_words) / len(q_words)


def download_file(url, output_path, headers=None, min_bytes=5000, timeout=30):
    try:
        r = requests.get(url, stream=True, headers=headers, timeout=timeout)
        r.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        return os.path.exists(output_path) and os.path.getsize(output_path) >= min_bytes
    except Exception as e:
        print(f"❌ Erreur téléchargement : {e}")
        return False


def save_text_fallback_image(prompt, output_path):
    img = Image.new("RGB", (1080, 1920), (15, 15, 18))
    draw = ImageDraw.Draw(img)
    text = "Fallback image\n\n" + prompt[:180]
    try:
        font = ImageFont.truetype("arial.ttf", 42)
    except Exception:
        font = ImageFont.load_default()
    draw.multiline_text((80, 120), text, fill="white", font=font, spacing=14)
    img.save(output_path)
    return True