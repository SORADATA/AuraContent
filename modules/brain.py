# modules/brain.py
import os
import re
import json
import time
import requests
import logging
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv

# Import des constantes de modèles
try:
    from constants import (
        GROQ_MODEL,
        OPENROUTER_FALLBACK_MODEL_1,
        OPENROUTER_FALLBACK_MODEL_2
    )
except ImportError:
    print("⚠️ Fichier constants.py introuvable. Utilisation de modèles par défaut.")
    GROQ_MODEL = "llama3-70b-8192"  # Exemple de modèle Groq actif
    OPENROUTER_FALLBACK_MODEL_1 = "meta-llama/llama-3.3-70b-instruct"
    OPENROUTER_FALLBACK_MODEL_2 = "google/gemma-3-27b-it:free"

# --- Tentatives d'importation des bibliothèques facultatives ---
try:
    from modules.utils.client_http.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Feedback loop desactive.")
    def get_latest_videos_stats(): return None

try:
    from modules.utils.wikipedia_grounding import fetch_grounding_source
    GROUNDING_AVAILABLE = True
except ImportError:
    GROUNDING_AVAILABLE = False
    def fetch_grounding_source(query, hint_country=None): return None

# Charger les variables d'environnement
load_dotenv()

# --- Configuration du logging (plus détaillé pour AuraContent Pipeline) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AuraBrain")


# =====================================================================
# INSTRUCTIONS SYSTÈME ET INVARIANTS (NARRATIF/VERACITÉ/STYLE)
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
    "etre respectee EXACTEMENT dans le texte, le titre et le sujet. "
    "3) Le sujet doit rester peu connu du grand public mais reel et verifiable. "
    "4) EVITE les noms de lieux trop generiques/ambigus -- precise toujours le nom complet "
    "(ex: 'Eglise Saint-Pierre d'Oron' plutot que juste 'Eglise Saint-Pierre'). "
    "5) Pour chaque lieu mentionne dans le champ 'location_name', precise aussi "
    "le pays reel dans un champ 'location_country' (ex: 'France', 'Allemagne', 'Suisse'). "
    "6) ATTENTION AUX LIEUX AMBIGUS AVEC MEME NOM : il existe souvent plusieurs "
    "legendes/lieux similaires dans differentes villes/regions."
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
    "privilegie des faits concrets avec dates et lieux precis quand ils sont verifiables ; "
    "chaque scene doit avoir une fonction narrative claire ET une idee visuelle distincte."
)


# =====================================================================
# OUTILS DE NETTOYAGE ET VALIDATION TEXTE (ROBUSTE)
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
# CLASSE WIKIDATA CHECKER (ROBUSTE ET CACHÉE)
# =====================================================================

class WikidataChecker:
    API_URL = "[https://www.wikidata.org/w/api.php](https://www.wikidata.org/w/api.php)"
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
                    logger.error(f"⚠️ Wikidata erreur reseau (abandon apres {max_retries + 1} tentatives) : {e}")
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
            logger.error(f"⚠️ Wikidata (parsing recherche) erreur pour '{location_name}' : {e}")
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
            logger.error(f"⚠️ Wikidata (parsing pays) erreur pour '{entity_id}' : {e}")
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
            logger.error(f"⚠️ Wikidata (parsing label) erreur : {e}")
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


# CORRECTIF : equivalence des noms de pays EN/FR pour eviter les faux positifs Wikidata
COUNTRY_NAME_EQUIVALENTS = {
    "germany": "allemagne", "switzerland": "suisse", "italy": "italie",
    "spain": "espagne", "belgium": "belgique", "unitedkingdom": "royaumeuni",
    "greatbritain": "royaumeuni", "england": "angleterre", "scotland": "ecosse",
    "wales": "paysdegalles", "netherlands": "paysbas", "holland": "paysbas",
    "austria": "autriche", "greece": "grece", "poland": "pologne",
    "egypt": "egypte", "turkey": "turquie", "russia": "russie",
    "unitedstates": "etatsunis", "usa": "etatsunis", "portugal": "portugal",
}

def _normalize_country_text(text):
    raw = re.sub(r"[^a-z]", "", str(text or "").lower())
    return COUNTRY_NAME_EQUIVALENTS.get(raw, raw)

def _countries_match(declared, real):
    if not declared or not real:
        return True
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
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))

def _is_rate_limit_error(err_str):
    err_lower = err_str.lower()
    return (
        "rate_limit_exceeded" in err_lower
        or "tokens per minute" in err_lower
        or "tpm" in err_lower
        or "requests per minute" in err_lower
        or "rpm" in err_lower
    )

def _estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // 3)

def _estimate_prompt_tokens(messages):
    return sum(_estimate_tokens(m.get("content", "")) for m in messages)


# =====================================================================
# CLASSE PRINCIPALE : CONTENT BRAIN V4 (ROBUSTE ET MODULAIRE)
# =====================================================================

class ContentBrain:
    def __init__(self):
        # 1. Client GROQ (Priorité 1 - Rapide, streaming activé)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            # base_url explicite pour Groq afin d'être compatible avec le SDK OpenAI
            self.groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)
            logger.info("✅ Client Groq initialise.")
        else:
            self.groq_client = None
            logger.warning("⚠️ Clé GROQ_API_KEY manquante.")

        # 2. Client OPENROUTER (Priorité 2 - Fallback de haute qualité, souvent gratuit)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            # L'API OpenRouter utilise une base_url spécifique.
            self.openrouter_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)
            logger.info("✅ Client OpenRouter Image/Fallback détecté.")
        else:
            self.openrouter_client = None
            logger.warning("⚠️ Clé OPENROUTER_API_KEY manquante.")

        # Configuration de l'ordre de fallback (votreconstants.py doit être à jour)
        self.PROVIDERS_PRIORITY = [
            {"client": self.groq_client, "model": GROQ_MODEL, "name": "Groq"},
            {"client": self.openrouter_client, "model": OPENROUTER_FALLBACK_MODEL_1, "name": "OpenRouter_Llama3"},
            {"client": self.openrouter_client, "model": OPENROUTER_FALLBACK_MODEL_2, "name": "OpenRouter_Gemma3"},
        ]

    def _extract_content(self, response):
        """Extrait le contenu texte de n'importe quelle réponse compatible OpenAI."""
        choices = getattr(response, "choices", None)
        # Gestion des structures de réponse "InferenceClient" (HF)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        
        if not choices:
            raise ValueError(f"Réponse inattendue de l'API: {response}")

        choice0 = choices[0]
        # Gestion des structures d'objet standard OpenAI vs dictionnaires HF
        message = getattr(choice0, "message", None)
        if message is None and isinstance(choice0, dict):
            message = choice0.get("message")

        if isinstance(message, dict):
            content = message.get("content")
        else:
            # CORRECTIF : response.choices[0].message.content est le format standard OpenAI
            content = getattr(message, "content", None)

        if content is None and isinstance(choice0, dict):
            # Cas rare HF où le contenu est à la racine de choice
            content = choice0.get("content")

        if isinstance(content, list):
            # Cas rare où le LLM renvoie des parties de contenu (ex: lors du stream)
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text") or item.get("content") or "")
                elif isinstance(item, str):
                    parts.append(item)
            content = "".join(parts).strip()

        if not content:
            raise ValueError(f"Contenu vide généré par l'API: {response}")

        return content.strip()

    # =====================================================================
    # NOUVELLE LOGIQUE : VRAI FALLBACK MULTI-MODÈLES
    # =====================================================================

    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False,
                            max_completion_tokens=3000, hard_token_cap=7500):
        """
        Génère une réponse en essayant les modèles configurés par ordre de priorité.
        Met en œuvre un vrai fallback en cas d'échec de la Priorité 1 (Groq).
        """
        last_error = None
        
        # Estimation des tokens pour ajuster le budget de sortie
        prompt_tokens_est = _estimate_prompt_tokens(messages)
        available = hard_token_cap - prompt_tokens_est - SAFETY_MARGIN_TOKENS
        
        if max_completion_tokens > available:
            adjusted = max(500, available)
            logger.info(f"ℹ️ Budget tokens sortie reduit preventitvement : {max_completion_tokens} -> {adjusted}")
            max_completion_tokens = adjusted

        # --- Boucle sur les différents PROVIDERS ---
        for provider in self.PROVIDERS_PRIORITY:
            client = provider["client"]
            model_name = provider["model"]
            provider_name = provider["name"]

            if not client:
                continue # Ignore si la clé API manque pour ce provider

            # --- Boucle de 'retries' INTERNE par modèle ---
            for attempt in range(3):
                try:
                    kwargs = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        # Attention: Groq n'accepte pas encore 'max_completion_tokens' (nouveau standard OpenAI)
                        # mais utilise 'max_tokens'
                        "max_tokens": max_completion_tokens,
                    }
                    
                    # Attention: OpenRouter ne supporte pas toujours response_format="json_object".
                    # Heureusement, _clean_json_response parse très bien le texte brut !
                    if json_mode and provider_name == "Groq":
                        kwargs["response_format"] = {"type": "json_object"}

                    response = client.chat.completions.create(**kwargs)
                    content = self._extract_content(response)
                    
                    logger.info(f"✅ Reponse obtenue via {provider_name} ({model_name})")
                    time.sleep(0.5) # Petite pause politesse
                    return content

                except Exception as e:
                    err_str = str(e)
                    last_error = e
                    
                    # Logique de gestion de Rate Limit spécifique (429/RPM/TPM)
                    if _is_rate_limit_error(err_str):
                        logger.warning(f"⏳ Rate Limit atteint sur {provider_name}. Fallback IMMEDIAT au modele suivant.")
                        # On SORT de la boucle interne 'attempt' pour passer au prochain 'provider'
                        break 
                    
                    # Logique de gestion de tokens épuisés
                    if "budget de tokens épuisé" in err_str:
                        # Si le prompt est trop gros, on réduit le budget de sortie pour le retry
                        prompt_tokens_est = _estimate_prompt_tokens(messages)
                        available = hard_token_cap - prompt_tokens_est - SAFETY_MARGIN_TOKENS
                        max_completion_tokens = max(500, min(max_completion_tokens + 1500, available))
                        time.sleep(2)
                        continue # Réessaie sur le MÊME modèle avec plus de tokens

                    rate_limit_nums = _parse_rate_limit_numbers(err_str)
                    if rate_limit_nums:
                        # Cas particulier Groq qui précise le dépassement
                        limit, requested = rate_limit_nums
                        overage = requested - limit
                        new_budget = max(500, max_completion_tokens - overage - SAFETY_MARGIN_TOKENS)
                        logger.warning(f"⚠️ Requête trop grosse sur Groq. Reduction tokens : {max_completion_tokens} -> {new_budget}.")
                        max_completion_tokens = new_budget
                        time.sleep(1)
                        continue # Réessaie sur le MÊME modèle avec budget réduit

                    # Erreur inconnue, on réessaie le même modèle si c'est temporaire
                    logger.error(f"⚠️ Echec avec {provider_name} (Tentative {attempt + 1}/3): {e}")
                    time.sleep(2)

        # Si on arrive ici, c'est que tous les providers ont échoué
        logger.critical(f"❌ Erreur critique : TOUS les modèles et providers d'IA ont échoué. Derniere erreur: {last_error}")
        raise RuntimeError(f"Impossible d'obtenir une reponse de l'IA après fallback complet. Dernière erreur: {last_error}")


    def _call_json_with_retry(self, messages, temperature=1.0, max_json_retries=2,
                              max_completion_tokens=6000, hard_token_cap=7500):
        """
        Appelle le fallback multi-modèles et garantit que la réponse est un JSON valide.
        """
        last_error = None

        for attempt in range(max_json_retries):
            # CORRECTIF : appel de la méthode multi-modèles
            content = self._call_with_fallback(
                messages,
                temperature=temperature,
                json_mode=True, # Active le mode JSON si possible (utile pour Groq)
                max_completion_tokens=max_completion_tokens,
                hard_token_cap=hard_token_cap,
            )
            try:
                # Utilise _clean_json_response avant le parsing (crucial pour le fallback OpenRouter)
                data = json.loads(_clean_json_response(content))
                return data
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(f"⚠️ JSON malforme reçu (tentative {attempt + 1}/{max_json_retries}). "
                               f"Ajustement budget tokens...")
                # Parfois, un JSON coupé est dû à un budget trop court
                max_completion_tokens = min(max_completion_tokens + 1000, 7000)

        # CORRECTIF FINAL POUR ÉVITER LE CRASH FATAL (ValueError/char 0)
        # Si on n'arrive pas à avoir de JSON, on ne crashe pas TOUT le pipeline
        # mais on renvoie None pour que la fonction parente (ex: generate_hook_variants)
        # puisse activer sa logique de secours.
        logger.error(f"❌ Impossible d'obtenir un JSON valide après {max_json_retries} tentatives : {last_error}")
        return None 


    # =================================================================
    # SUJET / ANGLE / REQUETE VISUELLE
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
                "ensuite s'y trouve reellement."
                + stats_instruction
            )},
        ]

        last_topic = ""
        for attempt in range(3):
            # Utilise _call_with_fallback
            content = self._call_with_fallback(messages, temperature=0.9, max_completion_tokens=2000)
            topic = _clean_single_line_title(content)
            last_topic = topic

            if _contains_ai_mention(topic):
                logger.warning(f"⚠️ Sujet rejeté (mention IA détectée, tentative {attempt + 1}) : {topic}")
                continue

            if topic and 4 <= len(topic.split()) <= 18:
                return topic
            logger.warning(f"⚠️ Sujet invalide genere (tentative {attempt + 1}) : {topic}")

        # Fallback ultime pour le sujet
        return "Un Mystere Historique Francais Oublie"

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

        if not refined or _contains_ai_mention(refined):
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
        content = self._call_with_fallback(messages, temperature=0.7, max_completion_tokens=1500)
        query = _clean_single_line_title(content).replace('"', '')

        if not query:
            return "photorealistic historical documentary dark atmosphere"
        return query


    # =================================================================
    # HOOKS
    # =================================================================

    def generate_hook_variants(self, topic, n=5, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="hooks")
        prompt = f"""
SUJET:
{topic}

GENERE {n} hooks viraux en francais.

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

        # Appel du JSON avec retry
        data = self._call_json_with_retry(
            messages, temperature=1.1, max_completion_tokens=4000
        )

        # CORRECTIF D'URGENCE POUR ÉVITER LE CRASH FATAL (Si data est None)
        if not data or not isinstance(data.get("hooks"), list):
            logger.error("❌ Echec critique lors de la génération des hooks (JSON malformé). Activation du Fallback par défaut.")
            # FALLBACK DE SECOURS : on génère un hook simple basé sur le sujet
            # pour que main.py puisse continuer son travail.
            hook_texte = f"Connaissez-vous le mystère de {topic[:30]}... ?"
            return [{"text": hook_texte, "pattern": "default", "raison": "Echec generation IA"}]

        # Normalisation des hooks (inchangée)
        hooks = data.get("hooks")
        normalized_hooks = []
        for h in hooks:
            text = str(h.get("text", "")).strip() if isinstance(h, dict) else str(h).strip()
            if text and not _contains_ai_mention(text):
                normalized_hooks.append({
                    "text": text,
                    "pattern": str(h.get("pattern", "question")).strip() if isinstance(h, dict) else "question",
                    "raison": str(h.get("raison", "")).strip() if isinstance(h, dict) else ""
                })

        # S'assure qu'on a le bon nombre, sinon ajoute un défaut
        while len(normalized_hooks) < n:
            normalized_hooks.append({"text": f"Mysterium: {topic}", "pattern": "default", "raison": "complement"})
        
        return normalized_hooks[:n]


    # =================================================================
    # ANCRAGE NARRATIF (GROUNDING WIKIPEDIA)
    # =================================================================

    def propose_real_case(self, topic):
        """Propose un cas historique réel sur lequel basculer pour le grounding Wikipedia."""
        if not GROUNDING_AVAILABLE:
            return {"case_name": None, "source": None}

        hint_country = _guess_country_hint(topic)
        messages = [
            {"role": "system", "content": (
                "Tu proposes un cas historique REEL et verifiable, peu connu du grand public, "
                "correspondant exactement au sujet donne. "
                "Reponds UNIQUEMENT avec le nom propre exact du lieu/evenement principal "
                "(celui qui a un article Wikipedia), sans phrase, sans raisonnement visible, une seule ligne."
            )},
            {"role": "user", "content": f"Sujet : {topic}"},
        ]

        content = self._call_with_fallback(messages, temperature=0.3, max_completion_tokens=1500)
        case_name = _clean_single_line_title(content)

        if not case_name:
            return {"case_name": None, "source": None}

        # Vérification Wikidata (robuste)
        if hint_country:
            real_country = WikidataChecker.get_real_country(case_name, hint_country=hint_country)
            if real_country and not _countries_match(hint_country, real_country):
                logger.warning(f"⚠️ Lieu '{case_name}' incorrect (Wikidata: {real_country}, attendu: {hint_country}). Retry...")
                messages_retry = [
                    {"role": "system", "content": ( f"Tu proposes un cas historique REEL situe EXACTEMENT en {hint_country}. Reponds UNIQUEMENT avec le nom propre exact, une seule ligne." )},
                    {"role": "user", "content": f"Sujet : {topic}"},
                ]
                content_retry = self._call_with_fallback(messages_retry, temperature=0.3, max_completion_tokens=1500)
                case_name_retry = _clean_single_line_title(content_retry)
                if case_name_retry:
                    case_name = case_name_retry

        # fetch_grounding_source utilise OpenRouter en interne pour le fact-checking
        # donc il utilise déjà OPENROUTER_FALLBACK_MODEL_1
        source = fetch_grounding_source(case_name, hint_country=hint_country)
        
        # Validation lexicale du source Wikipedia
        if source and not _is_plausible_grounding_match(case_name, source):
            logger.warning(f"⚠️ Source Wikipedia trouvée ('{source.get('title')}') semble sans rapport avec '{case_name}'. Source ignorée.")
            source = None

        return {
            "case_name": case_name,
            "source": source,
        }

    # =================================================================
    # SCRIPT
    # =================================================================

    def generate_script(self, topic, chosen_hook=None):
        """Méthode par défaut pour la compatibilité."""
        return self.generate_script_with_target(topic, scene_count=11, chosen_hook=chosen_hook)

    def generate_script_with_target(self, topic, scene_count=11, chosen_hook=None, max_fact_check_retries=2):
        """Génère un script complet en essayant de réduire le nombre de scènes si budget tokens trop court."""
        candidate_counts = []
        sc = scene_count
        while sc >= 6 and len(candidate_counts) < 3:
            candidate_counts.append(sc)
            sc -= 3
        if not candidate_counts:
            candidate_counts = [scene_count]

        last_error = None
        for idx, candidate_count in enumerate(candidate_counts):
            if idx > 0:
                logger.info(f"⚠️ Tentative budget reduit : {candidate_count} scenes.")
            try:
                # Appel de la logique de génération de script
                return self._generate_script_attempt(
                    topic, candidate_count, chosen_hook, max_fact_check_retries
                )
            except (RuntimeError, ValueError) as e:
                last_error = e
                logger.error(f"❌ Echec de generation avec {candidate_count} scenes : {e}")
                continue

        # Si tout a échoué
        raise RuntimeError(f"Impossible de generer un script valide ({candidate_counts}). Derniere erreur : {last_error}")


    def _generate_script_attempt(self, topic, scene_count, chosen_hook, max_fact_check_retries):
        hook_instruction = f'La scene 1 doit reprendre ce hook : "{chosen_hook}"' if chosen_hook else "Scene 1: Accroche choc."
        
        grounding = self.propose_real_case(topic)
        source = grounding.get("source")

        if source:
            extract_text = source['extract'][:1200]
            grounding_block = f"""
\nSOURCE Wikipedia: {source['title']}
Extrait: \"\"\"{extract_text}\"\"\"
REGLE: Baser faits UNIQUEMENT sur extrait. Dramatiser autorise, invention interdite.
Pour 'image_prompt': PHOTOGRAPHIE ULTRA-PRÉCISE Documentary (pas CGI/3D).
"""
            logger.info(f"🔗 Script ancre sur source : '{source['title']}'")
        else:
            grounding_block = ""
            logger.warning("⚠️ Aucune source Wikipedia trouvee, mode libre.")

        # Prompt de script alégé pour le budget tokens
        base_prompt = f"""
SUJET: {topic}
{hook_instruction}
{grounding_block}
{NARRATIVE_STRUCTURE_INSTRUCTION}
REGLES: Pas intros, faits directs scene 2. 'image_prompt' photorealiste ultra-precis. 'stock_search' générique ANGLAIS. UNIQUE phrase 10-15 mots max. JSON UNIQUEMENT.
CONTRAINTE: EXACTEMENT {scene_count} scenes complete JSON. 
{{title, visual_identity, audio_profile, scenes:[{{id, text, voice_direction, pause_after_ms, stock_search, image_prompt, location_name, location_country, voice_type, mood, role, scene_type, event_context}}]}}
"""

        # Estimation augmentée par scène pour inclure les nouveaux prompts
        estimated_tokens_needed = min(scene_count * 380 + 1200, 6500)
        correction_feedback = ""
        
        for fact_check_attempt in range(max_fact_check_retries + 1):
            messages = [
                {"role": "system", "content": (
                    f"Tu produis uniquement du JSON. EXACTEMENT {scene_count} scenes JSON. {ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION} {VERACITY_INSTRUCTION} {NARRATIVE_STRUCTURE_INSTRUCTION}"
                )},
                {"role": "user", "content": base_prompt + correction_feedback},
            ]
            
            data = self._call_json_with_retry(
                messages,
                temperature=0.7,
                max_completion_tokens=estimated_tokens_needed
            )

            if not data:
                raise ValueError("Echec critique generation script (JSON None)")

            scenes = data.get("scenes", [])
            if len(scenes) != scene_count:
                scene_count_issue = f"Le JSON contient {len(scenes)} scenes au lieu de {scene_count}."
                if fact_check_attempt < max_fact_check_retries:
                    correction_feedback = f"\nCORRECTION OBLIGATOIRE: {scene_count_issue}\nRegenere EXACTEMENT {scene_count} scenes concises."
                    continue
                else:
                    raise ValueError(f"Impossible d'obtenir {scene_count} scenes: {scene_count_issue}")

            # Validation et Post-processing basique
            allowed_moods = {"ominous", "intriguing", "tense", "awe", "scientific", "melancholic", "revelatory"}
            for idx, scene in enumerate(scenes, start=1):
                scene.setdefault("id", idx)
                scene.setdefault("voice_direction", "French premiumnarrator, calm, intriguing, contrôlé")
                scene.setdefault("pause_after_ms", 300)
                scene.setdefault("stock_search", "cinematic background vertical")
                scene.setdefault("image_prompt", "Vertical 9:16 cinematic scene")
                scene.setdefault("voice_type", "narrator")
                if scene.get("mood") not in allowed_moods:
                    scene["mood"] = "intriguing"
                scene.setdefault("location_name", "")
                scene.setdefault("location_country", "")

            # Validation syntaxique/IA mention
            try:
                self._validate_script(data, scene_count, topic)
            except ValueError as e:
                logger.warning(f"⚠️ Erreur validation (tentative {fact_check_attempt + 1}) : {e}")
                if fact_check_attempt < max_fact_check_retries:
                    correction_feedback = f"\nCORRECTION OBLIGATOIRE: Script invalide: {e}\nCorrige et regenere {scene_count} scenes."
                    continue
                else:
                    raise

            # Fact-check & Géographie (LLM seul ici car Wikipedia Grounding utilise un autre client)
            all_consistent = True
            issues = []
            
            geo_cons = self._check_geography_consistency(topic, scenes)
            if geo_cons: issues.append(geo_cons)
            
            issues.extend(self._check_wikidata_locations(scenes, hint_country=hint_country) or [])
            
            fc_res = self._fact_check_script(topic, data, source)
            if not fc_res.get("is_consistent"):
                all_consistent = False
                issues.extend(fc_res.get("issues", []))

            if all_consistent and not issues:
                return data

            if fact_check_attempt < max_fact_check_retries:
                logger.warning(f"⚠️ Incohérences détectées (tentative {fact_check_attempt + 1}) :")
                correction_feedback = f"\nCORRECTION OBLIGATOIRE: Incohérences:\n{chr(10).join(f'- {i}' for i in issues)}\nCorrige et regenere {scene_count} scenes."
            else:
                logger.error(f"❌ Incohérences persistantes : {issues}")
                return data # On retourne quand même pour éviter le crash fatal
        return data

    # =================================================================
    # VERIFICATIONS INTERNES (Fact-checking LLM)
    # =================================================================

    def _check_geography_consistency(self, topic, scenes):
        """Vérifie sommairement que si le sujet est français, aucun lieu étranger n'est cité."""
        if not _topic_claims_french_location(topic): return None
        for scene in scenes:
            country = str(scene.get("location_country", "")).strip().lower()
            if country and "france" not in country and "français" not in country:
                return f"Sujet français, mais scene '{scene.get('location_name')}' declare pays '{country}'."
        return None

    def _check_wikidata_locations(self, scenes, hint_country=None):
        """Vérifie la véracité des pays déclarés pour chaque lieu."""
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
        """Vérifie la cohérence factuelle du script contre sa source ou en mode libre."""
        scenes_sum = "\n".join(f"-Scene {s.get('id')} [{s.get('location_name', 'aucun lieu')}] : {s.get('text', '')[:100]}" for s in script_data.get("scenes", []))
        if grounding_source:
            extract = grounding_source['extract'][:1200]
            prompt = f"Fact-checker: Compare SCRIPT a SOURCE Wikipedia. Signale uniquement faits CONTRADICTOIRES ou AJOUTES absent de source (nom, lieu, date).\nSOURCE ({grounding_source['title']}): \"\"\"{extract}\"\"\"\nSCRIPT: {scenes_sum}\nJSON ONLY: {{\"is_consistent\": true/false, \"issues\": []}}"
        else:
            prompt = f"Fact-checker STRICT. Signale uniquement erreur factuelle objective (nom/lieu invente, date fausse) liée au SUJET: {topic}.\nSCRIPT: {scenes_sum}\nJSON ONLY: {{\"is_consistent\": true/false, \"issues\": []}}"
        
        messages = [{"role": "system", "content": "Tu es un fact-checker rigoureux et minimaliste (peu de faux positifs), JSON ONLY."}, {"role": "user", "content": prompt}]
        try:
            # Fact-check est critique, on utilise une température basse
            data = self._call_json_with_retry(messages, temperature=0.1, max_json_retries=1, max_completion_tokens=2500)
            if not data: return {"is_consistent": True, "issues": []}
            return {"is_consistent": bool(data.get("is_consistent", True)), "issues": data.get("issues", [])}
        except Exception as e:
            logger.error(f"⚠️ Echec fact-check LLM : {e}")
            return {"is_consistent": True, "issues": []}

    def _validate_script(self, data, scene_count, topic):
        """Vérifie la structure JSON finale du script et les règles de base."""
        scenes = data.get("scenes")
        if not isinstance(scenes, list) or len(scenes) != scene_count:
            raise ValueError(f"scenes invalide: attendu {scene_count}.")
        for scene in scenes:
            if not scene.get("text"): raise ValueError(f"Scene {scene.get('id')}: text manquant.")
            if _contains_ai_mention(scene.get("text", "")):
                raise ValueError(f"Scene {scene.get('id')}: mention IA détectée dans le texte.")
