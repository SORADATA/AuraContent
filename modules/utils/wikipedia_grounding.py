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


def wiki_candidates(queries, limit=10):
    titles = []
    for q in queries:
        try:
            r = requests.get(
                "https://fr.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": q,
                        "srlimit": limit, "format": "json"},
                headers=_wiki_headers(), timeout=10,
            )
            r.raise_for_status()
            for item in r.json().get("query", {}).get("search", []):
                t = item.get("title", "")
                if t and not t.startswith(("Liste", "Catégorie", "Wikipédia")):
                    titles.append(t)
        except Exception as e:
            print(f"⚠️ Wikipedia search erreur ({q}) : {e}")
    return list(dict.fromkeys(titles))


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

# ... le reste du fichier (_fetch_summary, _is_valid_match,
#     _build_query_variants, fetch_grounding_source) ne change pas.