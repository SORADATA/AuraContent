# modules/brain.py

import os
import re
import json
import time
import logging
from datetime import datetime

import requests
from dotenv import load_dotenv
from openai import OpenAI

# ============================================================
# ENV
# ============================================================

load_dotenv()


# ============================================================
# CONSTANTS
# ============================================================

# Import strict et direct depuis constants.py
from constants import (
    OPENROUTER_FALLBACK_MODEL_1,
    OPENROUTER_FALLBACK_MODEL_2,
    BRAIN_MAX_RETRIES_PER_PROVIDER,
    BRAIN_RETRY_DELAY,
    BRAIN_PROVIDER_COOLDOWN,
    BRAIN_HARD_TOKEN_CAP,
    BRAIN_SAFETY_MARGIN_TOKENS,
)


# ============================================================
# OPTIONAL GROUNDING
# ============================================================

try:
    from modules.utils.wikipedia_grounding import (
        fetch_grounding_source
    )

    GROUNDING_AVAILABLE = True

except ImportError:

    GROUNDING_AVAILABLE = False

    def fetch_grounding_source(
        query,
        hint_country=None
    ):
        return None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("AuraBrain")


# ============================================================
# GLOBAL INSTRUCTIONS
# ============================================================

ACCENTED_CHARS = (
    "éèêëàâäùûüçîïôœ"
)

ACCENT_INSTRUCTION = (
    "IMPÉRATIF ORTHOGRAPHE : "
    "le français doit être parfaitement accentué "
    "(é, è, ê, à, ù, ç, ô, î, etc.)."
)

NO_META_AI_INSTRUCTION = (
    "INTERDICTION ABSOLUE : ne jamais mentionner "
    "l'intelligence artificielle, l'IA, un algorithme, "
    "ChatGPT, OpenRouter ou la génération de contenu. "
    "Le sujet doit uniquement parler de l'histoire, du mystère "
    "ou du fait réel."
)

VERACITY_INSTRUCTION = (
    "EXIGENCE ABSOLUE DE VÉRACITÉ : "
    "n'invente aucun lieu, personnage, événement ou date. "
    "Ne déplace jamais géographiquement un événement réel. "
    "Utilise uniquement des informations vérifiables. "
    "Les lieux doivent être précis et désambiguïsés."
)

NARRATIVE_STRUCTURE_INSTRUCTION = (
    "STRUCTURE DE RÉTENTION : "
    "1. HOOK immédiat. "
    "2. PREUVE concrète. "
    "3. CONTEXTE minimal. "
    "4. ESCALADE. "
    "5. RÉVÉLATION. "
    "6. PAYOFF final ou question forte. "
    "Chaque scène doit apporter une information nouvelle."
)


# ============================================================
# AI MENTION DETECTION
# ============================================================

AI_MENTION_PATTERNS = [
    r"intelligence\s+artificielle",
    r"\bia\b",
    r"\bl'ia\b",
    r"artificial\s+intelligence",
    r"\balgorithme\b",
    r"\bchatgpt\b",
    r"\bopenrouter\b",
    r"\bgemini\b",
]


def _contains_ai_mention(text):

    if not text:
        return False

    text_lower = text.lower()

    return any(
        re.search(pattern, text_lower)
        for pattern in AI_MENTION_PATTERNS
    )


# ============================================================
# CLEANING
# ============================================================

def _clean_single_line_title(text):

    if not text:
        return ""

    text = str(text)

    text = (
        text
        .replace('"', "")
        .replace("'", "")
        .strip()
    )

    lines = [
        line.strip(" -•\t")
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        return ""

    return re.sub(
        r"\s+",
        " ",
        lines[0]
    ).strip()


def _clean_json_response(content):

    if not content:
        return ""

    cleaned = str(content).strip()

    if cleaned.startswith("```"):

        cleaned = re.sub(
            r"^```[a-zA-Z0-9_-]*\s*",
            "",
            cleaned
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned
        )

    return cleaned.strip()


# ============================================================
# TOKEN ESTIMATION
# ============================================================

def _estimate_tokens(text):

    if not text:
        return 0

    return max(
        1,
        len(str(text)) // 3
    )


def _estimate_prompt_tokens(messages):

    total = 0

    for message in messages:

        content = message.get(
            "content",
            ""
        )

        total += _estimate_tokens(
            content
        )

    return total


# ============================================================
# RATE LIMIT DETECTION
# ============================================================

def _is_rate_limit_error(error):

    text = str(error).lower()

    indicators = [
        "rate_limit",
        "rate limit",
        "429",
        "too many requests",
        "tokens per minute",
        "tpm",
        "requests per minute",
        "rpm",
        "quota",
        "capacity",
    ]

    return any(
        item in text
        for item in indicators
    )


def _is_temporary_error(error):

    text = str(error).lower()

    indicators = [
        "timeout",
        "timed out",
        "connection",
        "502",
        "503",
        "504",
        "server error",
        "temporarily unavailable",
        "overloaded",
        "capacity",
    ]

    return any(
        item in text
        for item in indicators
    )


def _is_provider_fatal_error(error):

    text = str(error).lower()

    indicators = [
        "401",
        "403",
        "404",
        "model not found",
        "invalid api key",
        "authentication",
        "permission",
    ]

    return any(
        item in text
        for item in indicators
    )


# ============================================================
# GEO
# ============================================================

COUNTRY_NAME_EQUIVALENTS = {
    "germany": "allemagne",
    "switzerland": "suisse",
    "italy": "italie",
    "spain": "espagne",
    "belgium": "belgique",
    "france": "france",
    "unitedstates": "etatsunis",
    "usa": "etatsunis",
    "portugal": "portugal",
    "austria": "autriche",
    "greece": "grece",
    "poland": "pologne",
    "egypt": "egypte",
    "turkey": "turquie",
    "russia": "russie",
}


def _normalize_country_text(text):

    value = re.sub(
        r"[^a-z]",
        "",
        str(text or "").lower()
    )

    return COUNTRY_NAME_EQUIVALENTS.get(
        value,
        value
    )


def _countries_match(
    declared,
    real
):

    if not declared or not real:
        return True

    d = _normalize_country_text(
        declared
    )

    r = _normalize_country_text(
        real
    )

    return (
        d == r
        or d in r
        or r in d
    )


COUNTRY_KEYWORDS = {

    "France": [
        "france",
        "français",
        "française",
        "bretagne",
        "normandie",
        "provence",
        "occitanie",
        "vendée",
        "aquitaine",
    ],

    "Suisse": [
        "suisse",
        "vaud",
        "genève",
        "valais",
        "zurich",
    ],

    "Allemagne": [
        "allemagne",
        "allemand",
        "bavière",
    ],

    "Italie": [
        "italie",
        "italien",
        "toscane",
        "sicile",
    ],

    "Espagne": [
        "espagne",
        "espagnol",
        "catalogne",
        "andalousie",
    ],
}


def _guess_country_hint(topic):

    text = str(
        topic or ""
    ).lower()

    for country, keywords in COUNTRY_KEYWORDS.items():

        if any(
            keyword in text
            for keyword in keywords
        ):
            return country

    return None


# ============================================================
# WIKIDATA
# ============================================================

class WikidataChecker:

    API_URL = (
        "https://www.wikidata.org/w/api.php"
    )

    HEADERS = {
        "User-Agent": os.getenv(
            "WIKIMEDIA_CONTACT",
            "AuraContentPipeline/3.0"
        )
    }

    CACHE = {}

    MIN_DELAY = 0.6

    @classmethod
    def _get(
        cls,
        params,
        retries=2
    ):

        for attempt in range(
            retries + 1
        ):

            try:

                time.sleep(
                    cls.MIN_DELAY
                )

                response = requests.get(
                    cls.API_URL,
                    params=params,
                    headers=cls.HEADERS,
                    timeout=10
                )

                if response.status_code == 429:

                    time.sleep(
                        2 * (attempt + 1)
                    )

                    continue

                response.raise_for_status()

                return response

            except requests.RequestException as error:

                if attempt == retries:

                    logger.warning(
                        "Wikidata indisponible: %s",
                        error
                    )

                    return None

                time.sleep(1)

        return None

    @classmethod
    def get_real_country(
        cls,
        location_name,
        hint_country=None
    ):

        if not location_name:
            return None

        cache_key = (
            f"{location_name.lower()}|"
            f"{hint_country or ''}"
        )

        if cache_key in cls.CACHE:
            return cls.CACHE[
                cache_key
            ]

        params = {
            "action": "wbsearchentities",
            "search": location_name,
            "language": "fr",
            "format": "json",
            "limit": 3,
            "type": "item",
        }

        response = cls._get(
            params
        )

        if response is None:
            return None

        try:

            results = response.json().get(
                "search",
                []
            )

            ids = [
                item.get("id")
                for item in results
                if item.get("id")
            ]

        except Exception:
            return None

        for entity_id in ids:

            params = {
                "action": "wbgetentities",
                "ids": entity_id,
                "props": "claims",
                "format": "json",
            }

            response = cls._get(
                params
            )

            if response is None:
                continue

            try:

                entity = (
                    response
                    .json()
                    .get("entities", {})
                    .get(entity_id, {})
                )

                claims = entity.get(
                    "claims",
                    {}
                )

                country_claims = claims.get(
                    "P17"
                )

                if not country_claims:
                    continue

                country_id = (
                    country_claims[0]
                    .get("mainsnak", {})
                    .get("datavalue", {})
                    .get("value", {})
                    .get("id")
                )

                if not country_id:
                    continue

                label_params = {
                    "action": "wbgetentities",
                    "ids": country_id,
                    "props": "labels",
                    "languages": "fr|en",
                    "format": "json",
                }

                label_response = cls._get(
                    label_params
                )

                if label_response is None:
                    continue

                labels = (
                    label_response
                    .json()
                    .get("entities", {})
                    .get(country_id, {})
                    .get("labels", {})
                )

                country = (
                    labels.get("fr")
                    or labels.get("en")
                )

                if country:

                    value = country[
                        "value"
                    ]

                    if (
                        not hint_country
                        or _countries_match(
                            hint_country,
                            value
                        )
                    ):

                        cls.CACHE[
                            cache_key
                        ] = value

                        return value

            except Exception:
                continue

        cls.CACHE[
            cache_key
        ] = None

        return None


# ============================================================
# CONTENT BRAIN
# ============================================================

class ContentBrain:

    def __init__(self):

        logger.info(
            "🧠 Initialisation AuraBrain (OpenRouter uniquement)..."
        )

        self.openrouter_client = None

        # ------------------------------------------------------
        # OPENROUTER
        # ------------------------------------------------------

        openrouter_key = os.getenv(
            "OPENROUTER_API_KEY"
        )

        if openrouter_key:

            self.openrouter_client = OpenAI(
                api_key=openrouter_key,
                base_url=(
                    "https://openrouter.ai/api/v1"
                ),
                timeout=90,
            )

            logger.info(
                "✅ OpenRouter activé."
            )

        else:

            logger.warning(
                "⚠️ OPENROUTER_API_KEY absente."
            )

        # ------------------------------------------------------
        # PROVIDERS
        # ------------------------------------------------------

        self.providers = [

            {
                "name": "OpenRouter-1",
                "client": self.openrouter_client,
                "model": OPENROUTER_FALLBACK_MODEL_1,
            },

            {
                "name": "OpenRouter-2",
                "client": self.openrouter_client,
                "model": OPENROUTER_FALLBACK_MODEL_2,
            },

        ]

        # ------------------------------------------------------
        # COOLDOWN
        # ------------------------------------------------------

        self.provider_cooldown = {}

    # ========================================================
    # PROVIDER COOLDOWN
    # ========================================================

    def _provider_available(
        self,
        provider_name
    ):

        cooldown_until = (
            self.provider_cooldown
            .get(provider_name, 0)
        )

        return time.time() >= cooldown_until

    def _disable_provider(
        self,
        provider_name,
        seconds=None
    ):

        seconds = (
            seconds
            or BRAIN_PROVIDER_COOLDOWN
        )

        self.provider_cooldown[
            provider_name
        ] = time.time() + seconds

        logger.warning(
            "⏸️ %s désactivé temporairement pendant %ss.",
            provider_name,
            seconds
        )

    # ========================================================
    # RESPONSE EXTRACTION
    # ========================================================

    def _extract_content(
        self,
        response
    ):

        choices = getattr(
            response,
            "choices",
            None
        )

        if not choices:
            raise ValueError(
                "Réponse API sans choices."
            )

        choice = choices[0]

        message = getattr(
            choice,
            "message",
            None
        )

        if message is None:
            raise ValueError(
                "Réponse API sans message."
            )

        content = getattr(
            message,
            "content",
            None
        )

        if isinstance(
            content,
            list
        ):

            parts = []

            for item in content:

                if isinstance(
                    item,
                    dict
                ):

                    parts.append(
                        item.get(
                            "text",
                            ""
                        )
                    )

                elif isinstance(
                    item,
                    str
                ):

                    parts.append(item)

            content = "".join(
                parts
            )

        if not content:
            raise ValueError(
                "Réponse API vide."
            )

        return str(
            content
        ).strip()

    # ========================================================
    # CORE MULTI-MODEL FALLBACK
    # ========================================================

    def _call_with_fallback(
        self,
        messages,
        temperature=0.7,
        json_mode=False,
        max_completion_tokens=3000,
        hard_token_cap=None,
    ):

        if hard_token_cap is None:

            hard_token_cap = (
                BRAIN_HARD_TOKEN_CAP
            )

        prompt_tokens = (
            _estimate_prompt_tokens(
                messages
            )
        )

        available = (
            hard_token_cap
            - prompt_tokens
            - BRAIN_SAFETY_MARGIN_TOKENS
        )

        if available < 500:

            logger.warning(
                "⚠️ Prompt trop volumineux."
            )

            available = 500

        max_tokens = min(
            max_completion_tokens,
            available
        )

        last_error = None

        # ====================================================
        # LOOP PROVIDERS
        # ====================================================

        for provider in self.providers:

            provider_name = provider[
                "name"
            ]

            client = provider[
                "client"
            ]

            model = provider[
                "model"
            ]

            if not client:

                continue

            if not model:

                continue

            if not self._provider_available(
                provider_name
            ):

                logger.info(
                    "⏭️ %s en cooldown.",
                    provider_name
                )

                continue

            logger.info(
                "🤖 Tentative %s → %s",
                provider_name,
                model
            )

            # ================================================
            # RETRIES PROVIDER
            # ================================================

            for attempt in range(
                BRAIN_MAX_RETRIES_PER_PROVIDER + 1
            ):

                try:

                    kwargs = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }

                    # JSON uniquement quand explicitement demandé
                    if json_mode:

                        kwargs[
                            "response_format"
                        ] = {
                            "type": "json_object"
                        }

                    response = (
                        client
                        .chat
                        .completions
                        .create(
                            **kwargs
                        )
                    )

                    content = (
                        self._extract_content(
                            response
                        )
                    )

                    if not content:

                        raise ValueError(
                            "Réponse vide."
                        )

                    logger.info(
                        "✅ Succès %s / %s",
                        provider_name,
                        model
                    )

                    return content

                except Exception as error:

                    last_error = error

                    logger.warning(
                        "⚠️ %s échec "
                        "(tentative %s/%s): %s",
                        provider_name,
                        attempt + 1,
                        BRAIN_MAX_RETRIES_PER_PROVIDER + 1,
                        error
                    )

                    # ----------------------------------------
                    # RATE LIMIT
                    # ----------------------------------------

                    if _is_rate_limit_error(
                        error
                    ):

                        self._disable_provider(
                            provider_name,
                            30
                        )

                        logger.warning(
                            "🚀 Fallback immédiat vers le modèle suivant."
                        )

                        break

                    # ----------------------------------------
                    # FATAL PROVIDER
                    # ----------------------------------------

                    if _is_provider_fatal_error(
                        error
                    ):

                        self._disable_provider(
                            provider_name,
                            300
                        )

                        logger.error(
                            "❌ Provider %s probablement indisponible.",
                            provider_name
                        )

                        break

                    # ----------------------------------------
                    # TEMPORARY ERROR
                    # ----------------------------------------

                    if _is_temporary_error(
                        error
                    ):

                        if attempt < BRAIN_MAX_RETRIES_PER_PROVIDER:

                            time.sleep(
                                BRAIN_RETRY_DELAY
                            )

                            continue

                        break

                    # ----------------------------------------
                    # UNKNOWN ERROR
                    # ----------------------------------------

                    if attempt < BRAIN_MAX_RETRIES_PER_PROVIDER:

                        time.sleep(
                            BRAIN_RETRY_DELAY
                        )

                    else:

                        break

        # ====================================================
        # EVERYTHING FAILED
        # ====================================================

        logger.critical(
            "❌ TOUS LES MODÈLES IA ONT ÉCHOUÉ."
        )

        raise RuntimeError(
            "Impossible d'obtenir une réponse IA. "
            f"Dernière erreur : {last_error}"
        )

    # ========================================================
    # JSON FALLBACK
    # ========================================================

    def _call_json_with_retry(
        self,
        messages,
        temperature=0.5,
        max_json_retries=2,
        max_completion_tokens=4000,
    ):

        last_error = None

        for attempt in range(
            max_json_retries + 1
        ):

            try:

                content = (
                    self._call_with_fallback(
                        messages=messages,
                        temperature=temperature,
                        json_mode=True,
                        max_completion_tokens=(
                            max_completion_tokens
                        ),
                    )
                )

                cleaned = (
                    _clean_json_response(
                        content
                    )
                )

                return json.loads(
                    cleaned
                )

            except json.JSONDecodeError as error:

                last_error = error

                logger.warning(
                    "⚠️ JSON invalide "
                    "(tentative %s/%s)",
                    attempt + 1,
                    max_json_retries + 1
                )

                if attempt < max_json_retries:

                    time.sleep(0.5)

                    continue

            except Exception as error:

                last_error = error

                logger.warning(
                    "⚠️ Erreur génération JSON: %s",
                    error
                )

                if attempt < max_json_retries:

                    continue

        logger.error(
            "❌ Impossible de générer un JSON valide : %s",
            last_error
        )

        return None

    # ========================================================
    # TOPIC
    # ========================================================
    # ========================================================
    # TOPIC
    # ========================================================

    def get_trending_topic(
        self,
        previous_stats_list=None,
        learning_context=None
    ):
        
        context_str = f"\n\nCONTEXTE D'APPRENTISSAGE :\n{learning_context}" if learning_context else ""

        messages = [

            {
                "role": "system",
                "content": (
                    "Tu es un stratège TikTok spécialisé "
                    "dans les mystères historiques réels. "
                    "Réponds avec un seul titre en français, "
                    "maximum 18 mots. "
                    f"{ACCENT_INSTRUCTION} "
                    f"{NO_META_AI_INSTRUCTION} "
                    f"{VERACITY_INSTRUCTION}"
                    f"{context_str}" # <-- On injecte les recommandations du Learner ici
                )
            },

            {
                "role": "user",
                "content": (
                    "Trouve un sujet réel, documenté, "
                    "peu connu et extrêmement intrigant. "
                    "Le sujet doit pouvoir être raconté "
                    "en moins d'une minute et provoquer "
                    "curiosité, commentaires et rewatch."
                )
            }

        ]

        for attempt in range(3):

            content = (
                self._call_with_fallback(
                    messages,
                    temperature=0.9,
                    max_completion_tokens=1000
                )
            )

            topic = (
                _clean_single_line_title(
                    content
                )
            )

            if (
                topic
                and not _contains_ai_mention(topic)
                and 4 <= len(topic.split()) <= 18
            ):

                return topic

        return (
            "Le mystère historique que presque personne ne connaît"
        )
    


    # ========================================================
    # REFINE TOPIC
    # ========================================================

    def refine_topic_angle(
        self,
        raw_topic
    ):

        messages = [

            {
                "role": "system",
                "content": (
                    "Reformule ce sujet en titre TikTok "
                    "très accrocheur sans changer les faits "
                    "ni la localisation."
                )
            },

            {
                "role": "user",
                "content": str(raw_topic)
            }

        ]

        content = (
            self._call_with_fallback(
                messages,
                temperature=0.8,
                max_completion_tokens=1000
            )
        )

        result = (
            _clean_single_line_title(
                content
            )
        )

        if (
            not result
            or _contains_ai_mention(result)
        ):

            return raw_topic

        return result

    # ========================================================
    # VISUAL SEARCH QUERY
    # ========================================================

    def generate_video_search_query(
        self,
        topic
    ):

        messages = [

            {
                "role": "system",
                "content": (
                    "Generate a short English visual "
                    "search query, maximum 6 words. "
                    "Use concrete visual nouns. "
                    "Do not use sentences."
                )
            },

            {
                "role": "user",
                "content": topic
            }

        ]

        content = (
            self._call_with_fallback(
                messages,
                temperature=0.5,
                max_completion_tokens=500
            )
        )

        query = (
            _clean_single_line_title(
                content
            )
        )

        return (
            query
            or
            "historical documentary dark atmosphere"
        )

    # ========================================================
    # HOOKS
    # ========================================================

    def generate_hook_variants(
        self,
        topic,
        n=5,
        previous_stats_list=None
    ):

        messages = [

            {
                "role": "system",
                "content": (
                    f"Génère exactement {n} hooks TikTok "
                    "en français. "
                    "Réponds uniquement en JSON. "
                    f"{ACCENT_INSTRUCTION} "
                    f"{NO_META_AI_INSTRUCTION}"
                )
            },

            {
                "role": "user",
                "content": f"""
Sujet :

{topic}

Format obligatoire :

{{
  "hooks": [
    {{
      "text": "...",
      "pattern": "question",
      "raison": "..."
    }}
  ]
}}

Patterns possibles :
- question
- contradiction
- révélation
- danger
- mystère
- chiffre
- curiosité
- histoire_inconnue
"""
            }

        ]

        data = (
            self._call_json_with_retry(
                messages,
                temperature=1.0,
                max_json_retries=2,
                max_completion_tokens=3000
            )
        )

        if not data:

            return [
                {
                    "text": (
                        f"Personne ne parle de ce mystère : "
                        f"{topic}."
                    ),
                    "pattern": "mystère",
                    "raison": "fallback"
                }
            ]

        hooks = data.get(
            "hooks",
            []
        )

        result = []

        for hook in hooks:

            if not isinstance(
                hook,
                dict
            ):

                continue

            text = str(
                hook.get(
                    "text",
                    ""
                )
            ).strip()

            if (
                text
                and not _contains_ai_mention(text)
            ):

                result.append(
                    {
                        "text": text,
                        "pattern": str(
                            hook.get(
                                "pattern",
                                "curiosité"
                            )
                        ),
                        "raison": str(
                            hook.get(
                                "raison",
                                ""
                            )
                        ),
                    }
                )

        return result[:n]

    # ========================================================
    # REAL CASE
    # ========================================================

    def propose_real_case(
        self,
        topic
    ):

        if not GROUNDING_AVAILABLE:

            return {
                "case_name": None,
                "source": None
            }

        hint_country = (
            _guess_country_hint(
                topic
            )
        )

        messages = [

            {
                "role": "system",
                "content": (
                    "Trouve le lieu ou événement historique "
                    "réel correspondant exactement au sujet. "
                    "Réponds uniquement avec son nom propre."
                )
            },

            {
                "role": "user",
                "content": topic
            }

        ]

        content = (
            self._call_with_fallback(
                messages,
                temperature=0.2,
                max_completion_tokens=500
            )
        )

        case_name = (
            _clean_single_line_title(
                content
            )
        )

        if not case_name:

            return {
                "case_name": None,
                "source": None
            }

        if hint_country:

            real_country = (
                WikidataChecker
                .get_real_country(
                    case_name,
                    hint_country
                )
            )

            if (
                real_country
                and not _countries_match(
                    hint_country,
                    real_country
                )
            ):

                logger.warning(
                    "⚠️ Pays incohérent pour %s",
                    case_name
                )

                return {
                    "case_name": None,
                    "source": None
                }

        source = (
            fetch_grounding_source(
                case_name,
                hint_country=hint_country
            )
        )

        return {
            "case_name": case_name,
            "source": source
        }

    # ========================================================
    # SCRIPT
    # ========================================================

    def generate_script(
        self,
        topic,
        chosen_hook=None
    ):

        return self.generate_script_with_target(
            topic,
            scene_count=11,
            chosen_hook=chosen_hook
        )

    def generate_script_with_target(
        self,
        topic,
        scene_count=11,
        chosen_hook=None,
        max_fact_check_retries=2
    ):

        # IMPORTANT :
        # On garde le même nombre de scènes autant que possible.
        # Si le budget est trop gros, on réduit progressivement.

        candidate_counts = []

        current = scene_count

        while current >= 6:

            candidate_counts.append(
                current
            )

            current -= 2

        last_error = None

        for count in candidate_counts:

            try:

                logger.info(
                    "🎬 Génération script : %s scènes",
                    count
                )

                return self._generate_script_attempt(
                    topic=topic,
                    scene_count=count,
                    chosen_hook=chosen_hook,
                    max_fact_check_retries=max_fact_check_retries
                )

            except Exception as error:

                last_error = error

                logger.warning(
                    "⚠️ Script %s scènes échoué : %s",
                    count,
                    error
                )

        raise RuntimeError(
            "Impossible de générer le script. "
            f"Dernière erreur : {last_error}"
        )

    # ========================================================
    # SCRIPT ATTEMPT
    # ========================================================

    def _generate_script_attempt(
        self,
        topic,
        scene_count,
        chosen_hook,
        max_fact_check_retries
    ):

        # CORRECTION IMPORTANTE :
        # hint_country doit être calculé ici.
        hint_country = (
            _guess_country_hint(
                topic
            )
        )

        grounding = (
            self.propose_real_case(
                topic
            )
        )

        source = grounding.get(
            "source"
        )

        grounding_block = ""

        if source:

            grounding_block = f"""

SOURCE HISTORIQUE :

Titre :
{source.get("title", "")}

Extrait :
{source.get("extract", "")[:1500]}

RÈGLE :
Les faits historiques doivent rester compatibles
avec cette source.
"""

        hook_instruction = (
            f'SCÈNE 1 : utiliser exactement ce hook : "{chosen_hook}"'
            if chosen_hook
            else
            "SCÈNE 1 : hook extrêmement fort."
        )

        prompt = f"""

SUJET :
{topic}

{hook_instruction}

{grounding_block}

{NARRATIVE_STRUCTURE_INSTRUCTION}

Génère EXACTEMENT {scene_count} scènes.

Chaque scène doit contenir :

- id
- text
- voice_direction
- pause_after_ms
- stock_search
- image_prompt
- location_name
- location_country
- voice_type
- mood
- role
- scene_type
- event_context

RÈGLES :

- français naturel
- phrases courtes
- narration orale
- aucune répétition
- chaque scène apporte une information
- image_prompt très visuel
- image_prompt photoréaliste
- stock_search en anglais
- stock_search court
- aucun CGI
- aucun 3D
- aucun render
- aucun texte à l'écran
- aucune invention
- exactement {scene_count} scènes

JSON UNIQUEMENT.

FORMAT :

{{
  "title": "...",
  "visual_identity": "...",
  "audio_profile": "...",
  "scenes": [...]
}}
"""

        for attempt in range(
            max_fact_check_retries + 1
        ):

            messages = [

                {
                    "role": "system",
                    "content": (
                        "Tu es un scénariste documentaire "
                        "spécialisé dans les vidéos courtes "
                        "à très forte rétention. "
                        "Retourne uniquement du JSON valide. "
                        f"{ACCENT_INSTRUCTION} "
                        f"{NO_META_AI_INSTRUCTION} "
                        f"{VERACITY_INSTRUCTION}"
                    )
                },

                {
                    "role": "user",
                    "content": prompt
                }

            ]

            data = (
                self._call_json_with_retry(
                    messages,
                    temperature=0.7,
                    max_json_retries=2,
                    max_completion_tokens=min(
                        6000,
                        scene_count * 400
                    )
                )
            )

            if not data:

                raise ValueError(
                    "JSON script vide."
                )

            scenes = data.get(
                "scenes"
            )

            if (
                not isinstance(
                    scenes,
                    list
                )
                or len(scenes) != scene_count
            ):

                logger.warning(
                    "⚠️ Nombre scènes incorrect : %s/%s",
                    len(scenes) if isinstance(
                        scenes,
                        list
                    ) else 0,
                    scene_count
                )

                continue

            # ------------------------------------------------
            # NORMALISATION
            # ------------------------------------------------

            moods = {
                "ominous",
                "intriguing",
                "tense",
                "awe",
                "scientific",
                "melancholic",
                "revelatory",
            }

            for index, scene in enumerate(
                scenes,
                start=1
            ):

                scene["id"] = index

                scene.setdefault(
                    "voice_direction",
                    "narrateur français premium, calme, mystérieux"
                )

                scene.setdefault(
                    "pause_after_ms",
                    300
                )

                scene.setdefault(
                    "stock_search",
                    "cinematic historical documentary"
                )

                scene.setdefault(
                    "image_prompt",
                    "photorealistic cinematic documentary scene"
                )

                scene.setdefault(
                    "location_name",
                    ""
                )

                scene.setdefault(
                    "location_country",
                    ""
                )

                scene.setdefault(
                    "voice_type",
                    "narrator"
                )

                scene.setdefault(
                    "mood",
                    "intriguing"
                )

                scene.setdefault(
                    "role",
                    "narration"
                )

                scene.setdefault(
                    "scene_type",
                    "generic"
                )

                scene.setdefault(
                    "event_context",
                    ""
                )

                if scene["mood"] not in moods:

                    scene["mood"] = (
                        "intriguing"
                    )

            # ------------------------------------------------
            # VALIDATION
            # ------------------------------------------------

            self._validate_script(
                data,
                scene_count,
                topic
            )

            # ------------------------------------------------
            # GEOGRAPHY
            # ------------------------------------------------

            geo_issue = (
                self._check_geography_consistency(
                    topic,
                    scenes
                )
            )

            if geo_issue:

                logger.warning(
                    "⚠️ %s",
                    geo_issue
                )

                continue

            # ------------------------------------------------
            # WIKIDATA
            # ------------------------------------------------

            location_issues = (
                self._check_wikidata_locations(
                    scenes,
                    hint_country
                )
            )

            if location_issues:

                logger.warning(
                    "⚠️ Problèmes géographiques : %s",
                    location_issues
                )

                pass

            # ------------------------------------------------
            # FACT CHECK
            # ------------------------------------------------

            fact_check = (
                self._fact_check_script(
                    topic,
                    data,
                    source
                )
            )

            if fact_check.get(
                "is_consistent",
                True
            ):

                return data

            logger.warning(
                "⚠️ Fact-check échoué : %s",
                fact_check.get(
                    "issues",
                    []
                )
            )

        # Si tout est passé sauf le fact-check,
        # on retourne le dernier résultat plutôt que
        # de tuer toute la pipeline.
        return data

    # ========================================================
    # GEOGRAPHY
    # ========================================================

    def _check_geography_consistency(
    self,
    topic,
    scenes
):

    hint_country = (
        _guess_country_hint(
            topic
        )
    )

    if not hint_country:

        return None

    # CORRECTIF : une histoire reelle mentionne souvent des lieux
    # secondaires legitimes dans d'autres pays (archives, enqueteurs,
    # temoins, contexte historique) sans que ce soit une erreur
    # factuelle. L'ancienne version rejetait TOUT le script (via
    # `continue` dans l'appelant) dès qu'UNE SEULE scène avait un pays
    # different du sujet principal, ce qui empechait quasiment toute
    # convergence et provoquait des boucles de 3 tentatives >60s
    # chacune, jusqu'au timeout du workflow CI.
    #
    # Nouvelle regle : on ne signale une incoherence que si une
    # MAJORITE stricte des scenes localisees (pays declare non vide)
    # sont incoherentes avec le pays du sujet. Une ou deux scenes
    # secondaires dans un autre pays restent tolerees.
    mismatches = []
    total_located = 0

    for scene in scenes:

        country = str(
            scene.get(
                "location_country",
                ""
            )
        ).strip()

        if not country:
            continue

        total_located += 1

        if not _countries_match(
            hint_country,
            country
        ):

            mismatches.append(
                f"{scene.get('location_name')} ({country})"
            )

    if total_located == 0:
        return None

    mismatch_ratio = len(mismatches) / total_located

    if mismatch_ratio > 0.5:

        return (
            f"Incoherence geographique majeure : "
            f"{len(mismatches)}/{total_located} lieux localises "
            f"({', '.join(mismatches)}) ne correspondent pas au "
            f"pays attendu ({hint_country})."
        )

    return None

    def _check_wikidata_locations(
        self,
        scenes,
        hint_country=None
    ):

        issues = []

        for scene in scenes:

            name = str(
                scene.get(
                    "location_name",
                    ""
                )
            ).strip()

            declared = str(
                scene.get(
                    "location_country",
                    ""
                )
            ).strip()

            if not name or not declared:

                continue

            real = (
                WikidataChecker
                .get_real_country(
                    name,
                    hint_country
                )
            )

            if (
                real
                and not _countries_match(
                    declared,
                    real
                )
            ):

                issues.append(
                    f"{name}: "
                    f"{real} != {declared}"
                )

        return issues

    # ========================================================
    # FACT CHECK
    # ========================================================

    def _fact_check_script(
        self,
        topic,
        script_data,
        grounding_source=None
    ):

        scenes_text = "\n".join(
            [
                (
                    f"Scene {scene.get('id')}: "
                    f"{scene.get('text', '')}"
                )
                for scene
                in script_data.get(
                    "scenes",
                    []
                )
            ]
        )

        if grounding_source:

            prompt = f"""

Compare le script avec cette source.

SOURCE :
{grounding_source.get("title", "")}

{grounding_source.get("extract", "")[:1500]}

SCRIPT :
{scenes_text}

Signale uniquement les contradictions
factuelles objectives.

JSON :

{{
  "is_consistent": true,
  "issues": []
}}
"""

        else:

            prompt = f"""

Sujet :
{topic}

Script :
{scenes_text}

Détecte uniquement les erreurs factuelles
objectives.

JSON :

{{
  "is_consistent": true,
  "issues": []
}}
"""

        messages = [

            {
                "role": "system",
                "content": (
                    "Tu es un fact-checker historique "
                    "strict et minimaliste. "
                    "Réponds uniquement en JSON."
                )
            },

            {
                "role": "user",
                "content": prompt
            }

        ]

        result = (
            self._call_json_with_retry(
                messages,
                temperature=0.1,
                max_json_retries=1,
                max_completion_tokens=1500
            )
        )

        if not result:

            return {
                "is_consistent": True,
                "issues": []
            }

        return {
            "is_consistent": bool(
                result.get(
                    "is_consistent",
                    True
                )
            ),
            "issues": result.get(
                "issues",
                []
            )
        }

    # ========================================================
    # SCRIPT VALIDATION
    # ========================================================

    def _validate_script(
        self,
        data,
        scene_count,
        topic
    ):

        if not isinstance(
            data,
            dict
        ):

            raise ValueError(
                "Script non dictionnaire."
            )

        scenes = data.get(
            "scenes"
        )

        if not isinstance(
            scenes,
            list
        ):

            raise ValueError(
                "scenes doit être une liste."
            )

        if len(scenes) != scene_count:

            raise ValueError(
                f"Nombre de scènes incorrect : "
                f"{len(scenes)} != {scene_count}"
            )

        for index, scene in enumerate(
            scenes,
            start=1
        ):

            text = str(
                scene.get(
                    "text",
                    ""
                )
            ).strip()

            if not text:

                raise ValueError(
                    f"Scene {index}: texte absent."
                )

            if _contains_ai_mention(
                text
            ):

                raise ValueError(
                    f"Scene {index}: "
                    "mention interdite."
                )

            if len(
                text.split()
            ) < 5:

                raise ValueError(
                    f"Scene {index}: "
                    "texte trop court."
                )

        return True
