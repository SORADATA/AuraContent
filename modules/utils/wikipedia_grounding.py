"""
wikipedia_grounding.py
=======================
Ancrage (grounding) de la generation sur une source Wikipedia reelle.

CORRECTIFS APPLIQUES :
1) Les variantes de requete "(ville)" / "legende" ont ete supprimees : elles
   cassaient le matching par prefixe d'opensearch et faisaient deriver la
   recherche vers des titres totalement hors-sujet (ex: "Vix Krater legende"
   -> "Vikram Samvat"). On ne garde que des variantes qui restent proches du
   nom propre recherche.
2) Ajout d'un filtre de pertinence (_is_relevant_title) : un titre candidat
   n'est retenu QUE s'il partage un token significatif (mot de 3+ lettres,
   hors mots vides) avec la requete d'origine. Avant ce correctif, le premier
   resultat "assez long" etait accepte sans aucune verification de rapport
   avec le sujet, ce qui produisait des sources de grounding aberrantes et
   faisait echouer le fact-check en aval (donc des scripts regeneres a vide,
   avec un budget de tokens de plus en plus reduit).
3) La recherche 'opensearch' est complementee par une recherche full-text
   ('action=query&list=search') en repli, plus robuste que le prefixe seul
   pour des noms propres a plusieurs mots (ex: "Vix Krater").
"""
import os
import re
import requests
import urllib.parse

MIN_EXTRACT_LENGTH = 300

# Mots vides ignores dans le calcul de pertinence (FR + EN), pour ne pas
# valider un match uniquement sur "le", "la", "de", "of", "the", etc.
_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "au", "aux",
    "the", "of", "and", "in", "on", "at", "a", "an", "to", "for",
}


def _wiki_headers():
    contact = os.getenv("WIKIMEDIA_CONTACT", "https://github.com/tonuser")
    return {"User-Agent": f"AuraContentPipeline/2.0 ({contact}) requests/{requests.__version__}"}


def _tokenize(text):
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", str(text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _is_relevant_title(query, title):
    """
    Un titre n'est retenu que s'il partage au moins un token significatif
    avec la requete d'origine (nom propre, lieu, evenement...). Empeche
    d'accepter un article Wikipedia totalement hors-sujet juste parce que
    son extrait est assez long.
    """
    query_tokens = _tokenize(query)
    title_tokens = _tokenize(title)
    if not query_tokens or not title_tokens:
        return False
    return len(query_tokens & title_tokens) > 0


def _search_wikipedia_title_opensearch(query, lang="fr"):
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 5,
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


def _search_wikipedia_title_fulltext(query, lang="fr"):
    """
    Repli en recherche full-text, plus robuste que le prefixe pour les noms
    propres a plusieurs mots (ex: "Vix Krater").
    """
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 5,
        "format": "json",
    }
    try:
        r = requests.get(url, params=params, headers=_wiki_headers(), timeout=10)
        r.raise_for_status()
        data = r.json()
        results = data.get("query", {}).get("search", [])
        return [item.get("title") for item in results if item.get("title")]
    except Exception as e:
        print(f"⚠️ Wikipedia (fulltext search) erreur pour '{query}' ({lang}) : {e}")
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


def _build_query_variants(query, hint_country=None):
    """
    Genere des variantes de requete restant proches du nom propre recherche.
    CORRECTIF : les anciennes variantes "(ville)" et "legende" ont ete
    supprimees -- elles cassaient le matching par prefixe d'opensearch et
    faisaient deriver la recherche vers des titres hors-sujet.
    """
    variants = [query]
    if hint_country:
        variants.append(f"{query} {hint_country}")
    return variants


def fetch_grounding_source(query, hint_country=None):
    """
    Tente de trouver une source Wikipedia exploitable et PERTINENTE pour
    'query'. Essaie plusieurs variantes de requete, en francais puis en
    anglais, via opensearch puis en repli via une recherche full-text.
    Chaque titre candidat est verifie par _is_relevant_title avant d'etre
    retenu. Retourne un dict {title, extract, url, lang} ou None si
    introuvable / non pertinent.
    """
    variants = _build_query_variants(query, hint_country=hint_country)

    for lang in ("fr", "en"):
        for variant in variants:
            candidate_titles = _search_wikipedia_title_opensearch(variant, lang=lang)
            candidate_titles += _search_wikipedia_title_fulltext(variant, lang=lang)

            # Dedupe en conservant l'ordre.
            seen = set()
            deduped_titles = []
            for t in candidate_titles:
                if t not in seen:
                    seen.add(t)
                    deduped_titles.append(t)

            for title in deduped_titles:
                if not _is_relevant_title(query, title):
                    print(f"ℹ️ Titre '{title}' ecarte (aucun rapport lexical avec '{query}').")
                    continue

                summary = _fetch_summary(title, lang=lang)
                if summary:
                    print(f"✅ Source Wikipedia trouvée ({lang}, requête '{variant}') : "
                          f"'{summary['title']}' ({len(summary['extract'])} caractères)")
                    return summary

    print(f"⚠️ Aucune source Wikipedia exploitable et pertinente trouvée pour '{query}' "
          f"(après {len(variants) * 2} variantes testées).")
    return None
