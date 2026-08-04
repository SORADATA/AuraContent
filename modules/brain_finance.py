import os
import re
import json
import random
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

try:
    from modules.utils.zernio_client_finance import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Création de données factices pour le test.")
    def get_latest_videos_stats(): return None

try:
    from modules.utils.market_data_client import get_market_signals
except ImportError:
    print("⚠️ Module market_data_client introuvable. Aucune donnée de marché live injectée.")
    def get_market_signals(**kwargs): return None

# Verrouillage best-effort de l'état du curriculum. Si le package n'est
# pas installé, on continue sans verrou (risque résiduel en cas de deux
# générations strictement concurrentes, mais ça ne casse rien).
try:
    from filelock import FileLock
    FILELOCK_AVAILABLE = True
except ImportError:
    FILELOCK_AVAILABLE = False

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash"

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc). Exemples obligatoires : 'épargne' "
    "(jamais 'epargne'), 'intérêt' (jamais 'interet'), 'stratégie' "
    "(jamais 'strategie'), 'bénéfice' (jamais 'benefice'). "
    "Verifie chaque mot avant de repondre."
)

COMPLIANCE_INSTRUCTION = (
    "REGLE DE CONFORMITE (LOI DU 9 JUIN 2023 / AMF) : ce contenu est de "
    "l'education financiere generale, jamais un conseil en investissement "
    "personnalise. N'utilise jamais des formulations imperatives du type "
    "'achete cette action', 'tu dois investir dans', 'c'est une valeur sure'. "
    "Prefere des formulations educatives : 'voici comment ca fonctionne', "
    "'voici ce que font certains investisseurs', 'a etudier selon ton profil'. "
    "Mentionne implicitement ou explicitement qu'investir comporte des "
    "risques de perte en capital. N'invente aucune promesse de gain garanti "
    "ni de rendement chiffre non verifiable."
)

COMPLIANCE_RETRY_INSTRUCTION = (
    "ATTENTION - LA GENERATION PRECEDENTE A ECHOUE LE CONTROLE DE CONFORMITE "
    "car elle contenait une formulation interdite (conseil en investissement "
    "personnalise, promesse de gain garanti, ou incitation directe a l'achat). "
    "Relis chaque phrase avant de repondre et reformule TOUT passage "
    "imperatif en formulation strictement educative. " + COMPLIANCE_INSTRUCTION
)

PEDAGOGY_INSTRUCTION = (
    "PRIORITE PEDAGOGIQUE : cette video doit apprendre une notion financiere "
    "reelle et transferable, pas seulement divertir. A la fin, le spectateur "
    "doit pouvoir expliquer le concept a quelqu'un d'autre avec ses propres mots. "
    "Utilise une analogie simple et concrete pour la notion abordee. "
    "Privilegie la clarte a la sophistication : une seule idee centrale par video."
)

CONTENT_PILLARS = {
    "epargne": {
        "label": "Épargne et produits bancaires",
        "seed_notions": [
            {"notion": "Le fonctionnement des intérêts composés", "niveau": "debutant"},
            {"notion": "Différence entre livret A, PEL et assurance-vie", "niveau": "debutant"},
            {"notion": "La règle du fonds d'urgence avant d'investir", "niveau": "debutant"},
            {"notion": "Pourquoi l'inflation érode ton épargne si elle dort", "niveau": "debutant"},
            {"notion": "Comment les banques gagnent de l'argent sur ton compte courant", "niveau": "debutant"},
        ],
    },
    "investissement": {
        "label": "Investissement et marchés",
        "seed_notions": [
            {"notion": "Comment fonctionne un ETF et pourquoi il est populaire", "niveau": "debutant"},
            {"notion": "Le principe de la diversification d'un portefeuille", "niveau": "intermediaire"},
            {"notion": "Comment fonctionne un PEA et ses avantages fiscaux", "niveau": "intermediaire"},
            {"notion": "Le principe de l'allocation d'actifs selon l'âge", "niveau": "avance"},
        ],
    },
    "credit_dette": {
        "label": "Crédit et dette",
        "seed_notions": [
            {"notion": "Comment fonctionne le crédit immobilier et le taux d'endettement", "niveau": "intermediaire"},
            {"notion": "Pourquoi la dette n'est pas toujours mauvaise (effet de levier)", "niveau": "intermediaire"},
        ],
    },
    "fiscalite": {
        "label": "Fiscalité et revenus",
        "seed_notions": [
            {"notion": "Comment fonctionne l'imposition des plus-values en France", "niveau": "intermediaire"},
            {"notion": "Comment lit-on une fiche de paie pour repérer les erreurs", "niveau": "debutant"},
            {"notion": "La différence entre revenu actif et revenu passif", "niveau": "debutant"},
        ],
    },
    "psychologie_argent": {
        "label": "Psychologie de l'argent",
        "seed_notions": [
            {"notion": "Le biais du coût irrécupérable et son impact sur tes finances", "niveau": "intermediaire"},
        ],
    },
}

ANGLES = [
    "mythe_a_corriger",
    "etude_de_cas_chiffree",
    "comparaison_avant_apres",
    "question_audience",
    "analogie_inedite",
    "erreur_vecue",
    "chiffre_choc",
]

CURRICULUM_STATE_DIR = os.path.join(os.getcwd(), "assets", "state")
CURRICULUM_STATE_PATH = os.path.join(CURRICULUM_STATE_DIR, "curriculum_finance_state.json")
CURRICULUM_STATE_LOCK_PATH = CURRICULUM_STATE_PATH + ".lock"
RECENT_WINDOW = 15
RECYCLE_COOLDOWN_DAYS = 21

FORBIDDEN_COMPLIANCE_PHRASES = [
    "achete cette action", "achete maintenant", "c'est une valeur sure",
    "rendement garanti", "gain garanti", "investis dans", "tu dois investir",
]


class ComplianceViolationError(Exception):
    def __init__(self, violations):
        self.violations = violations
        details = "; ".join(f"scene {v['scene_id']}: '{v['phrase']}'" for v in violations)
        super().__init__(f"Formulations non conformes detectees : {details}")


def _flatten_curriculum(pillars=None):
    pillars = pillars or CONTENT_PILLARS
    flat = []
    for pillar_key, pillar_data in pillars.items():
        for entry in pillar_data["seed_notions"]:
            flat.append({**entry, "pillar": pillar_key})
    return flat


def _state_lock():
    if FILELOCK_AVAILABLE:
        return FileLock(CURRICULUM_STATE_LOCK_PATH, timeout=10)

    class _NullLock:
        def __enter__(self):
            return self
        def __exit__(self, *exc_info):
            return False

    return _NullLock()


def _load_curriculum_state():
    if not os.path.exists(CURRICULUM_STATE_PATH):
        return {"generated_notions": [], "history": []}
    try:
        with open(CURRICULUM_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"generated_notions": [], "history": []}


def _save_curriculum_state(state):
    os.makedirs(CURRICULUM_STATE_DIR, exist_ok=True)
    tmp_path = CURRICULUM_STATE_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CURRICULUM_STATE_PATH) 
    except OSError as e:
        print(f"⚠️ Impossible d'ecrire l'etat du curriculum : {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _get_full_curriculum(state):
    return _flatten_curriculum() + state.get("generated_notions", [])


def _pillar_with_least_coverage(state):
    history = state.get("history", [])[-60:]
    counts = {key: 0 for key in CONTENT_PILLARS.keys()}
    for h in history:
        pillar = h.get("pillar")
        if pillar in counts:
            counts[pillar] += 1
    return min(counts, key=counts.get)


def _has_missing_accents(text, min_hits=3):
    suspicious_patterns = [
        r"\bepargn", r"\binteret", r"\bstrateg", r"\bbenefic",
        r"\bmarche", r"\bmonetaire", r"\binvestiss", r"\bcapital",
        r"\bcredit", r"\bimpot", r"\breeval", r"\bdifferen",
        r"\ba ete\b", r"\bpeut etre\b", r"\binteresse",
    ]
    text_lower = text.lower()
    hits = sum(1 for p in suspicious_patterns if re.search(p, text_lower))
    has_any_accent = any(c in text_lower for c in ACCENTED_CHARS)
    return hits >= min_hits and not has_any_accent


def _script_missing_accents(script_data):
    scenes = script_data.get("scenes", [])
    if not scenes:
        return False
    full_text = " ".join(s.get("text", "") for s in scenes)
    return _has_missing_accents(full_text)


def _safe_json_loads(content):
    text = content.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        return json.loads(candidate) 

    raise json.JSONDecodeError("Impossible d'extraire un objet JSON valide", text, 0)


def _format_stats_instruction(previous_stats_list, label="hooks"):
    if not previous_stats_list:
        return ""
    stats_text = "\n".join([
        f'- Titre : "{s["title"]}" | Vues : {s["views"]} | Likes : {s["likes"]}'
        for s in previous_stats_list
    ])
    return f"""
ANALYSE DES PERFORMANCES RECENTES (FEEDBACK LOOP) :
Voici les resultats de nos dernieres videos publiees :
{stats_text}


INSTRUCTION D'APPRENTISSAGE (AGENT IA) :
Analyse brievement quelles notions ou structures pedagogiques ont le mieux
retenu l'attention (vues completes, likes). Ajuste le {label} en consequence,
sans jamais sacrifier la clarte pedagogique pour la viralite.
"""


def _format_market_illustration(market_signals, notion):
    if not market_signals:
        return ""
    lines = []
    sentiment = market_signals.get("sentiment")
    if sentiment:
        lines.append(f"- Sentiment de marche actuel : {sentiment}")
    gainers = market_signals.get("top_gainers") or []
    if gainers:
        gainers_text = ", ".join(f"{g['ticker']} (+{g['change_percent']}%)" for g in gainers[:3])
        lines.append(f"- Exemples de titres en forte hausse aujourd'hui : {gainers_text}")
    losers = market_signals.get("top_losers") or []
    if losers:
        losers_text = ", ".join(f"{l['ticker']} ({l['change_percent']}%)" for l in losers[:3])
        lines.append(f"- Exemples de titres en forte baisse aujourd'hui : {losers_text}")
    if not lines:
        return ""
    signals_text = "\n".join(lines)
    return f"""
DONNEES DE MARCHE DU JOUR (OPTIONNEL, A UTILISER SEULEMENT SI PERTINENT) :
{signals_text}


INSTRUCTION :
Si et seulement si un de ces exemples illustre naturellement la notion
"{notion}", tu peux t'en servir comme UN exemple concret parmi d'autres
(formule avec prudence : "par exemple, ces derniers jours..."). Si aucun
exemple ne colle naturellement a la notion, ignore completement ces donnees
et utilise un exemple generique intemporel a la place. La pedagogie prime
toujours sur l'actualite.
"""


def _clean_single_line_title(text):
    if not text:
        return ""
    cleaned = text.replace('"', '').replace('"', '').replace('"', '').strip()
    lines = [line.strip(' -•\t') for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""
    first_line = lines[0]
    return re.sub(r"\s+", " ", first_line).strip()


def _is_valid_topic_candidate(topic, recent_topics=None):
    if not topic:
        return False
    lowered = topic.lower().strip()
    invalid_markers = [
        "mais voici", "voici le bon", "je me suis trompé", "je me suis trompe",
        "option", "proposition", "titre :", "sujet :", "1.", "2.", "3.",
        "\n", "hook", "analyse", "explication"
    ]
    if any(marker in lowered for marker in invalid_markers):
        return False
    word_count = len(topic.split())
    if word_count < 4 or word_count > 18:
        return False
    if lowered.endswith(":"):
        return False
    if topic.count('.') > 1:
        return False
    if recent_topics:
        for past in recent_topics:
            past_words = set(past.lower().split())
            current_words = set(lowered.split())
            overlap = past_words & current_words
            if len(overlap) >= max(3, int(0.5 * min(len(past_words), len(current_words)))):
                return False
    return True


def _normalize_title_for_matching(title):
    text = str(title).lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _enrich_stats_with_local_pattern(previous_stats_list, state):
    if not previous_stats_list:
        return []

    history = state.get("history", [])
    pattern_by_title = {
        _normalize_title_for_matching(h["topic"]): h.get("hook_pattern")
        for h in history
        if h.get("topic") and h.get("hook_pattern")
    }

    enriched = []
    for stat in previous_stats_list:
        stat_copy = dict(stat)
        normalized = _normalize_title_for_matching(stat.get("title", ""))
        matched_pattern = pattern_by_title.get(normalized)
        if matched_pattern:
            stat_copy["pattern"] = matched_pattern
        enriched.append(stat_copy)
    return enriched


def _score_hook(hook, enriched_stats_list):
    if not enriched_stats_list:
        return 0
    best_patterns = {}
    for stat in enriched_stats_list:
        pattern = stat.get("pattern")
        views = stat.get("views", 0)
        if pattern:
            best_patterns[pattern] = best_patterns.get(pattern, 0) + views
    return best_patterns.get(hook.get("pattern"), 0)


class ContentBrain:
    def _build_client(self, provider):
        if provider == "groq":
            groq_key = os.getenv("GROQ_API_KEY")
            if not groq_key:
                return None
            return OpenAI(base_url="[https://api.groq.com/openai/v1](https://api.groq.com/openai/v1)", api_key=groq_key)
        if provider == "gemini":
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                return None
            return OpenAI(
                base_url="[https://generativelanguage.googleapis.com/v1beta/openai/](https://generativelanguage.googleapis.com/v1beta/openai/)",
                api_key=gemini_key
            )
        return None

    def _model_for(self, provider):
        return GROQ_MODEL if provider == "groq" else GEMINI_MODEL

    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False, skip_providers=None):
        skip_providers = skip_providers or set()
        last_error = None
        for provider in ("groq", "gemini"):
            if provider in skip_providers:
                continue
            client = self._build_client(provider)
            if client is None:
                print(f"Cle API absente pour {provider}, on passe au suivant...")
                continue
            try:
                kwargs = {
                    "model": self._model_for(provider),
                    "messages": messages,
                    "temperature": temperature,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**kwargs)
                print(f"Reponse obtenue via {provider}")
                return response.choices[0].message.content, provider
            except Exception as e:
                print(f"Echec avec {provider}: {e}")
                last_error = e
                continue
        raise RuntimeError(f"Aucun provider disponible. Derniere erreur: {last_error}")

    def expand_curriculum_with_llm(self, pillar_key, existing_notions, n=8):
        pillar_label = CONTENT_PILLARS[pillar_key]["label"]
        existing_text = "\n".join(f"- {n_}" for n_ in existing_notions) or "(aucune)"

        prompt = f"""
Tu es directeur pedagogique d'une chaine francophone d'education financiere.

PILIER : {pillar_label}

NOTIONS DEJA TRAITEES DANS CE PILIER (a ne surtout pas repeter) :
{existing_text}

OBJECTIF :
Genere {n} NOUVELLES notions financieres precises et enseignables, dans ce
pilier, que le grand
