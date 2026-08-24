import os
import re
import json
import time
import requests
import logging
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
from constants import (
        GROQ_MODEL,
        OPENROUTER_FALLBACK_MODEL_1,
        OPENROUTER_FALLBACK_MODEL_2
    )

# --- Mocks pour les modules externes ---
try:
    from modules.utils.client_http.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Création de données factices pour le test.")
    def get_latest_videos_stats():
        return None

try:
    from modules.utils.wikipedia_grounding import fetch_grounding_source
    GROUNDING_AVAILABLE = True
except ImportError:
    GROUNDING_AVAILABLE = False
    def fetch_grounding_source(query, hint_country=None):
        return None

# Charger les variables d'environnement
load_dotenv()

# --- Configuration du logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AuraBrain")

# =====================================================================
# INSTRUCTIONS SYSTÈME CLÉS
# =====================================================================
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
    "Suisse'). Si le sujet annonce une zone geographique specifique, TOUS les "
    "lieux du script doivent appartenir a cette zone reelle. "
    "6) ATTENTION AUX LIEUX AMBIGUS AVEC MEME NOM : il existe souvent plusieurs "
    "lieux similaires (ex: plusieurs 'ponts du diable' en France, plusieurs "
    "lieux portant un nom proche)."
)

NARRATIVE_STRUCTURE_INSTRUCTION = (
    "STRUCTURE NARRATIVE OBLIGATOIRE (RETENTION MAXIMALE) : "
    "Repartis ces phases proportionnellement sur les scenes disponibles : "
    "1) HOOK (debut) : commence IMMEDIATEMENT par le fait le plus intrigant, sans introduction. "
    "2) PREUVE : donne un element concret qui justifie le hook. "
    "3) CONTEXTE : explique uniquement ce qui est necessaire, sans remplissage. "
    "4) ESCALADE : chaque scene doit apporter une information nouvelle, jamais une redite. "
    "5) REVELATION : presente le detail le plus surprenant du sujet. "
    "6) PAYOFF (fin) : reponse, retournement ou question extremement forte donnant envie "
    "de revoir ou commenter la video. "
    "REGLES : aucune introduction generique, aucune phrase vide, aucune repetition ; "
    "interdiction des formulations comme 'aujourd'hui nous allons decouvrir...' ; "
    "privilegie des faits concrets avec dates et lieux precis quand ils sont verifiables ; "
    "chaque scene doit avoir une fonction narrative claire ET une idee visuelle distincte ; "
    "ne jamais inventer une source ou un evenement historique ; "
    "distingue clairement fait historique etabli et hypothese/legende."
)

# =====================================================================
# OUTILS DE NETTOYAGE ET VALIDATION TEXTE
# =====================================================================

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
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in AI_MENTION_PATTERNS)

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
    cleaned = text.replace('"', '').replace('"', '').replace('"', '').strip()
    lines = [line.strip(' -•\t') for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""
    return re.sub(r"\s+", " ", lines[0]).strip()

def _clean_json_response(content):
    if not content:
        return content
    cleaned = content.strip()
    # Enleve les balises de code markdown ```json ... ```
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()

# =====================================================================
# GÉOGRAPHIE ET CORRESPONDANCE DE PAYS
# =====================================================================

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

def _topic_claims_french_location(topic):
    topic_lower = topic.lower()
    return any(kw in topic_lower for kw in FRENCH_GEO_KEYWORDS)

def _guess_country_hint(topic):
    topic_lower = topic.lower()
    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(kw in topic_lower for kw in keywords):
            return country.capitalize()
    return None

def _tokenize_for_match(text):
    return set(
        w for w in re.sub(r"[^a-zA-ZÀ-ÿ0-9 ]", " ", str(text or "").lower()).split()
        if len(w) > 2
    )

def _is_plausible_grounding_match(case_name, source):
    if not source or not source.get("title"):
        return False
    case_tokens = _tokenize_for_match(case_name)
    title_tokens = _tokenize_for_match(source["title"])
    if not case_tokens or not title_tokens:
        return False
    return len(case_tokens & title_tokens) > 0

# =====================================================================
# CLASSE WIKIDATA CHECKER (ROBUSTE)
# =====================================================================

class WikidataChecker:
    API_URL = "https://www.wikidata.org/w/api.php"
    HEADERS = {
        "User-Agent": os.getenv(
            "WIKIMEDIA_CONTACT",
            "AuraContentPipeline/3.0 (contact non configure)"
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
                    logger.warning(f"⏳ Wikidata 429, attente {wait}s avant retry...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r
            except requests.exceptions.RequestException as e:
                if attempt == max_retries:
                    logger.error(f"⚠️ Wikidata erreur reseau : {e}")
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
        if r is None: return []
        try:
            results = r.json().get("search", [])
            return [item.get("id") for item in results if item.get("id")]
        except Exception as e:
            logger.error(f"⚠️ Wikidata search parse error for '{location_name}' : {e}")
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
        if r is None: return None
        try:
            entities = r.json().get("entities", {})
            entity = entities.get(entity_id, {})
            claims = entity.get("claims", {})
            country_claims = claims.get("P17")
            if not country_claims: return None
            country_entity_id = country_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if not country_entity_id: return None
            return cls._resolve_entity_label(country_entity_id)
        except Exception as e:
            logger.error(f"⚠️ Wikidata country parse error for '{entity_id}' : {e}")
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
        if r is None: return None
        try:
            entities = r.json().get("entities", {})
            entity = entities.get(entity_id, {})
            labels = entity.get("labels", {})
            label = labels.get("fr") or labels.get("en")
            if label: return label.get("value")
        except Exception as e:
            logger.error(f"⚠️ Wikidata label parse error : {e}")
        return None

    @classmethod
    def get_real_country(cls, location_name, hint_country=None):
        if not location_name: return None
        cache_key = f"{location_name.strip().lower()}|{(hint_country or '').lower()}"
        if cache_key in cls.CACHE: return cls.CACHE[cache_key]

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

# Équivalence des noms de pays pour éviter les faux positifs
COUNTRY_NAME_EQUIVALENTS = {
    "germany": "allemagne", "switzerland": "suisse", "italy": "italie",
    "spain": "espagne", "belgium": "belgique", "unitedkingdom": "royaumeuni",
    "greatbritain": "royaumeuni", "england": "angleterre", "scotland": "ecosse",
    "wales": "paysdegalles", "netherlands": "paysbas", "holland": "paysbas",
    "austria": "autriche", "greece": "grece", "poland": "pologne",
    "egypt": "egypte", "turkey": "turquie", "russia": "russie",
    "sweden": "suede", "norway": "norvege", "denmark": "danemark",
    "ireland": "irlande", "czechia": "tchequie", "czechrepublic": "tchequie",
    "unitedstates": "etatsunis", "unitedstatesofamerica": "etatsunis",
    "usa": "etatsunis", "portugal": "portugal", "morocco": "maroc",
}

def _normalize_country_text(text):
    raw = re.sub(r"[^a-z]", "", str(text or "").lower())
    return COUNTRY_NAME_EQUIVALENTS.get(raw, raw)

def _countries_match(declared, real):
    if not declared or not real: return True
    d = _normalize_country_text(declared)
    r = _normalize_country_text(real)
    return d == r or d in r or r in d

# =====================================================================
# DÉTECTION ET ESTIMATION TOKENS
# =====================================================================
_RATE_LIMIT_NUMS_RE = re.compile(r"Limit[:\s]+(\d+),?\s*Requested[:\s]+(\d+)", re.IGNORECASE)
SAFETY_MARGIN_TOKENS = 400

def _parse_rate_limit_numbers(err_str):
    match = _RATE_LIMIT_NUMS_RE.search(err_str)
    if not match: return None
    return int(match.group(1)), int(match.group(2))

def _is_rate_limit_error(err_str):
    err_lower = err_str.lower()
    return any(kw in err_lower for kw in ["rate_limit_exceeded", "tokens per minute", "tpm", "rpm", "requests per minute"])

def _estimate_tokens(text):
    if not text: return 0
    return max(1, len(text) // 3)

def _estimate_prompt_tokens(messages):
    return sum(_estimate_tokens(m.get("content", "")) for m in messages)

# =====================================================================
# CLASSE PRINCIPALE : CONTENT BRAIN (MULTI-MODEL FALLBACK)
# =====================================================================

class ContentBrain:
    def __init__(self):
        # 1. Initialisation unique des clients API
        
        # Client GROQ (Priorité 1)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)
            logger.info("✅ Client Groq initialise.")
        else:
            self.groq_client = None
            logger.warning("⚠️ Clé GROQ_API_KEY manquante.")

        # Client OPENROUTER (Priorité 2 & 3 - Fallback)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            self.openrouter_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)
            logger.info("✅ Client OpenRouter initialise.")
        else:
            self.openrouter_client = None
            logger.warning("⚠️ Clé OPENROUTER_API_KEY manquante.")

        # Configuration de la priorité des providers
        self.PROVIDERS_PRIORITY = [
            {"client": self.groq_client, "model": GROQ_MODEL, "name": "Groq"},
            {"client": self.openrouter_client, "model": OPENROUTER_FALLBACK_MODEL_1, "name": "OpenRouter_Llama3"},
            {"client": self.openrouter_client, "model": OPENROUTER_FALLBACK_MODEL_2, "name": "OpenRouter_Gemma3"},
        ]

    def _extract_content(self, response):
        """Extrait le contenu texte d'une réponse OpenAI compatible."""
        # Correction de la syntaxe ici (remplacement de la ligne erronée)
        try:
            return response.choices[0].message.content.strip()
        except (AttributeError, IndexError, TypeError) as e:
            # Fallback pour des structures de réponse exotiques ou dictionnaires
            choices = getattr(response, "choices", None)
            if choices and len(choices) > 0:
                choice0 = choices[0]
                message = getattr(choice0, "message", None)
                if message:
                    content = getattr(message, "content", None)
                    if content: return str(content).strip()
            
            logger.error(f"⚠️ Erreur critique lors de l'extraction du contenu: {e}. Reponse: {response}")
            raise ValueError(f"Impossible d'extraire le contenu de la reponse : {response}")

    # =====================================================================
    # NOUVELLE LOGIQUE : VRAI FALLBACK MULTI-MODÈLES
    # =====================================================================
    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False,
                            max_completion_tokens=3000, hard_token_cap=7500):
        """
        Génère une réponse en essayant les modèles configurés par ordre de priorité.
        Met en œuvre un vrai fallback en cas d'échec (Rate Limit, Panne).
        """
        last_error = None
        
        # Estimation des tokens pour ajuster le budget de sortie
        prompt_tokens_est = _estimate_prompt_tokens(messages)
        available = hard_token_cap - prompt_tokens_est - SAFETY_MARGIN_TOKENS
        
        if max_completion_tokens > available:
            adjusted = max(500, available)
            logger.info(f"ℹ️ Budget tokens sortie reduit : {max_completion_tokens} -> {adjusted}")
            max_completion_tokens = adjusted

        # --- Boucle sur les différents PROVIDERS ---
        for provider in self.PROVIDERS_PRIORITY:
            client = provider["client"]
            model_name = provider["model"]
            provider_name = provider["name"]

            if not client: continue # Ignore si la clé API manque

            # --- Boucle de 'retries' INTERNE par modèle ---
            for attempt in range(3):
                try:
                    kwargs = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_completion_tokens, # max_tokens standard pour OpenAI/OpenRouter
                    }
                    
                    # OpenRouter ne supporte pas toujours response_format="json_object".
                    # Heureusement, _clean_json_response parse très bien le texte brut !
                    if json_mode and provider_name == "Groq":
                        kwargs["response_format"] = {"type": "json_object"}

                    response = client.chat.completions.create(**kwargs)
                    content = self._extract_content(response)
                    
                    logger.info(f"✅ Reponse obtenue via {provider_name} ({model_name})")
                    time.sleep(0.5) # Petite pause politesse
                    return content

                except OpenAIError as e:
                    err_str = str(e)
                    last_error = e
                    
                    # Gestion spécifique des Rate Limits (TPM/RPM)
                    if _is_rate_limit_error(err_str):
                        logger.warning(f"⏳ Rate Limit atteint sur {provider_name}. Fallback IMMEDIAT au modele suivant.")
                        # On SORT de la boucle interne 'attempt' pour passer au prochain 'provider'
                        break 
                    
                    # Gestion spécifique du budget tokens épuisé (ex: finish_reason=length)
                    if "budget de tokens épuisé" in err_str or "finish_reason='length'" in err_str:
                        logger.warning(f"⚠️ Budget tokens epuise sur {provider_name}. Ajustement...")
                        max_completion_tokens = max(500, min(max_completion_tokens + 1500, available))
                        time.sleep(2)
                        continue # Réessaie sur le MÊME modèle avec un plus grand budget

                    logger.error(f"⚠️ Echec avec {provider_name} (Tentative {attempt + 1}/3): {e}")
                    time.sleep(3 * (attempt + 1)) # Attente exponentielle avant réessai sur le même modèle

        # Si on arrive ici, c'est que tous les providers ont échoué
        logger.critical(f"❌ Erreur critique : TOUS les modèles ont échoué. Dernier échec : {last_error}")
        raise RuntimeError(f"Impossible de generer du contenu après fallback complet. Dernière erreur: {last_error}")

    # --- Reste des méthodes du Brain (inchangées, sauf appels) ---

    def _call_json_with_retry(self, messages, temperature=1.0, max_json_retries=2,
                              max_completion_tokens=6000, hard_token_cap=7500):
        last_error = None
        for attempt in range(max_json_retries):
            content = self._call_with_fallback(
                messages, temperature=temperature, json_mode=True,
                max_completion_tokens=max_completion_tokens, hard_token_cap=hard_token_cap,
            )
            try:
                # Utilise _clean_json_response avant le parsing
                data = json.loads(_clean_json_response(content))
                return data
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(f"⚠️ JSON malforme (tentative {attempt + 1}/{max_json_retries}). Ajustement budget...")
                max_completion_tokens = min(max_completion_tokens + 1000, 7000)

        raise ValueError(f"Impossible d'obtenir un JSON valide après {max_json_retries} tentatives : {last_error}")

    # =================================================================
    # MÉTHODES GÉNÉRATEURS (Sujet, Hook, Script, etc.)
    # =================================================================

    def get_trending_topic(self, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")
        messages = [
            {"role": "system", "content": (
                "Tu es un strategiste de contenu viral. Reponds uniquement avec un seul titre "
                "en francais, une seule ligne, sans guillemets, maximum 18 mots. "
                "Ne montre jamais ton raisonnement, reponds directement avec le titre final. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION} {VERACITY_INSTRUCTION}"
            )},
            {"role": "user", "content": (
                "Donne un sujet viral totalement inédit et surprenant pour TikTok en français, "
                "portant sur un mystere, un lieu ou un fait historique REEL et verifiable, "
                "peu connu du grand public. Ne pas annoncer une zone geographique precise "
                "(ex: un pays, une region) si tu n'es pas certain que l'exemple developpe "
                "ensuite s'y trouve reellement." + stats_instruction
            )},
        ]
        last_topic = ""
        for attempt in range(3):
            content = self._call_with_fallback(messages, temperature=0.9, max_completion_tokens=2000)
            topic = _clean_single_line_title(content)
            last_topic = topic
            if _contains_ai_mention(topic):
                logger.warning(f"⚠️ Sujet rejeté (mention IA, tentative {attempt + 1}) : {topic}")
                continue
            if topic and 4 <= len(topic.split()) <= 18: return topic
            logger.warning(f"⚠️ Sujet invalide (tentative {attempt + 1}) : {topic}")

        raise ValueError(f"Impossible d'obtenir un sujet valide : {last_topic}")

    def refine_topic_angle(self, raw_topic):
        messages = [
            {"role": "system", "content": (
                "Tu reformules le sujet en un titre accrocheur, sans changer le theme "
                "ni la localisation geographique reelle du fait evoque. "
                "Reponds uniquement avec le titre reformule, sans montrer ton raisonnement. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION} {VERACITY_INSTRUCTION}"
            )},
            {"role": "user", "content": f"Sujet brut / trend repere: {raw_topic}"},
        ]
        content = self._call_with_fallback(messages, temperature=0.8, max_completion_tokens=2000)
        refined = _clean_single_line_title(content)
        if not refined or _contains_ai_mention(refined): return _clean_single_line_title(raw_topic)
        return refined

    def generate_video_search_query(self, topic):
        messages = [
            {"role": "system", "content": (
                "Tu génères une requête de recherche visuelle en anglais, 6 mots max, "
                "sans phrase, sans raisonnement visible. Inclure : photorealistic, historical "
                "documentary, real photography, dark mysterious atmosphere. INTERDICTION "
                "d'utiliser CGI, 3D, render ou Unreal Engine."
            )},
            {"role": "user", "content": f"Sujet : {topic}"},
        ]
        content = self._call_with_fallback(messages, temperature=0.7, max_completion_tokens=1500)
        query = _clean_single_line_title(content).replace('"', '')
        if not query: return "photorealistic historical documentary dark atmosphere"
        return query

    def generate_hook_variants(self, topic, n=5, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="hooks")
        prompt = f"SUJET:\n{topic}\n\nGENERE {n} hooks viraux en francais. RETURNS JSON:\n{{\"hooks\": [ {{\"text\": \"hook\", \"pattern\": \"question\", \"raison\": \"...\"}} ] }}\n{stats_instruction}"
        messages = [
            {"role": "system", "content": (f"Tu produis uniquement du JSON valide avec exactement {n} hooks. {ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION}")},
            {"role": "user", "content": prompt},
        ]
        data = self._call_json_with_retry(messages, temperature=1.1, max_completion_tokens=4000)
        hooks = data.get("hooks")
        if not isinstance(hooks, list): raise ValueError("Champ hooks invalide.")
        normalized_hooks = []
        for h in hooks:
            text = str(h.get("text", "")).strip() if isinstance(h, dict) else str(h).strip()
            if text and not _contains_ai_mention(text):
                normalized_hooks.append({
                    "text": text,
                    "pattern": str(h.get("pattern", "question")).strip() if isinstance(h, dict) else "default",
                    "raison": str(h.get("raison", "")).strip() if isinstance(h, dict) else ""
                })
        if len(normalized_hooks) < n: raise ValueError(f"Nombre de hooks invalide: {len(normalized_hooks)}/{n}.")
        return normalized_hooks[:n]

    def propose_real_case(self, topic):
        if not GROUNDING_AVAILABLE: return {"case_name": None, "source": None}
        hint_country = _guess_country_hint(topic)
        messages = [{"role": "system", "content": ( "Tu proposes un cas historique REEL et verifiable, peu connu, correspondant exactement au sujet donne. Reponds UNIQUEMENT avec le nom propre exact du lieu/evenement principal, une seule ligne." )}, {"role": "user", "content": f"Sujet : {topic}"}]
        content = self._call_with_fallback(messages, temperature=0.3, max_completion_tokens=1500)
        case_name = _clean_single_line_title(content)
        if not case_name: return {"case_name": None, "source": None}
        
        # Wikidata check
        if hint_country:
            real_country = WikidataChecker.get_real_country(case_name, hint_country=hint_country)
            if real_country and not _countries_match(hint_country, real_country):
                logger.warning(f"⚠️ Lieu '{case_name}' incorrect (Wikidata: {real_country}, attendu: {hint_country}). Retry...")
                messages_retry = [{"role": "system", "content": ( f"Tu proposes un cas historique REEL situe EXACTEMENT en {hint_country}. Reponds UNIQUEMENT avec le nom propre exact, une seule ligne." )}, {"role": "user", "content": f"Sujet : {topic}"}]
                content_retry = self._call_with_fallback(messages_retry, temperature=0.3, max_completion_tokens=1500)
                case_name_retry = _clean_single_line_title(content_retry)
                if case_name_retry: case_name = case_name_retry

        source = fetch_grounding_source(case_name, hint_country=hint_country)
        # Validation lexicale de la source
        if source and not _is_plausible_grounding_match(case_name, source):
            logger.warning(f"⚠️ Source Wikipedia trouvée ('{source.get('title')}') semble sans rapport avec '{case_name}'. Source ignorée.")
            source = None
        return {"case_name": case_name, "source": source}

    def generate_script(self, topic, chosen_hook=None):
        return self.generate_script_with_target(topic, scene_count=11, chosen_hook=chosen_hook)

    def generate_script_with_target(self, topic, scene_count=11, chosen_hook=None, max_fact_check_retries=2):
        candidate_counts = []
        sc = scene_count
        while sc >= 6 and len(candidate_counts) < 3:
            candidate_counts.append(sc)
            sc -= 3
        if not candidate_counts: candidate_counts = [scene_count]
        last_error = None
        for idx, candidate_count in enumerate(candidate_counts):
            if idx > 0: logger.info(f"⚠️ Tentative budget reduit : {candidate_count} scenes.")
            try:
                return self._generate_script_attempt(topic, candidate_count, chosen_hook, max_fact_check_retries)
            except (RuntimeError, ValueError) as e:
                last_error = e
                logger.error(f"❌ Echec avec {candidate_count} scenes : {e}")
                continue
        raise RuntimeError(f"Impossible de generer un script valide ({candidate_counts}). Derniere erreur : {last_error}")

    def _generate_script_attempt(self, topic, scene_count, chosen_hook, max_fact_check_retries):
        hook_instruction = f'La scene 1 doit reprendre ce hook : "{chosen_hook}"' if chosen_hook else "Scene 1: Accroche choc."
        grounding = self.propose_real_case(topic)
        source = grounding.get("source")
        if source:
            extract_text = source['extract'][:1200]
            grounding_block = f"\nSOURCE VERIFIEE Wikipedia: {source['title']}\nExtrait: \"\"\"{extract_text}\"\"\"\nREGLE: Baser faits UNIQUEMENT sur extrait. Dramatiser autorise, invention interdite."
            logger.info(f"🔗 Script ancre sur source : '{source['title']}'")
        else:
            grounding_block = ""
            logger.warning("⚠️ Aucune source Wikipedia trouvee, mode libre.")

        # Prompt de script alégé pour le budget tokens
        base_prompt = f"SUJET: {topic}\n{hook_instruction}\n{grounding_block}\n{NARRATIVE_STRUCTURE_INSTRUCTION}\nREGLES: Pas intros, faits directs dès scene 2. 'image_prompt' photorealiste ultra-precis (pas CGI/3D). 'stock_search' générique ANGLAIS (pas lieux precis). UNIQUE phrase 10-15 mots max par scene. JSON UNIQUEMENT.\nCONTRAINTE: Retourne EXACTEMENT {scene_count} scenes complettes JSON. title, visual_identity, audio_profile, scenes[id, text, voice_direction, pause_after_ms, stock_search, image_prompt, location_name, location_country, voice_type, mood, role, scene_type, event_context]"

        estimated_tokens_needed = min(scene_count * 380 + 1200, 6500)
        correction_feedback = ""
        for fact_check_attempt in range(max_fact_check_retries + 1):
            messages = [{"role": "system", "content": ( f"Tu produis uniquement du JSON. EXACTEMENT {scene_count} scenes JSON. {ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION} {VERACITY_INSTRUCTION} {NARRATIVE_STRUCTURE_INSTRUCTION}" )}, {"role": "user", "content": base_prompt + correction_feedback}]
            data = self._call_json_with_retry(messages, temperature=0.7, max_completion_tokens=estimated_tokens_needed)
            scenes = data.get("scenes", [])
            if len(scenes) != scene_count:
                scene_count_issue = f"Le JSON contient {len(scenes)} scenes au lieu de {scene_count}."
                if fact_check_attempt < max_fact_check_retries:
                    correction_feedback = f"\nCORRECTION OBLIGATOIRE: {scene_count_issue}\nRegenere EXACTEMENT {scene_count} scenes concises."
                    continue
                else: raise ValueError(f"Impossible d'obtenir {scene_count} scenes: {scene_count_issue}")

            # Validation et Post-processing basique
            for idx, scene in enumerate(scenes, start=1):
                scene.setdefault("id", idx)
                scene.setdefault("voice_direction", "French premium narrator, calm, intrigant, contrôlé")
                scene.setdefault("pause_after_ms", 300)
                scene.setdefault("stock_search", "cinematic background vertical")
                scene.setdefault("image_prompt", "Vertical 9:16 cinematic scene")
                scene.setdefault("voice_type", "narrator")

            try:
                self._validate_script(data, scene_count, topic)
            except ValueError as e:
                logger.warning(f"⚠️ Erreur validation (tentative {fact_check_attempt + 1}) : {e}")
                if fact_check_attempt < max_fact_check_retries:
                    correction_feedback = f"\nCORRECTION OBLIGATOIRE: Script invalide: {e}\nCorrige et regenere {scene_count} scenes."
                    continue
                else: raise

            # Fact-check & Géographie
            all_consistent = True
            issues = []
            issues.extend(self._check_geography_consistency(topic, scenes) or [])
            issues.extend(self._check_wikidata_locations(scenes, grounding.get("country_hint")) or [])
            fc_res = self._fact_check_script(topic, data, source)
            if not fc_res.get("is_consistent"): all_consistent = False; issues.extend(fc_res.get("issues", []))

            if all_consistent and not issues: return data
            if fact_check_attempt < max_fact_check_retries:
                logger.warning(f"⚠️ Incohérences détectées (tentative {fact_check_attempt + 1}) :")
                correction_feedback = f"\nCORRECTION OBLIGATOIRE: Incohérences:\n{chr(10).join(f'- {i}' for i in issues)}\nCorrige et regenere {scene_count} scenes."
            else: logger.error(f"❌ Incohérences persistantes : {issues}"); return data
        return data

    # =================================================================
    # VERIFICATIONS (Validation interne)
    # =================================================================

    def _check_geography_consistency(self, topic, scenes):
        if not _topic_claims_french_location(topic): return None
        for scene in scenes:
            country = str(scene.get("location_country", "")).strip().lower()
            if country and "france" not in country and "français" not in country:
                return f"Sujet français, mais scene '{scene.get('location_name')}' declare pays '{country}'."
        return None

    def _check_wikidata_locations(self, scenes, hint_country=None):
        issues = []
        for scene in scenes:
            name = str(scene.get("location_name", "")).strip()
            declared = str(scene.get("location_country", "")).strip()
            if not name or not declared: continue
            real = WikidataChecker.get_real_country(name, hint_country)
            if real and not _countries_match(declared, real):
                issues.append(f"Wikidata: '{name}' est en '{real}', mais script declare '{declared}'.")
        return issues

    def _fact_check_script(self, topic, script_data, grounding_source=None):
        scenes_sum = "\n".join(f"-Scene {s.get('id')} [{s.get('location_name', 'aucun lieu')}] : {s.get('text', '')[:100]}" for s in script_data.get("scenes", []))
        if grounding_source:
            extract = grounding_source['extract'][:1200]
            prompt = f"Fact-checker: Compare SCRIPT a SOURCE Wikipedia. Signale uniquement faits CONTRADICTOIRES ou AJOUTES absent de source (nom, lieu, date).\nSOURCE ({grounding_source['title']}): \"\"\"{extract}\"\"\"\nSCRIPT: {scenes_sum}\nJSON ONLY: {{\"is_consistent\": true/false, \"issues\": []}}"
        else:
            prompt = f"Fact-checker STRICT. Signale uniquement erreur factuelle objective (nom/lieu invente, date fausse) liée au SUJET: {topic}.\nSCRIPT: {scenes_sum}\nJSON ONLY: {{\"is_consistent\": true/false, \"issues\": []}}"
        
        messages = [{"role": "system", "content": "Tu es un fact-checker rigoureux et minimaliste (peu de faux positifs), JSON ONLY."}, {"role": "user", "content": prompt}]
        try:
            data = self._call_json_with_retry(messages, temperature=0.1, max_json_retries=1, max_completion_tokens=2500)
            return {"is_consistent": bool(data.get("is_consistent", True)), "issues": data.get("issues", [])}
        except Exception as e: return {"is_consistent": True, "issues": []}

    def _validate_script(self, data, scene_count, topic):
        scenes = data.get("scenes")
        if not isinstance(scenes, list) or len(scenes) != scene_count:
            raise ValueError(f"scenes invalide: attendu {scene_count}.")
        for scene in scenes:
            if not scene.get("text"): raise ValueError(f"Scene {scene.get('id')}: text manquant.")
            if _contains_ai_mention(scene.get("text", "")):
                raise ValueError(f"Scene {scene.get('id')}: mention IA détectée.")
            scene.setdefault("voice_direction", "French narrator")
            if not isinstance(scene.get("pause_after_ms"), int): scene["pause_after_ms"] = 300
