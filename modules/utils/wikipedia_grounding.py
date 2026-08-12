"""
wikipedia_grounding.py
=======================
Ancrage (grounding) de la generation sur une source Wikipedia reelle.

CORRECTIF : essaie plusieurs variantes de requete avant d'abandonner
(nom seul, nom + "Suisse"/"France"/pays probable, nom + "canton" etc.),
car un nom court comme "Oron" echoue souvent en recherche directe alors
qu'un article existe sous un titre plus complet (ex: "Oron (Vaud)").
"""

import os
import requests

MIN_EXTRACT_LENGTH = 300


def _wiki_headers():
    contact = os.getenv("WIKIMEDIA_CONTACT", "contact non configure")
    return {"User-Agent": f"AuraContentPipeline/1.0 ({contact})"}


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
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
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
    """CORRECTIF : genere plusieurs variantes de requete pour maximiser les
    chances de trouver un article exploitable, surtout pour des noms courts
    ou ambigus (ex: 'Oron' -> 'Oron', 'Oron Suisse', 'Oron (Vaud)')."""
    variants = [query]
    if hint_country:
        variants.append(f"{query} {hint_country}")
    variants.append(f"{query} (ville)")
    variants.append(f"{query} légende")
    return variants


def fetch_grounding_source(query, hint_country=None):
    """
    Tente de trouver une source Wikipedia exploitable pour 'query'.
    Essaie plusieurs variantes de requete, en francais puis en anglais.
    Retourne un dict {title, extract, url, lang} ou None si introuvable.
    """
    variants = _build_query_variants(query, hint_country=hint_country)

    for lang in ("fr", "en"):
        for variant in variants:
            candidate_titles = _search_wikipedia_title(variant, lang=lang)
            for title in candidate_titles:
                summary = _fetch_summary(title, lang=lang)
                if summary:
                    print(f"✅ Source Wikipedia trouvee ({lang}, requete '{variant}') : "
                          f"'{summary['title']}' ({len(summary['extract'])} caracteres)")
                    return summary

    print(f"⚠️ Aucune source Wikipedia exploitable trouvee pour '{query}' "
          f"(apres {len(variants) * 2} variantes testees).")
    return None
