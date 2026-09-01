"""
Tracker de sujets déjà utilisés, pour empêcher le pipeline de régénérer
plusieurs vidéos sur le même sujet réel (ex: 5 videos sur le Palais des
Papes d'Avignon avec des titres reformulés différemment).

Fonctionne sur le même principe que hook_tracker.py : un historique
persisté sur disque (JSON), consulté et mis à jour à chaque génération.

Utilisation typique dans brain.py :

    from modules.utils.topic_tracker import (
        load_topic_history, is_duplicate_topic, record_topic_usage,
    )

    used_topics = load_topic_history()
    for attempt in range(MAX_RETRIES):
        candidate = <generation LLM du sujet>
        if not is_duplicate_topic(candidate, used_topics):
            record_topic_usage(candidate)
            return candidate
        # sinon on regenere
"""

import json
import os
import re
import unicodedata
from difflib import SequenceMatcher

TOPIC_HISTORY_PATH = os.path.join(
    os.getcwd(), "assets", "state", "topic_history.json"
)

# Seuil de similarité (0-1) au-dessus duquel deux sujets sont considérés
# comme le même sujet réel malgré une reformulation différente.
DEFAULT_SIMILARITY_THRESHOLD = 0.6

# Nombre max de sujets conservés dans l'historique (evite un fichier qui
# grossit indefiniment ; les plus anciens sont les moins pertinents pour
# la dedup, un pipeline qui tourne depuis des mois ne devrait pas comparer
# un nouveau sujet a une video vieille de 2 ans).
MAX_HISTORY_SIZE = 500

# Mots "gabarit" du pipeline qui reviennent dans presque tous les titres
# et ne portent aucune information sur le SUJET réel (l'entité/lieu).
STOPWORDS = {
    "le", "la", "les", "l", "de", "des", "du", "un", "une", "et", "en",
    "sur", "sous", "dans", "au", "aux", "a", "d", "revele", "revelee",
    "mystere", "mysteres", "secret", "secrets", "secrete", "decouvert",
    "decouverte", "apres", "ans", "oubli", "millenaire", "medieval",
    "medievale", "france", "francaise", "francais",
    "chateau", "tour", "tunnel", "tunnels", "forteresse",
    "palais", "abbaye", "grotte", "basilique", "monastere",
    "couvent", "cite", "ville", "ile", "pont", "salle",
    "chambre", "piece", "chapelle", "eglise",
    "souterrain", "souterrains", "souterraine", "cathedrale",
    "cathedrales", "enfouies", "enfoui", "enfouie",
    "cachee", "cache", "caches", "trouve", "trouvee", "legendes",
    "legende", "histoire", "historique", "veritable", "reelle", "reel",
}


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _keywords(title: str) -> set:
    text = _strip_accents(title.lower())
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    words = re.split(r"[\s\-]+", text)
    return {w for w in words if w and w not in STOPWORDS and len(w) > 2}


def _similarity(title_a: str, title_b: str) -> float:
    kw_a, kw_b = _keywords(title_a), _keywords(title_b)
    if not kw_a or not kw_b:
        overlap = 0.0
    else:
        overlap = len(kw_a & kw_b) / min(len(kw_a), len(kw_b))
    seq = SequenceMatcher(None, title_a.lower(), title_b.lower()).ratio()
    return max(overlap, seq * 0.7)


def load_topic_history():
    """Charge la liste des sujets déjà utilisés (liste de strings)."""
    if not os.path.exists(TOPIC_HISTORY_PATH):
        return []
    try:
        with open(TOPIC_HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(t) for t in data]
        return []
    except Exception as e:
        print(f"⚠️ Impossible de charger topic_history.json, on repart de zéro : {e}")
        return []


def is_duplicate_topic(candidate, history, threshold=DEFAULT_SIMILARITY_THRESHOLD):
    """
    Retourne (True, sujet_similaire) si le candidat ressemble trop a un
    sujet deja utilise, sinon (False, None).
    """
    if not candidate:
        return False, None
    for past_topic in history:
        sim = _similarity(candidate, past_topic)
        if sim >= threshold:
            return True, past_topic
    return False, None


def record_topic_usage(topic):
    """Ajoute un sujet à l'historique persistant et le sauvegarde."""
    if not topic:
        return
    history = load_topic_history()
    history.append(topic)
    if len(history) > MAX_HISTORY_SIZE:
        history = history[-MAX_HISTORY_SIZE:]

    os.makedirs(os.path.dirname(TOPIC_HISTORY_PATH), exist_ok=True)
    try:
        with open(TOPIC_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Impossible d'écrire topic_history.json : {e}")