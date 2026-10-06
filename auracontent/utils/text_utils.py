import re
import json
import unicodedata
from config.settings import ACCENTED_CHARS, AI_MENTION_PATTERNS, _TITLE_STOPWORDS


def _has_missing_accents(text, min_hits=3):
    suspicious_patterns = [
        r"\bdecouv", r"\bmyster", r"\bsecret", r"\bexplor",
        r"\btheori", r"\bphenomen", r"\bhistoi", r"\bevenem",
        r"\bepoque", r"\betrang", r"\brevel", r"\bdifferen",
        r"\ba ete\b", r"\bpeut etre\b", r"\binteresse",
    ]
    text_lower = text.lower()
    hits = sum(1 for p in suspicious_patterns if re.search(p, text_lower))
    has_any_accent = any(
        c in text_lower for c in ACCENTED_CHARS
        )
    return hits >= min_hits and not has_any_accent


def _contains_ai_mention(text):
    if not text:
        return False
    return any(
        re.search(p, text, re.IGNORECASE) for p in AI_MENTION_PATTERNS
        )


def _clean_single_line_title(text):
    if not text:
        return ""
    cleaned = text.replace('"', '').replace('“', '').replace('”', '').strip()
    lines = [line.strip(' -•\t') for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""
    return re.sub(r"\s+", " ", lines[0]).strip()


def _clean_json_response(content):
    if not content:
        return content
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // 3)


def _estimate_prompt_tokens(messages):
    return sum(
        _estimate_tokens(m.get("content", "")) for m in messages
        )


def _title_tokens(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"\(.*?\)", " ", text.lower())
    tokens = re.findall(r"[a-z0-9]+", text)
    return {t for t in tokens if t not in _TITLE_STOPWORDS and len(t) > 1}


def _source_matches_case(case_name, source_title, threshold=0.6):
    a, b = _title_tokens(case_name), _title_tokens(source_title)
    if not a or not b:
        return False
    common = a & b
    return min(len(common) / len(a), len(common) / len(b)) >= threshold


def _format_stats_instruction(previous_stats_list, label="hooks"):
    """Générique : formate les stats précédentes pour le prompt de n'importe quelle chaîne"""
    if not previous_stats_list:
        return ""
    stats_text = "\n".join([
        f'- Titre : "{s.get("title", "?")}" | Vues : {s.get("views", "?")} | Likes : {s.get("likes", "?")}'
        for s in previous_stats_list
        if isinstance(s, dict) and "title" in s
    ])
    return f"\nANALYSE DES PERFORMANCES RECENTES :\nVoici les resultats de nos dernieres videos publiees :\n{stats_text}\n\nINSTRUCTION :\nAdapte le {label} selon les performances sans citer les stats explicitement.\n"