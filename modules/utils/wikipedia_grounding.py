"""
wikipedia_grounding.py
=======================
Ancrage (grounding) de la generation sur une source Wikipedia reelle.
"""

import os
import re
import requests
import urllib.parse

MIN_EXTRACT_LENGTH = 300


def _wiki_headers():
    contact = os.getenv("WIKIMEDIA_CONTACT", "https://github.com/tonuser")
    return {"User-Agent": f"AuraContentPipeline/2.0 ({contact}) requests/{requests.__version__}"}


def _search_wikipedia_title(query, lang="fr"):
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "format": "json",
    }
    try:
        r = requests.get(url, params=params, headers=_wiki_headers(), timeout=10)
        r.raise_for_status()
        data = r.json()
        search_results = data.get("query", {}).get("search", [])
        return [item["title"] for item in search_results]
    except Exception as e:
        print(f"⚠️ Wikipedia (search) erreur pour '{query}' ({lang}) : {e}")
        return []


def _fetch_summary(title, lang="fr"):
    safe_title = urllib.parse.quote(title)
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{safe_title}"
    try:
        r = requests.get(url, headers=_wiki_headers(), timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()

        if data.get("type") == "disambiguation":
            return None

        extract = data.get("extract", "")
        if len(extract) < MIN_EXTRACT_LENGTH:
            return None

        return {
            "title": data.get("title", title),
            "extract": extract,
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "lang": lang,
        }
    except Exception as e:
        print(f"⚠️ Wikipedia (summary) erreur pour '{title}' ({lang}) : {e}")
        return None


def _is_valid_match(original_query, title, extract):
    """
    Vérifie que l'article trouvé parle bien du sujet en cherchant
    les mots-clés uniques de la requête dans le titre ou l'extrait.
    """
    q_lower = original_query.lower()
    t_lower = title.lower()
    e_lower = extract.lower()

    # Filtres ultra-stricts pour ignorer les mots de liaison ET les mots génériques ("saint")
    stopwords = {"ile", "île", "le", "la", "les", "de", "des", "du", "un", "une",
                 "et", "en", "à", "a", "pour", "dans", "saint", "sainte", "pont"}

    # Extraction des mots significatifs (plus de 3 lettres)
    q_words = [w for w in re.findall(r'\w+', q_lower) if w not in stopwords and len(w) >= 3]

    if not q_words:
        return True

    # Il faut qu'au moins UN mot "fort" (ex: "cado") soit présent
    for w in q_words:
        if w in t_lower or w in e_lower:
            return True

    return False


def _build_query_variants(query, hint_country=None):
    variants = [query]
    if hint_country:
        variants.append(f"{query} {hint_country}")
    variants.append(f"{query} (ville)")
    variants.append(f"{query} légende")
    return variants


def fetch_grounding_source(query, hint_country=None):
    variants = _build_query_variants(query, hint_country=hint_country)

    for lang in ("fr", "en"):
        for variant in variants:
            candidate_titles = _search_wikipedia_title(variant, lang=lang)
            for title in candidate_titles:
                summary = _fetch_summary(title, lang=lang)
                if summary:
                    # BOUCLIER ANTI-HALLUCINATION
                    if _is_valid_match(query, summary["title"], summary["extract"]):
                        print(f"✅ Source Wikipedia trouvée et VALIDÉE ({lang}, requête '{variant}') : "
                              f"'{summary['title']}' ({len(summary['extract'])} caractères)")
                        return summary
                    else:
                        print(
                            f"🚫 Faux positif Wikipedia rejeté : '{summary['title']}' ne correspond pas à '{query}'."
                            )

    print(f"⚠️ Aucune source Wikipedia exploitable trouvée pour '{query}' "
          f"(après {len(variants) * 2} variantes testées).")
    return None
