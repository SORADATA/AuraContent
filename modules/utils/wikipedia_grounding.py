"""
wikipedia_grounding.py
=======================
Ancrage (grounding) de la generation sur une source Wikipedia reelle,
pour verifier la VERACITE NARRATIVE (pas seulement la geographie).

Principe :
1) On demande au LLM de proposer UN sujet reel precis + son titre exact
   d'article Wikipedia (au lieu de le laisser inventer librement les faits
   dans le script final).
2) On recupere le VRAI extrait Wikipedia via l'API publique (source
   externe verifiable, independante du LLM).
3) Si l'article existe et a un contenu substantiel, on fournit cet extrait
   comme "source de verite" obligatoire au LLM qui ecrit le script -- il
   doit se baser UNIQUEMENT sur ces faits, sans en inventer d'autres.
4) Le fact-check final compare le script genere a ce meme extrait, ce qui
   est une comparaison texte-contre-texte bien plus fiable qu'un rappel
   de memoire du LLM sur lui-meme.

LIMITE HONNETE : Wikipedia n'est pas infaillible et certaines legendes
obscures ont des articles courts ou absents. Ce mecanisme reduit tres
fortement le risque d'invention pure, mais ne garantit pas une exactitude
absolue a 100%. Si aucun article correct n'est trouve apres plusieurs
tentatives, le pipeline retombe sur l'ancien mode (LLM libre + fact-check
a l'aveugle) avec un avertissement explicite dans les logs.
"""

import os
import re
import requests

MIN_EXTRACT_LENGTH = 300  # caracteres minimum pour considerer l'extrait exploitable


def _wiki_headers():
    contact = os.getenv("WIKIMEDIA_CONTACT", "contact non configure")
    return {"User-Agent": f"AuraContentPipeline/1.0 ({contact})"}


def _search_wikipedia_title(query, lang="fr"):
    """Resout le titre exact d'un article Wikipedia a partir d'une requete
    approximative (gere les fautes de frappe, variantes, redirections)."""
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 1,
        "namespace": 0,
        "format": "json",
    }
    try:
        r = requests.get(url, params=params, headers=_wiki_headers(), timeout=10)
        r.raise_for_status()
        data = r.json()
        titles = data[1] if len(data) > 1 else []
        return titles[0] if titles else None
    except Exception as e:
        print(f"⚠️ Wikipedia (opensearch) erreur pour '{query}' ({lang}) : {e}")
        return None


def _fetch_summary(title, lang="fr"):
    """Recupere l'extrait/resume d'un article via l'API REST Wikipedia."""
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


def fetch_grounding_source(query):
    """
    Fonction principale : tente de trouver une source Wikipedia exploitable
    pour 'query' (nom de lieu/evenement propose par le LLM).
    Essaie d'abord en francais, puis en anglais si echec.
    Retourne un dict {title, extract, url, lang} ou None si introuvable.
    """
    for lang in ("fr", "en"):
        resolved_title = _search_wikipedia_title(query, lang=lang)
        if not resolved_title:
            continue
        summary = _fetch_summary(resolved_title, lang=lang)
        if summary:
            print(f"✅ Source Wikipedia trouvee ({lang}) : '{summary['title']}' "
                  f"({len(summary['extract'])} caracteres)")
            return summary

    print(f"⚠️ Aucune source Wikipedia exploitable trouvee pour '{query}'.")
    return None
