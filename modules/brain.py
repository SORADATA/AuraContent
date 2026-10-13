import os
import re
import json
import time
import requests
import random
from openai import OpenAI
import unicodedata
from dotenv import load_dotenv
from modules.utils.viral_trends import fetch_viral_videos
from constants import GROQ_MODEL
from modules.utils.topic_tracker import (
    load_topic_history, is_duplicate_topic, record_topic_usage,
    load_last_categories, save_last_category,
    load_last_regions, save_last_region,
)


try:
    from modules.utils.client_http.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Création de données factices pour le test.")

    def get_latest_videos_stats():
        return None
try:
    from modules.utils.wikipedia_grounding import fetch_grounding_source, wiki_candidates, NICHE_KEYWORDS
    GROUNDING_AVAILABLE = True
except ImportError:
    GROUNDING_AVAILABLE = False
    NICHE_KEYWORDS = ["mystère", "secret", "histoire", "légende"]  # Liste de secours

    def fetch_grounding_source(query, hint_country=None):
        return None

    def wiki_candidates(queries, limit=10):
        return []
load_dotenv()

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc)."
)

NO_META_AI_INSTRUCTION = (
    "INTERDICTION ABSOLUE : ne jamais mentionner l'intelligence artificielle, "
    "l'IA, un algorithme, une technologie de generation de contenu, ou tout "
    "aspect meta concernant la creation de la video elle-meme. Le sujet et le "
    "texte doivent parler uniquement du mystere/de l'histoire reelle, jamais "
    "de l'outil ou de la methode utilisee pour le raconter."
)

VERACITY_INSTRUCTION = (
    "EXIGENCE DE VERACITE HISTORIQUE : "
    "1) N'utilise QUE des lieux, evenements et personnages REELS et documentes. "
    "Interdiction absolue d'inventer un nom de lieu, un evenement ou un personnage. "
    "2) Ne deplace JAMAIS geographiquement un fait reel. Si un evenement/lieu "
    "s'est produit dans un pays ou une region precise, cette localisation doit "
    "etre respectee EXACTEMENT dans le texte, le titre et le sujet. Ne jamais "
    "presenter un fait etranger comme francais (ou inversement) meme si l'histoire "
    "est fascinante. "
    "3) Le sujet doit rester peu connu du grand public mais reel et verifiable, "
    "jamais une invention presentee comme un fait. "
    "4) EVITE les noms de lieux trop generiques/ambigus (ex: une simple 'Eglise "
    "Saint-Pierre' sans precision) qui existent en plusieurs exemplaires dans "
    "differents pays -- precise toujours le nom complet et specifique du lieu "
    "(ex: 'Eglise Saint-Pierre d'Oron' plutot que juste 'Eglise Saint-Pierre'). "
    "5) Pour chaque lieu mentionne dans le champ 'location_name', precise aussi "
    "le pays reel dans un champ 'location_country' (ex: 'France', 'Allemagne', "
    "'Suisse'). Si le sujet annonce une zone geographique specifique, TOUS les "
    "lieux du script doivent appartenir a cette zone reelle. "
    "6) ATTENTION AUX LIEUX AMBIGUS AVEC MEME NOM : il existe souvent plusieurs "
    "lieux similaires (ex: plusieurs 'ponts du diable' en France, plusieurs "
    "'eglises Saint-Pierre') dans des villes/regions differentes. Verifie "
    "mentalement que le lieu precis correspond exactement au sujet donne, sans "
    "confondre deux legendes/lieux distincts portant un nom proche."
)


def _has_missing_accents(text, min_hits=3):
    suspicious_patterns = [
        r"\bdecouv", r"\bmyster", r"\bsecret", r"\bexplor",
        r"\btheori", r"\bphenomen", r"\bhistoi", r"\bevenem",
        r"\bepoque", r"\betrang", r"\brevel", r"\bdifferen",
        r"\ba ete\b", r"\bpeut etre\b", r"\binteresse",
    ]
    text_lower = text.lower()
    hits = sum(1 for p in suspicious_patterns if re.search(p, text_lower))
    has_any_accent = any(c in text_lower for c in ACCENTED_CHARS)
    return hits >= min_hits and not has_any_accent


AI_MENTION_PATTERNS = [
    r"intelligence\s+artificielle", r"\bIA\b", r"\bl'IA\b",
    r"artificial\s+intelligence", r"\bl'algorithme\b", r"\bchatgpt\b",
    r"\bgroq\b", r"\bgemini\b", r"genere[e]?\s+par\s+l'?ia",
]


def _contains_ai_mention(text):
    if not text:
        return False
    return any(re.search(p, text, re.IGNORECASE) for p in AI_MENTION_PATTERNS)


def _format_stats_instruction(previous_stats_list, label="hooks"):
    if not previous_stats_list:
        return ""

    stats_text = "\n".join([
        f'- Titre : "{s.get("title", "?")}" | Vues : {s.get("views", "?")} | Likes : {s.get("likes", "?")}'
        for s in previous_stats_list
        if isinstance(s, dict) and "title" in s
    ])

    return f"""
ANALYSE DES PERFORMANCES RECENTES :
Voici les resultats de nos dernieres videos publiees :
{stats_text}

INSTRUCTION :
Adapte le {label} selon les performances sans citer les stats explicitement.
"""


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


def _strip_reasoning(text):
    """Les modeles 'reasoning' gratuits renvoient parfois <think>...</think>."""
    if not text:
        return text
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"^.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)  # balise ouvrante perdue
    return text.strip()


def _repair_json_text(text):
    """
    Tente de reparer un JSON casse (typiquement le failed_generation de Groq).
    Corrige :
      - l'accolade de scene manquante  ...},"id":5,...  ->  ...},{"id":5,...
      - un JSON tronque (guillemet/accolades/crochets non fermes)
    Retourne le texte repare s'il est parsable, sinon None.
    """
    if not text:
        return None
    t = _strip_reasoning(_clean_json_response(text))

    try:
        json.loads(t)
        return t
    except Exception:
        pass

    # Cas observe : "},"id":5," -> "},{"id":5,"
    t = re.sub(r'\}\s*,?\s*"id"\s*:', '},{"id":', t)

    stack, in_str, escape = [], False, False
    for ch in t:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                stack.pop()

    repaired = t
    if in_str:
        repaired += '"'
    repaired = re.sub(r",\s*$", "", repaired)
    repaired += "".join("}" if o == "{" else "]" for o in reversed(stack))

    try:
        json.loads(repaired)
        return repaired
    except Exception:
        return None


FRENCH_GEO_KEYWORDS = [
    "france", "francaise", "francais", "bretagne", "normandie", "vendee",
    "charente", "gironde", "aquitaine", "atlantique francaise",
    "cote atlantique francaise", "cote d'azur", "provence", "occitanie",
]

COUNTRY_KEYWORDS = {
    "france": ["france", "francaise", "francais", "bretagne", "normandie",
               "vendee", "charente", "gironde", "aquitaine", "provence", "occitanie"],
    "suisse": ["suisse", "helvetique", "vaud", "geneve", "valais", "zurich", "berne"],
    "allemagne": ["allemagne", "allemand", "allemande", "baviere", "bavaria"],
    "italie": ["italie", "italien", "italienne", "toscane", "sicile"],
    "espagne": ["espagne", "espagnol", "espagnole", "catalogne", "andalousie"],
    "belgique": ["belgique", "belge"],
}

# --- Listes de diversification pour les sujets ---
FRENCH_REGIONS = [
    "Île-de-France (hors Paris intra-muros)",
    "Bretagne",
    "Normandie",
    "Hauts-de-France",
    "Grand Est (Alsace, Lorraine, Champagne)",
    "Bourgogne-Franche-Comté",
    "Auvergne-Rhône-Alpes",
    "Nouvelle-Aquitaine",
    "Occitanie",
    "Provence-Alpes-Côte d'Azur",
    "Corse",
    "Pays de la Loire",
    "Centre-Val de Loire",
    "Outre-mer français (Guadeloupe, Martinique, Réunion, etc.)",
    "Paris intra-muros",  # gardé, mais noyé parmi 13 autres options
]
REGION_LOOKBACK = 3  # nb de dernieres regions a exclure de la selection

# Videos virales marquees comme fictives : on ne s'en inspire pas
FICTION_MARKERS = ["fiction", "fictive", "fictif", "⚠️", "#story", "#storytime", "#horror"]


def _is_fiction_title(title):
    t = str(title or "").lower()
    return any(m in t for m in FICTION_MARKERS)


def _topic_claims_french_location(topic):
    topic_lower = topic.lower()
    return any(kw in topic_lower for kw in FRENCH_GEO_KEYWORDS)


def _guess_country_hint(topic):
    topic_lower = topic.lower()
    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(kw in topic_lower for kw in keywords):
            return country.capitalize()
    return None


class WikidataChecker:
    API_URL = "https://www.wikidata.org/w/api.php"
    HEADERS = {
        "User-Agent": os.getenv(
            "WIKIMEDIA_CONTACT",
            "AuraContentPipeline/1.0 (contact non configure)"
        )
    }
    CACHE = {}
    MIN_DELAY_BETWEEN_CALLS = 0.6

    @classmethod
    def _throttled_get(cls, params, max_retries=2):
        for attempt in range(max_retries + 1):
            time.sleep(cls.MIN_DELAY_BETWEEN_CALLS)
            try:
                r = requests.get(cls.API_URL, params=params, headers=cls.HEADERS, timeout=10)
                if r.status_code == 429:
                    wait = 3 * (attempt + 1)
                    print(f"⏳ Wikidata 429, attente {wait}s avant retry...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r
            except requests.exceptions.RequestException as e:
                if attempt == max_retries:
                    print(f"⚠️ Wikidata erreur reseau (abandon apres {max_retries + 1} tentatives) : {e}")
                    return None
                time.sleep(2)
        return None

    @classmethod
    def _search_entity_ids(cls, location_name, limit=3):
        params = {
            "action": "wbsearchentities",
            "search": location_name,
            "language": "fr",
            "format": "json",
            "limit": limit,
            "type": "item",
        }
        r = cls._throttled_get(params)
        if r is None:
            return []
        try:
            results = r.json().get("search", [])
            return [item.get("id") for item in results if item.get("id")]
        except Exception as e:
            print(f"⚠️ Wikidata (parsing recherche) erreur pour '{location_name}' : {e}")
            return []

    @classmethod
    def _get_country_for_entity(cls, entity_id):
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "claims",
            "format": "json",
        }
        r = cls._throttled_get(params)
        if r is None:
            return None
        try:
            entities = r.json().get("entities", {})
            entity = entities.get(entity_id, {})
            claims = entity.get("claims", {})
            country_claims = claims.get("P17")
            if not country_claims:
                return None
            country_entity_id = (
                country_claims[0]
                .get("mainsnak", {})
                .get("datavalue", {})
                .get("value", {})
                .get("id")
            )
            if not country_entity_id:
                return None
            return cls._resolve_entity_label(country_entity_id)
        except Exception as e:
            print(f"⚠️ Wikidata (parsing pays) erreur pour '{entity_id}' : {e}")
            return None

    @classmethod
    def _resolve_entity_label(cls, entity_id):
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "labels",
            "languages": "fr|en",
            "format": "json",
        }
        r = cls._throttled_get(params)
        if r is None:
            return None
        try:
            entities = r.json().get("entities", {})
            entity = entities.get(entity_id, {})
            labels = entity.get("labels", {})
            label = labels.get("fr") or labels.get("en")
            if label:
                return label.get("value")
        except Exception as e:
            print(f"⚠️ Wikidata (parsing label) erreur : {e}")
        return None

    @classmethod
    def get_real_country(cls, location_name, hint_country=None):
        if not location_name:
            return None

        cache_key = f"{location_name.strip().lower()}|{(hint_country or '').lower()}"
        if cache_key in cls.CACHE:
            return cls.CACHE[cache_key]

        entity_ids = cls._search_entity_ids(location_name, limit=3)
        if not entity_ids:
            cls.CACHE[cache_key] = None
            return None

        candidates_countries = []
        for entity_id in entity_ids:
            country = cls._get_country_for_entity(entity_id)
            candidates_countries.append(country)

            if hint_country and country and _countries_match(hint_country, country):
                cls.CACHE[cache_key] = country
                return country

        result = next((c for c in candidates_countries if c), None)
        cls.CACHE[cache_key] = result
        return result


def _normalize_country_text(text):
    return re.sub(r"[^a-z]", "", str(text or "").lower())


def _countries_match(declared, real):
    if not declared or not real:
        return True
    d = _normalize_country_text(declared)
    r = _normalize_country_text(real)
    return d == r or d in r or r in d


# ═══════════════════════════════════════════════════════════════════════════
#  GESTION DES LLM : Groq + modeles OpenRouter 100 % GRATUITS
# ═══════════════════════════════════════════════════════════════════════════
# Les modeles gratuits OpenRouter tournent souvent (retires sans preavis).
# On ne code donc PAS de slug en dur : on les decouvre dynamiquement via
# l'API publique /models (uniquement ceux finissant par ":free", prix 0,
# compatibles JSON), puis on termine par le routeur officiel "openrouter/free".
#
# Override manuel possible dans .env :
#   OPENROUTER_FREE_MODELS=meta-llama/llama-3.3-70b-instruct:free,openai/gpt-oss-120b:free

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_FREE_ROUTER = "openrouter/free"
OPENROUTER_MAX_DISCOVERED = 2
FREE_MODELS_CACHE_TTL = 3600  # secondes

# Ordre de preference (le premier mot-cle trouve gagne)
FREE_MODEL_PREFERENCES = [
    "llama-3.3-70b", "gpt-oss-120b", "qwen3-235b", "qwen3-next", "qwen3-coder",
    "qwen", "nemotron", "deepseek", "gemma-3-27b", "gemma", "mistral", "glm", "llama",
]
FREE_MODEL_BLACKLIST = ["vision", "-vl", "image", "audio", "embed", "thinking", "lfm", "guard", "safeguard"]
_SMALL_MODEL_RE = re.compile(r"(?<![0-9a-z])(0?\.?[1-9])b(?![a-z0-9])")  # 1b..9b = trop petit pour du JSON long

_FREE_MODELS_CACHE = {"ts": 0.0, "models": []}
_DEAD_MODELS = set()  # slugs renvoyant 404 pendant cette execution


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _discover_free_models(max_models=OPENROUTER_MAX_DISCOVERED):
    env_models = [m.strip() for m in os.getenv("OPENROUTER_FREE_MODELS", "").split(",") if m.strip()]
    if env_models:
        return [m for m in env_models if m not in _DEAD_MODELS][:max_models]

    now = time.time()
    cached = _FREE_MODELS_CACHE["models"]
    if cached and now - _FREE_MODELS_CACHE["ts"] < FREE_MODELS_CACHE_TTL:
        return [m for m in cached if m not in _DEAD_MODELS][:max_models]

    try:
        r = requests.get(f"{OPENROUTER_BASE_URL}/models", timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as e:
        print(f"⚠️ Decouverte des modeles gratuits OpenRouter impossible : {e}")
        return [m for m in cached if m not in _DEAD_MODELS][:max_models]

    scored = []
    for m in data:
        mid = str(m.get("id", ""))
        low = mid.lower()
        if not mid.endswith(":free") or mid in _DEAD_MODELS:
            continue
        pricing = m.get("pricing") or {}
        if _to_float(pricing.get("prompt")) not in (0.0, None) or _to_float(pricing.get("completion")) not in (0.0, None):
            continue
        params = m.get("supported_parameters") or []
        if not ("response_format" in params or "structured_outputs" in params):
            continue
        if (m.get("context_length") or 0) < 16000:
            continue
        out_mods = (m.get("architecture") or {}).get("output_modalities") or ["text"]
        if "text" not in out_mods:
            continue
        if any(b in low for b in FREE_MODEL_BLACKLIST) or _SMALL_MODEL_RE.search(low):
            continue
        score = next((len(FREE_MODEL_PREFERENCES) - i for i, k in enumerate(FREE_MODEL_PREFERENCES) if k in low), 0)
        scored.append((score, m.get("context_length") or 0, mid))

    scored.sort(reverse=True)
    models = [mid for _, _, mid in scored]
    if models:
        _FREE_MODELS_CACHE.update({"ts": now, "models": models})
        print(f"🆓 Modeles OpenRouter gratuits retenus : {models[:max_models]}")
    return models[:max_models]


def _build_providers():
    providers = []
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        providers.append({
            "name": "Groq", "model": GROQ_MODEL,
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": groq_key, "is_groq": True,
        })

    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key:
        slugs = _discover_free_models()
        if OPENROUTER_FREE_ROUTER not in slugs:
            slugs = slugs + [OPENROUTER_FREE_ROUTER]  # filet de securite final
        for i, slug in enumerate(slugs, start=1):
            if slug in _DEAD_MODELS:
                continue
            providers.append({
                "name": f"OpenRouter free #{i}", "model": slug,
                "base_url": OPENROUTER_BASE_URL,
                "api_key": or_key, "is_groq": False,
            })
    return providers


# ═══════════════════════════════════════════════════════════════════════════
#  CLASSIFICATION DES ERREURS
# ═══════════════════════════════════════════════════════════════════════════
_RATE_LIMIT_NUMS_RE = re.compile(r"Limit[:\s]+(\d+),?\s*Requested[:\s]+(\d+)", re.IGNORECASE)
SAFETY_MARGIN_TOKENS = 400


def _parse_rate_limit_numbers(err_str):
    match = _RATE_LIMIT_NUMS_RE.search(err_str)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _is_rate_limit_error(err_str):
    err_lower = err_str.lower()
    return (
        "rate_limit_exceeded" in err_lower
        or "rate limit" in err_lower
        or "tokens per minute" in err_lower
        or "tpm" in err_lower
        or "requests per minute" in err_lower
        or "rpm" in err_lower
        or "error code: 429" in err_lower
    )


def _classify_error(e, err_str):
    low = err_str.lower()
    if isinstance(e, ValueError) and "budget de tokens" in low:
        return "length"
    if isinstance(e, ValueError):
        return "empty"
    if "json_validate_failed" in low or "failed to generate json" in low or "failed to validate json" in low:
        return "json_failed"
    if "error code: 404" in low or "no endpoints found" in low or "unavailable" in low or "not a valid model" in low:
        return "not_found"
    if "error code: 402" in low or "more credits" in low or "insufficient" in low:
        return "no_credit"
    if _is_rate_limit_error(err_str):
        return "rate_limit"
    if "error code: 400" in low and ("response_format" in low or "json_object" in low or "structured" in low):
        return "json_mode_unsupported"
    if "i'm sorry" in low or "i’m sorry" in low or "content_policy" in low or "moderation" in low:
        return "refusal"
    return "other"


def _extract_failed_generation(e, err_str):
    """Recupere le texte 'failed_generation' d'une erreur 400 Groq."""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict) and inner.get("failed_generation"):
            return inner["failed_generation"]
    m = re.search(r"'failed_generation': '(.*)'\}\}", err_str, re.DOTALL)
    if m:
        return m.group(1).replace("\\'", "'").replace("\\n", "\n")
    return None


def _estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // 3)


def _estimate_prompt_tokens(messages):
    return sum(_estimate_tokens(m.get("content", "")) for m in messages)


_TITLE_STOPWORDS = {"de", "du", "des", "la", "le", "les", "d", "l", "et", "en",
                    "au", "aux", "un", "une", "the", "of"}


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


def _norm_title(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _match_candidate(wiki_title, candidates):
    """Retrouve un titre de la liste meme si casse/accents/ponctuation different."""
    if wiki_title in candidates:
        return wiki_title
    target = _norm_title(wiki_title)
    for c in candidates:
        if _norm_title(c) == target:
            return c
    return None


class ContentBrain:
    def __init__(self):
        pass

    def _extract_content(self, response):
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        if not choices:
            raise ValueError(f"Réponse inattendue du LLM: {response}")

        choice0 = choices[0]
        message = getattr(choice0, "message", None)
        if message is None and isinstance(choice0, dict):
            message = choice0.get("message")

        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)

        if content is None and isinstance(choice0, dict):
            content = choice0.get("content")

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text") or item.get("content") or "")
                elif isinstance(item, str):
                    parts.append(item)
            content = "".join(parts).strip()

        content = _strip_reasoning(content) if content else content

        if not content:
            finish_reason = getattr(choice0, "finish_reason", None)
            if finish_reason is None and isinstance(choice0, dict):
                finish_reason = choice0.get("finish_reason")

            if finish_reason == "length":
                raise ValueError("Contenu vide du LLM : budget de tokens épuisé (finish_reason='length'). Augmenter max_completion_tokens.")

            raise ValueError(f"Contenu vide du LLM: {response}")

        return content.strip()

    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False,
                            max_completion_tokens=3000, hard_token_cap=7500):
        """
        Cascade : Groq -> modeles OpenRouter gratuits (decouverts dynamiquement)
        -> routeur openrouter/free. Chaque type d'erreur a sa propre strategie :
          json_failed  -> recupere/repare le failed_generation, sinon retente
          not_found    -> blackliste le modele, passe au suivant
          no_credit    -> passe au suivant (ne devrait pas arriver en :free)
          rate_limit   -> attente courte puis suivant
          refusal      -> suivant immediatement
          length       -> augmente le budget de sortie
        """
        providers = _build_providers()
        if not providers:
            raise RuntimeError("Brain Error: aucune clé API (GROQ_API_KEY / OPENROUTER_API_KEY) configurée.")

        last_error = None
        prompt_tokens_est = _estimate_prompt_tokens(messages)

        for provider in providers:
            if provider["model"] in _DEAD_MODELS:
                continue

            is_groq = provider["is_groq"]
            client = OpenAI(
                base_url=provider["base_url"],
                api_key=provider["api_key"],
                max_retries=0,
                timeout=90,
                default_headers=None if is_groq else {
                    "HTTP-Referer": "https://github.com/aura-content-pipeline",
                    "X-Title": "AuraContentPipeline",
                },
            )

            current_max_tokens = max_completion_tokens
            if is_groq:
                ceiling = max(500, hard_token_cap - prompt_tokens_est - SAFETY_MARGIN_TOKENS)
                if current_max_tokens > ceiling:
                    print(f"ℹ️ Budget de sortie réduit préventivement : {current_max_tokens} -> {ceiling}")
                    current_max_tokens = ceiling
            else:
                ceiling = max(max_completion_tokens, 8000)

            use_json_mode = json_mode
            cur_temp = temperature
            rate_limit_hits = 0

            for attempt in range(3):
                try:
                    kwargs = {
                        "model": provider["model"],
                        "messages": messages,
                        "temperature": cur_temp,
                        "max_completion_tokens": current_max_tokens,
                    }
                    if use_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    response = client.chat.completions.create(**kwargs)
                    content = self._extract_content(response)
                    print(f"✅ Réponse obtenue via {provider['name']} ({provider['model']})")
                    time.sleep(0.5)
                    return content

                except Exception as e:
                    err_str = str(e)
                    last_error = e
                    kind = _classify_error(e, err_str)
                    short_err = err_str[:300] + ("…" if len(err_str) > 300 else "")
                    print(f"⚠️ Échec {provider['name']} [{provider['model']}] "
                          f"(tentative {attempt + 1}/3, type={kind}) : {short_err}")

                    if kind == "json_failed":
                        # Erreur de FORMAT (pas de moderation) : on tente de recuperer le JSON.
                        raw = _extract_failed_generation(e, err_str)
                        salvaged = _repair_json_text(raw) if raw else None
                        if salvaged:
                            print("🩹 JSON récupéré et réparé depuis failed_generation.")
                            return salvaged
                        cur_temp = max(0.2, cur_temp - 0.2)  # moins de derive structurelle
                        time.sleep(1)
                        continue

                    if kind == "refusal":
                        print(f"🚫 Refus de sécurité sur {provider['name']}, bascule vers le fallback.")
                        break

                    if kind == "not_found":
                        _DEAD_MODELS.add(provider["model"])
                        print(f"🚫 Modèle indisponible ({provider['model']}), ignoré pour cette exécution.")
                        break

                    if kind == "no_credit":
                        print(f"💳 Crédits insuffisants sur {provider['name']}, passage au suivant.")
                        break

                    if kind == "json_mode_unsupported":
                        print("ℹ️ response_format non supporté par ce modèle, retry sans json_mode.")
                        use_json_mode = False
                        continue

                    if kind == "length":
                        current_max_tokens = min(current_max_tokens + 1500, ceiling)
                        time.sleep(1)
                        continue

                    if kind == "rate_limit":
                        rate_limit_hits += 1
                        low = err_str.lower()
                        if "per day" in low or "daily" in low:
                            print(f"⛔ Quota journalier atteint sur {provider['name']}, passage au suivant.")
                            break
                        nums = _parse_rate_limit_numbers(err_str)
                        if nums:
                            limit, requested = nums
                            current_max_tokens = max(500, current_max_tokens - (requested - limit) - SAFETY_MARGIN_TOKENS)
                            time.sleep(1)
                            continue
                        if not is_groq and rate_limit_hits >= 2:
                            break
                        wait_time = 25 if is_groq else 6
                        print(f"⏳ Limite de débit sur {provider['name']}, attente de {wait_time}s...")
                        time.sleep(wait_time)
                        continue

                    # empty / other
                    time.sleep(2 if kind == "empty" else 3)

            print(f"❌ Abandon de {provider['name']} ({provider['model']}).")

        raise RuntimeError(
            "Brain Error (Script): Échec total après utilisation de tous les modèles "
            f"(Groq + OpenRouter gratuits). Dernière erreur: {last_error}"
        )

    def _call_json_with_retry(self, messages, temperature=1.0, max_json_retries=2,
                              max_completion_tokens=6000, hard_token_cap=7500):
        last_error = None

        for attempt in range(max_json_retries):
            content = self._call_with_fallback(
                messages,
                temperature=temperature,
                json_mode=True,
                max_completion_tokens=max_completion_tokens,
                hard_token_cap=hard_token_cap,
            )
            try:
                try:
                    data = json.loads(_clean_json_response(content))
                except json.JSONDecodeError:
                    repaired = _repair_json_text(content)
                    if repaired is None:
                        raise
                    print("🩹 JSON malformé réparé localement.")
                    data = json.loads(repaired)

                # Bouclier de structure racine : liste brute -> dict
                if isinstance(data, list):
                    print("⚠️ Le LLM a renvoyé une liste au lieu d'un dictionnaire. Correction automatique appliquée.")
                    data = {"scenes": data}

                return data
            except json.JSONDecodeError as e:
                last_error = e
                print(f"⚠️ JSON malformé reçu (tentative {attempt + 1}/{max_json_retries}), "
                      f"nouvelle tentative avec budget de tokens augmenté...")
                max_completion_tokens = min(max_completion_tokens + 1000, min(7000, hard_token_cap))

        raise ValueError(f"Impossible d'obtenir un JSON valide après {max_json_retries} tentatives : {last_error}")

    def is_duplicate_topic_llm(self, candidate, history):
        if not history:
            return False, None
        recent = history[-15:]
        prompt = f"""Voici un nouveau sujet de video : "{candidate}"

Voici les 15 derniers sujets deja publies :
{chr(10).join(f"- {t}" for t in recent)}

Le nouveau sujet reprend-il le meme TYPE de concept qu'un des sujets deja publies,
meme si le lieu ou le nom propre change (ex: deux sujets sur un tunnel/souterrain/
passage cache, meme a des endroits differents, comptent comme le meme type) ?

Reponds uniquement en JSON : {{"is_duplicate_type": true/false, "matched_topic": "..." ou null}}"""

        data = self._call_json_with_retry(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_completion_tokens=300
        )
        if data.get("is_duplicate_type"):
            return True, data.get("matched_topic")
        return False, None

    def get_trending_topic(self, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")
        used_topics = load_topic_history()

        # --- Rotation forcee de categorie thematique ---
        THEME_CATEGORIES = [
            "un objet ou artefact physique disparu ou vole (bijou, manuscrit, tableau, relique, instrument scientifique)",
            "un personnage historique reel meconnu ou une affaire judiciaire oubliee",
            "un evenement etouffe ou censure (incendie suspect, epidemie cachee, scandale politique, sabotage)",
            "une loi, un reglement ou une tradition administrative absurde et reelle",
            "un phenomene architectural visible en surface (facade, statue, plaque, vitrail, gargouille) avec une histoire cachee",
            "une decouverte archeologique ou scientifique recente et peu connue",
        ]

        last_categories = load_last_categories(n=2)
        available_categories = [c for c in THEME_CATEGORIES if c not in last_categories] or THEME_CATEGORIES
        forced_category = random.choice(available_categories)

        # --- Rotation forcee de REGION ---
        last_regions = load_last_regions(n=REGION_LOOKBACK)
        available_regions = [r for r in FRENCH_REGIONS if r not in last_regions] or FRENCH_REGIONS
        forced_region = random.choice(available_regions)

        # --- Ban temporaire du champ lexical souterrain si sur-represente ---
        BANNED_IF_RECENT = ["tunnel", "souterrain", "passage secret", "catacombe", "salle secrete", "chambre secrete"]
        recent_topics_text = " ".join(used_topics[-8:]).lower() if used_topics else ""
        recent_ban_count = sum(recent_topics_text.count(w) for w in BANNED_IF_RECENT)

        ban_instruction = ""
        if recent_ban_count >= 2:
            ban_instruction = (
                "\n\nINTERDICTION TEMPORAIRE STRICTE : tu as trop utilise recemment les concepts de "
                "tunnel/souterrain/passage secret/catacombe/salle cachee. "
                "INTERDICTION ABSOLUE d'utiliser ces mots ou concepts dans ce nouveau sujet."
            )

        messages = [
            {"role": "system", "content": (
                "Tu es un createur de contenu ultra-creatif et totalement imprevisible. "
                "Ta force est la diversite absolue : tu ne recycles jamais tes structures de phrases, "
                "ton vocabulaire, ton angle d'attaque, ni ta zone geographique. "
                "Reponds uniquement avec un seul titre en francais, une seule ligne, sans guillemets, maximum 18 mots. "
                "Ne montre jamais ton raisonnement. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION} {VERACITY_INSTRUCTION}"
            )},
            {"role": "user", "content": (
                "Donne un sujet viral totalement inedit pour TikTok en francais, "
                "portant sur un fait historique REEL et verifiable, tres peu connu du grand public. "
                f"REGION IMPOSEE POUR CE SUJET : {forced_region}. "
                "Le lieu precis du sujet doit se situer dans cette region, PAS a Paris sauf si la region "
                "imposee est explicitement Paris. "
                f"CATEGORIE THEMATIQUE IMPOSEE POUR CE SUJET : {forced_category}. "
                "Le sujet doit appartenir A CETTE CATEGORIE UNIQUEMENT. "
                "Explore aussi bien les villages, provinces, littoral, montagne, sites ruraux ou industriels "
                "que les villes -- ne te limite jamais aux grandes metropoles. "
                "Alterne radicalement tes formats de titres a chaque fois : question provocante, "
                "affirmation brute, paradoxe frappant, ou simple anecdote ciblee."
                + ban_instruction
                + stats_instruction
                + (
                    "\n\nSUJETS DEJA TRAITES (Casse tes habitudes : propose un univers, un vocabulaire, un format "
                    "et une region radicalement differents de ce qui figure dans cette liste) :\n- "
                    + "\n- ".join(used_topics[-30:]) if used_topics else ""
                )
            )},
        ]

        last_topic = ""
        for attempt in range(5):
            content = self._call_with_fallback(
                messages, temperature=0.9, max_completion_tokens=2000
            )
            topic = _clean_single_line_title(content)
            last_topic = topic

            if _contains_ai_mention(topic):
                print(f"⚠️ Sujet rejeté (mention IA détectée, tentative {attempt + 1}) : {topic}")
                continue

            if recent_ban_count >= 2 and any(w in topic.lower() for w in BANNED_IF_RECENT):
                print(f"⚠️ Sujet rejeté (mot-clé souterrain banni temporairement, tentative {attempt + 1}) : {topic}")
                continue

            if not (topic and 4 <= len(topic.split()) <= 18):
                print(f"⚠️ Sujet invalide généré (tentative {attempt + 1}) : {topic}")
                continue

            is_dup, matched = is_duplicate_topic(topic, used_topics)
            if is_dup:
                print(f"⚠️ Sujet rejeté (doublon de '{matched}', tentative {attempt + 1}) : {topic}")
                continue

            # Sauvegarde des rotations une fois le sujet validé
            save_last_category(forced_category)
            save_last_region(forced_region)

            return topic

        raise ValueError(f"Impossible d'obtenir un sujet valide et unique après 5 tentatives : {last_topic}")

    def get_viral_inspired_topic(self, previous_stats_list=None):

        viral = fetch_viral_videos()

        # On ecarte les videos explicitement fictives / storytime : on veut du reel
        before = len(viral)
        viral = [v for v in viral if not _is_fiction_title(v.get("title", ""))]
        if before != len(viral):
            print(f"🧹 {before - len(viral)} vidéo(s) virale(s) fictive(s) écartée(s).")

        niche = [v for v in viral
                 if any(k in v["title"].lower() for k in NICHE_KEYWORDS)]
        viral = niche if len(niche) >= 3 else viral
        if not viral:
            print("⚠️ Aucune tendance virale, fallback sujet LLM libre.")
            return self.get_trending_topic(previous_stats_list)

        used_topics = load_topic_history()
        viral_text = "\n".join(f"- {v['title']} ({v['views_per_day']} vues/jour)" for v in viral)
        print("🎯 Tendances retenues pour la niche :\n" + viral_text)

        # Etape 1 : theme -> requetes Wikipedia
        data = self._call_json_with_retry([
            {"role": "system", "content": "Tu produis uniquement du JSON valide, sans raisonnement visible."},
            {"role": "user", "content": (
                f"Videos virales recentes :\n{viral_text}\n\n"
                "Identifie le theme et le ressort emotionnel dominants. "
                "Retourne un JSON {\"theme\": \"...\", \"wiki_queries\": [3 requetes courtes "
                "en francais pour chercher sur Wikipedia des faits historiques reels qui "
                "exploitent ce theme, en France de preference]}"
            )},
        ], temperature=0.7, max_completion_tokens=800)

        queries = [str(q) for q in data.get("wiki_queries", [])][:3]
        print(f"🧭 Theme viral : {data.get('theme')} | requetes : {queries}")

        candidates = wiki_candidates(queries)
        used_lower = " ".join(used_topics[-30:]).lower()
        candidates = [t for t in candidates if t.lower() not in used_lower][:25]
        if not candidates:
            print("⚠️ Aucun article Wikipedia candidat, fallback sujet LLM libre.")
            return self.get_trending_topic(previous_stats_list)

        # Etape 2 : choix parmi des articles reels
        for attempt in range(3):
            if not candidates:
                break
            pick = self._call_json_with_retry([
                {"role": "system", "content": (
                    "Tu produis uniquement du JSON valide. "
                    f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION}"
                )},
                {"role": "user", "content": (
                    f"Theme viral : {data.get('theme')}\n"
                    "Articles Wikipedia reels disponibles :\n- " + "\n- ".join(candidates) +
                    "\n\nChoisis UN article de cette liste, le plus mysterieux et le moins "
                    "connu, qui colle au theme. Retourne {\"wiki_title\": \"titre exact de la "
                    "liste\", \"topic\": \"accroche TikTok en francais, 18 mots max, "
                    "contenant le nom exact du lieu/sujet, SANS commencer par 'Découvrez'\"}"
                )},
            ], temperature=0.8, max_completion_tokens=800)

            raw_title = str(pick.get("wiki_title", "")).strip()
            wiki_title = _match_candidate(raw_title, candidates)
            topic = _clean_single_line_title(str(pick.get("topic", "")))

            if not wiki_title:
                print(f"⚠️ Titre hors liste, tentative {attempt + 1} : {raw_title}")
                continue
            if _contains_ai_mention(topic) or not (4 <= len(topic.split()) <= 18):
                print(f"⚠️ Rejeté (IA/longueur, tentative {attempt + 1}) : {topic}")
                continue
            is_dup, matched = is_duplicate_topic(topic, used_topics)
            if is_dup:
                print(f"⚠️ Rejeté (doublon de '{matched}') : {topic}")
                candidates.remove(wiki_title)
                continue

            print(f"✅ Sujet ancré sur l'article Wikipedia : {wiki_title}")
            return topic

        print("⚠️ Échec mode viral, fallback sujet LLM libre.")
        return self.get_trending_topic(previous_stats_list)

    def refine_topic_angle(self, raw_topic):
        messages = [
            {"role": "system", "content": (
                "Tu reformules le sujet en un titre accrocheur (max 14 mots), sans changer le theme "
                "ni la localisation geographique reelle du fait evoque. "
                "Ne commence JAMAIS par 'Découvrez' ni 'Plongez' : prefere une question "
                "provocante, un paradoxe ou une affirmation brute contenant le nom exact du lieu. "
                "Reponds uniquement avec le titre reformule, sans montrer ton raisonnement. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION} {VERACITY_INSTRUCTION}"
            )},
            {"role": "user", "content": f"Sujet brut / trend repere: {raw_topic}"},
        ]
        content = self._call_with_fallback(
            messages, temperature=0.8, max_completion_tokens=2000
        )
        refined = _clean_single_line_title(content)

        if not refined or _contains_ai_mention(refined):
            print(f"⚠️ Reformulation rejetée (vide ou mention IA détectée) : '{refined}' → on garde le sujet brut.")
            return _clean_single_line_title(raw_topic)

        return refined

    def generate_video_search_query(self, topic):
        messages = [
            {"role": "system", "content": (
                "Tu génères une requête de recherche visuelle en anglais, 6 mots max, "
                "sans phrase, sans raisonnement visible -- reponds directement avec la "
                "requete finale. Inclure des termes comme photorealistic, historical "
                "documentary, real photography, dark mysterious atmosphere. INTERDICTION "
                "ABSOLUE d'utiliser les mots CGI, 3D, render ou Unreal Engine."
            )},
            {"role": "user", "content": f"Sujet : {topic}"},
        ]
        content = self._call_with_fallback(
            messages, temperature=0.7, max_completion_tokens=1500
        )
        query = _clean_single_line_title(content).replace('"', '')

        if not query:
            return "photorealistic historical documentary dark atmosphere"
        return query

    def generate_hook_variants(self, topic, n=5, previous_stats_list=None, grounding_extract=None):
        """grounding_extract (optionnel) : extrait Wikipedia pour que les hooks
        ne contredisent/n'inventent rien par rapport a la source."""
        stats_instruction = _format_stats_instruction(previous_stats_list, label="hooks")
        grounding_instruction = ""
        if grounding_extract:
            grounding_instruction = (
                "\nSOURCE DE REFERENCE (les hooks doivent rester fideles a ces faits, "
                "sans rien inventer d'absent de l'extrait) :\n"
                f'"""{str(grounding_extract)[:800]}"""\n'
            )
        prompt = f"""
SUJET:
{topic}
{grounding_instruction}
GENERE {n} hooks viraux en francais (courts, 12 mots max, qui donnent envie de regarder la suite).

RETURNS JSON:
{{
  "hooks": [
    {{
      "text": "hook",
      "pattern": "question",
      "raison": "..."
    }}
  ]
}}

{stats_instruction}
"""
        messages = [
            {"role": "system", "content": (
                f"Tu produis uniquement du JSON valide avec exactement {n} hooks, "
                "sans aucun texte ni raisonnement en dehors du JSON. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION}"
            )},
            {"role": "user", "content": prompt},
        ]

        data = self._call_json_with_retry(
            messages, temperature=1.0, max_completion_tokens=4000
        )

        hooks = data.get("hooks")
        if not isinstance(hooks, list):
            raise ValueError("Champ hooks invalide.")

        normalized_hooks = []
        for h in hooks:
            if isinstance(h, str):
                text = h.strip()
                if text and not _contains_ai_mention(text):
                    normalized_hooks.append({"text": text, "pattern": "question", "raison": ""})
            elif isinstance(h, dict):
                text = str(h.get("text", "")).strip()
                if text and not _contains_ai_mention(text):
                    normalized_hooks.append({
                        "text": text,
                        "pattern": str(h.get("pattern", "question")).strip(),
                        "raison": str(h.get("raison", "")).strip()
                    })

        if not normalized_hooks:
            return [{"text": topic, "pattern": "default", "raison": ""}]

        # Tolerance : mieux vaut 3-4 bons hooks qu'un crash du pipeline
        if len(normalized_hooks) < n:
            print(f"⚠️ Seulement {len(normalized_hooks)}/{n} hooks valides, on continue avec ceux-là.")

        return normalized_hooks[:n]

    def propose_real_case(self, topic):
        if not GROUNDING_AVAILABLE:
            return {"case_name": None, "wiki_query": None, "source": None}

        hint_country = _guess_country_hint(topic) or "France"

        messages = [
            {"role": "system", "content": (
                "Tu proposes un cas historique REEL et verifiable, peu connu du "
                "grand public, correspondant exactement au sujet donne. "
                "ATTENTION : sois tres precis sur le lieu exact -- il existe "
                "souvent plusieurs legendes/lieux similaires dans differentes "
                "villes/regions (ex: plusieurs 'ponts du diable' en France a "
                "des endroits differents). Verifie mentalement que le lieu "
                "que tu proposes correspond exactement aux details du sujet "
                "(region, nom propre, contexte). "
                "Reponds UNIQUEMENT avec le nom propre exact du lieu/evenement/ "
                "personnage principal (celui qui a un article Wikipedia), sans "
                "phrase, sans guillemets, sans raisonnement visible, une seule ligne."
            )},
            {"role": "user", "content": f"Sujet : {topic}\n\nDonne le nom exact du cas reel principal a developper."},
        ]

        content = self._call_with_fallback(
            messages, temperature=0.3, max_completion_tokens=1500
        )
        case_name = _clean_single_line_title(content)

        if not case_name:
            return {"case_name": None, "wiki_query": None, "source": None}

        if hint_country:
            real_country = WikidataChecker.get_real_country(case_name, hint_country=hint_country)
            if real_country and not _countries_match(hint_country, real_country):
                print(f"⚠️ Lieu propose '{case_name}' semble incorrect "
                      f"(Wikidata: {real_country}, attendu: {hint_country}). "
                      f"Nouvelle tentative avec consigne renforcee...")

                messages_retry = [
                    {"role": "system", "content": (
                        "Tu proposes un cas historique REEL, peu connu, "
                        f"situe EXACTEMENT en {hint_country} (pas ailleurs). "
                        "Reponds UNIQUEMENT avec le nom propre exact du lieu, "
                        "sans phrase, sans guillemets, sans raisonnement visible, une seule ligne."
                    )},
                    {"role": "user", "content": f"Sujet : {topic}"},
                ]
                content_retry = self._call_with_fallback(
                    messages_retry, temperature=0.3, max_completion_tokens=1500
                )
                case_name_retry = _clean_single_line_title(content_retry)
                if case_name_retry:
                    case_name = case_name_retry

        source = fetch_grounding_source(case_name, hint_country=hint_country)

        if source and not _source_matches_case(case_name, source.get("title", "")):
            print(f"🚫 Source rejetée : '{source.get('title')}' ne correspond pas à '{case_name}'.")
            source = None

        return {
            "case_name": case_name,
            "wiki_query": case_name,
            "source": source,
        }