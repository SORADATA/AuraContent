import os
import json
import subprocess
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
        if not t:
            return ""
        t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9\s]", " ", t)
    q_words = {w for w in _clean(query).split() if w not in _STOPWORDS_FR_EN and len(w) > 2}
    t_words = {w for w in _clean(text).split() if w not in _STOPWORDS_FR_EN and len(w) > 2}
    if not q_words:
        return 0.0
    return len(q_words & t_words) / len(q_words)


def _is_video_ext(path):
    return str(path).lower().endswith((".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"))


def validate_video_file(path, probe_timeout=15, min_duration=0.3):
    """
    CORRECTIF : vérifie qu'un fichier vidéo téléchargé est réellement
    décodable et a une durée exploitable, AVANT qu'il n'atteigne le
    pipeline de rendu ffmpeg (Composer). Sans ce garde-fou, un
    téléchargement interrompu en cours de route (mais qui passe quand
    même le test `min_bytes` de download_file) peut produire un fichier
    tronqué/corrompu. Utilisé ensuite avec `stream_loop=-1` dans
    Composer.process_scene, ce type de fichier est un candidat plausible
    à un vrai blocage ffmpeg (le decoder tourne en boucle sans jamais
    atteindre la durée demandée par `trim`).

    Utilise directement `ffprobe` avec un timeout dur — comme
    QualityControl._probe() — plutôt que ffmpeg.probe() qui n'a aucun
    timeout intégré.

    Retourne True si le fichier est valide et exploitable, False sinon.
    """
    if not path or not os.path.exists(path):
        return False

    args = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    try:
        result = subprocess.run(
            args,
            timeout=probe_timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        print(f"      ⏱️ Validation vidéo : ffprobe timeout sur {os.path.basename(path)} (fichier suspect).")
        return False

    if result.returncode != 0:
        print(f"      ❌ Validation vidéo : ffprobe échec sur {os.path.basename(path)}.")
        return False

    try:
        data = json.loads(result.stdout.decode("utf8", errors="ignore"))
        duration = float(data.get("format", {}).get("duration", 0))
        streams = data.get("streams", [])
        has_video_stream = any(s.get("codec_type") == "video" for s in streams)
    except Exception:
        print(f"      ❌ Validation vidéo : JSON ffprobe illisible pour {os.path.basename(path)}.")
        return False

    if not has_video_stream or duration < min_duration:
        print(
            f"      ❌ Validation vidéo : {os.path.basename(path)} invalide "
            f"(durée={duration:.2f}s, flux vidéo={has_video_stream})."
        )
        return False

    return True


def download_file(url, output_path, headers=None, min_bytes=5000, timeout=30):
    try:
        r = requests.get(url, stream=True, headers=headers, timeout=timeout)
        r.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if not (os.path.exists(output_path) and os.path.getsize(output_path) >= min_bytes):
            return False

        # CORRECTIF : validation supplémentaire pour les fichiers vidéo.
        # Un téléchargement peut être interrompu (connexion coupée,
        # timeout réseau côté serveur) tout en produisant un fichier
        # qui dépasse `min_bytes` sans être un flux vidéo valide/complet.
        # On le détecte ici, avant qu'il n'atteigne le rendu ffmpeg.
        if _is_video_ext(output_path):
            if not validate_video_file(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
                return False

        return True
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
