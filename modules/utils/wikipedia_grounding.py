"""
wikipedia_grounding.py
=======================
Ancrage (grounding) de la generation sur une source Wikipedia reelle.
"""

import os
import requests
import urllib.parse

MIN_EXTRACT_LENGTH = 300

def _wiki_headers():
    contact = os.getenv("WIKIMEDIA_CONTACT", "https://github.com/tonuser")
    # Mise à jour de la version pour correspondre à ton nouveau pipeline 2.0
    return {"User-Agent": f"AuraContentPipeline/2.0 ({contact}) requests/{requests.__version__}"}

def _search_wikipedia_title(query, lang="fr"):
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 3,
        "namespace": 0,
        "format": "json",
    }
    try:
        r = requests.get(url, params=params, headers=_wiki_headers(), timeout=10)
        r.raise_for_status()
        data = r.json()
        titles = data[1] if len(data) > 1 else []
        return titles
    except Exception as e:
        print(f"⚠️ Wikipedia (opensearch) erreur pour '{query}' ({lang}) : {e}")
        return []

def _fetch_summary(title, lang="fr"):
    # Utilisation de urllib.parse.quote pour encoder le titre proprement
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

def _build_query_variants(query, hint_country=None):
    """Génère plusieurs variantes de requête pour maximiser les chances de trouver un article exploitable."""
    variants = [query]
    if hint_country:
        variants.append(f"{query} {hint_country}")
    variants.append(f"{query} (ville)")
    variants.append(f"{query} légende")
    return variants

def fetch_grounding_source(query, hint_country=None):
    """
    Tente de trouver une source Wikipedia exploitable pour 'query'.
    Essaie plusieurs variantes de requête, en français puis en anglais.
    Retourne un dict {title, extract, url, lang} ou None si introuvable.
    """
    variants = _build_query_variants(query, hint_country=hint_country)

    for lang in ("fr", "en"):
        for variant in variants:
            candidate_titles = _search_wikipedia_title(variant, lang=lang)
            for title in candidate_titles:
                summary = _fetch_summary(title, lang=lang)
                if summary:
                    print(f"✅ Source Wikipedia trouvée ({lang}, requête '{variant}') : "
                          f"'{summary['title']}' ({len(summary['extract'])} caractères)")
                    return summary

    print(f"⚠️ Aucune source Wikipedia exploitable trouvée pour '{query}' "
          f"(après {len(variants) * 2} variantes testées).")
    return None