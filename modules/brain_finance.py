import os
import re
import json
import random
import time
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

try:
    from filelock import FileLock
    FILELOCK_AVAILABLE = True
except ImportError:
    FILELOCK_AVAILABLE = False

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(accents obligatoires). Exemples : 'epargne' avec accent, 'interet' avec "
    "accent, 'strategie' avec accent, 'benefice' avec accent."
)

COMPLIANCE_INSTRUCTION = (
    "REGLE DE CONFORMITE (AMF) ABSOLUE : Tu adoptes un ton de 'révélation' et de 'secret', "
    "MAIS ce contenu reste de l'éducation financière. Ne donne JAMAIS de conseil en investissement personnalisé. "
    "N'utilise jamais de formulations impératives du type 'achète cette action', 'investis là-dedans'. "
    "Parle des 'mécanismes', des 'règles cachées', de 'ce que font les riches'. "
    "N'invente aucune promesse de gain garanti."
)

COMPLIANCE_RETRY_INSTRUCTION = (
    "ATTENTION - LA GENERATION PRECEDENTE A ECHOUE LE CONTROLE DE CONFORMITE. "
    "Même avec un ton mystérieux et percutant, tu ne dois formuler AUCUN conseil direct d'achat. "
    "Garde le mystère, mais reste éducatif. " + COMPLIANCE_INSTRUCTION
)

PERSONA_INSTRUCTION = (
    "PERSONA : Tu n'es plus un prof de finance ennuyeux. Tu es un 'insider', un initié "
    "qui révèle les rouages cachés de l'argent et du système économique avec un ton direct, "
    "mystérieux, et légèrement provocateur. Ta promesse globale est : 'Je t'explique l'argent en moins d'une minute'. "
    "Le spectateur doit avoir l'impression de découvrir un secret jalousement gardé."
)

VISUAL_CONSISTENCY_INSTRUCTION = (
    "COHERENCE VISUELLE OBLIGATOIRE (STYLE MYSTERE FINANCIER) : "
    "L'esthétique doit être moderne, sombre, luxueuse et cinématique (dark corporate, néons discrets, "
    "ambiance 'Succession' ou 'Loup de Wall Street' version sombre). "
    "Chaque 'image_prompt' doit réutiliser EXACTEMENT la même palette de couleurs sombres et "
    "le même éclairage définis dans 'visual_identity'. Interdiction d'utiliser les mots CGI, 3D, render."
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

ANGLES = ["secret_des_riches", "illusion_du_systeme", "chiffre_choc", "erreur_fatale"]

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
    cleaned = text.replace('"', '').strip()
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
        "voici le bon", "je me suis trompe",
        "option", "proposition", "titre :", "sujet :", "1.", "2.", "3.",
        "\n", "hook", "analyse", "explication"
    ]
    if any(marker in lowered for marker in invalid_markers):
        return False
        
    word_count = len(topic.split())
    if word_count < 4 or word_count > 30:
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
    def _build_client(self):
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("Clé GROQ_API_KEY introuvable dans l'environnement.")
        return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)

    def _extract_content(self, response):
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        if not choices:
            raise ValueError(f"Réponse inattendue de Groq: {response}")

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

        if not content:
            raise ValueError(f"Contenu vide de Groq: {response}")

        return content

    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False):
        client = self._build_client()
        last_error = None

        for attempt in range(3):
            try:
                kwargs = {
                    "model": GROQ_MODEL,
                    "messages": messages,
                    "temperature": temperature,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                response = client.chat.completions.create(**kwargs)
                content = self._extract_content(response)
                print("✅ Reponse obtenue via Groq")

                time.sleep(4)
                return content

            except Exception as e:
                print(f"⚠️ Echec avec Groq (Tentative {attempt + 1}/3): {e}")
                last_error = e
                time.sleep(8)

        raise RuntimeError(f"Erreur critique Groq après 3 tentatives. Dernière erreur: {last_error}")

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
pilier, que le grand public francais confond souvent ou ne connait pas.
Chaque notion doit etre assez precise pour tenir dans UNE seule video de
60 a 90 secondes (pas un sujet trop vaste).

REGLES :
- Chaque notion est une phrase courte en francais parfaitement accentue.
- Niveau parmi : "debutant", "intermediaire", "avance".
- Aucune redite avec les notions deja traitees, meme reformulees.
- {ACCENT_INSTRUCTION}

FORMAT DE SORTIE : JSON uniquement, sans Markdown.
{{
  "notions": [
    {{"notion": "...", "niveau": "debutant"}}
  ]
}}
"""
        messages = [
            {
                "role": "system",
                "content": f"Tu produis uniquement du JSON valide avec exactement {n} notions inedites. {ACCENT_INSTRUCTION}"
            },
            {"role": "user", "content": prompt},
        ]

        try:
            content = self._call_with_fallback(messages, temperature=0.9, json_mode=True)
            data = _safe_json_loads(content)
            notions = data.get("notions", [])
            return [
                {"notion": n_["notion"], "niveau": n_.get("niveau", "debutant"), "pillar": pillar_key}
                for n_ in notions if n_.get("notion")
            ]
        except Exception as e:
            print(f"⚠️ Echec de l'expansion du curriculum via LLM : {e}")
            return []

    def _pick_recycled_notion_with_new_angle(self, state):
        history = state.get("history", [])
        if not history:
            return None, random.choice(ANGLES)

        now = datetime.now()
        eligible = []
        for h in history:
            try:
                h_date = datetime.fromisoformat(h["date"])
            except (KeyError, ValueError):
                continue
            if now - h_date >= timedelta(days=RECYCLE_COOLDOWN_DAYS):
                eligible.append(h)

        if not eligible:
            eligible = history

        past_by_notion = {}
        for h in history:
            past_by_notion.setdefault(h["notion"], []).append(h.get("angle"))

        candidate = random.choice(eligible)
        notion_text = candidate["notion"]
        used_angles = set(past_by_notion.get(notion_text, []))
        available_angles = [a for a in ANGLES if a not in used_angles]
        angle = random.choice(available_angles) if available_angles else random.choice(ANGLES)

        notion_entry = {
            "notion": notion_text,
            "niveau": candidate.get("niveau", "intermediaire"),
            "pillar": candidate.get("pillar", "epargne"),
        }
        return notion_entry, angle

    def pick_curriculum_notion(self):
        with _state_lock():
            state = _load_curriculum_state()
            all_notions = _get_full_curriculum(state)
            recent_notions = {h["notion"] for h in state.get("history", [])[-RECENT_WINDOW:]}

            candidates = [n for n in all_notions if n["notion"] not in recent_notions]

            if candidates:
                notion_entry = random.choice(candidates)
                angle = random.choice(ANGLES)
                return notion_entry, angle, state

            print("📚 Curriculum recent epuise, expansion automatique du pilier le moins couvert...")
            pillar_key = _pillar_with_least_coverage(state)
            existing_in_pillar = [n["notion"] for n in all_notions if n.get("pillar") == pillar_key]
            new_notions = self.expand_curriculum_with_llm(pillar_key, existing_in_pillar, n=8)

            if new_notions:
                state["generated_notions"].extend(new_notions)
                _save_curriculum_state(state)
                notion_entry = random.choice(new_notions)
                angle = random.choice(ANGLES)
                print(f"✅ {len(new_notions)} nouvelles notions ajoutees au pilier '{pillar_key}'.")
                return notion_entry, angle, state

            print("⚠️ Expansion impossible, recyclage d'une ancienne notion avec angle inedit.")
            notion_entry, angle = self._pick_recycled_notion_with_new_angle(state)
            if notion_entry is None:
                notion_entry = random.choice(_flatten_curriculum())
            return notion_entry, angle, state

    def get_pedagogical_topic(self, previous_stats_list=None, market_signals=None):
        notion_entry, angle, state = self.pick_curriculum_notion()
        notion = notion_entry["notion"]
        niveau = notion_entry.get("niveau", "intermediaire")

        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")
        market_instruction = _format_market_illustration(market_signals, notion)

        messages = [
            {
                "role": "system",
                "content": (
                    f"{PERSONA_INSTRUCTION}\n"
                    "Tu dois créer une véritable IDENTITÉ de série (comme une mini-série Netflix sur l'argent). "
                    "Le but n'est pas de faire un titre scolaire, mais de créer une dissonance cognitive, de révéler un secret d'initié ou de poser une situation hyper concrète pour donner envie de voir le prochain épisode.\n\n"
                    "FORMAT EXIGÉ : Commence TOUJOURS par 'ARGENT #XX :' (invente un numéro aléatoire entre 01 et 99). "
                    "Réponds UNIQUEMENT avec un seul titre en français, sur UNE seule ligne. MAXIMUM 18 MOTS STRICTEMENT.\n\n"
                    "ANALYSE CES EXEMPLES POUR COMPRENDRE L'ADN DE LA CHAÎNE (applique cette même psychologie à la notion demandée) :\n"
                    "- Paradoxe/Dissonance : 'ARGENT #01 : Pourquoi ton salaire augmente mais tu as l'impression de t'appauvrir ?'\n"
                    "- Comportement d'initié : 'ARGENT #02 : Pourquoi les riches ne gardent presque jamais tout leur argent sur leur compte ?'\n"
                    "- Cas hyper concret + Mise en garde : 'ARGENT #03 : Si tu gagnes 2 000 €, voici l'erreur que tu ne dois surtout pas faire.'\n"
                    "- Projection mathématique choc : 'ARGENT #04 : 100 € par mois pendant 20 ans : voici ce que ça peut réellement devenir.'\n\n"
                    f"{ACCENT_INSTRUCTION} {COMPLIANCE_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Notion financière à enseigner (niveau {niveau}) : {notion}\n"
                    f"Angle de révélation imposé : {angle.replace('_', ' ')}\n"
                    "Applique l'ADN de la chaîne pour créer LE titre percutant de cet épisode. Reste très court (18 mots max)."
                    + stats_instruction
                    + market_instruction
                )
            }
        ]
        
        last_topic = ""
        for attempt in range(2):
            content = self._call_with_fallback(messages, temperature=0.85)
            topic = _clean_single_line_title(content)
            last_topic = topic
            if _is_valid_topic_candidate(topic):
                return {
                    "topic": topic, "notion": notion, "niveau": niveau,
                    "angle": angle, "pillar": notion_entry.get("pillar"), "state": state,
                }
            print(f"⚠️ Sujet invalide généré (tentative {attempt + 1}) : {topic}")

        raise ValueError(f"Impossible d'obtenir un sujet valide : {last_topic}")

    def generate_hook_variants(self, topic, notion=None, angle=None, n=5, previous_stats_list=None):
        print(f"Génération de {n} hooks mystères pour: {topic}...")
        stats_instruction = _format_stats_instruction(previous_stats_list, label="hooks")
        
        prompt = f"""
{PERSONA_INSTRUCTION}

SUJET / TITRE :
{topic}
NOTION CACHÉE : {notion}

OBJECTIF :
Génère {n} hooks différents. Le hook est la toute première phrase de la vidéo (max 3 secondes).
Il doit créer un choc cognitif, révéler une dissonance ou dénoncer une illusion du système financier.

REGLES :
- 12 à 18 mots max. Phrase très orale, percutante.
- Ne mentionne PAS le préfixe 'ARGENT #XX' dans le texte lu à voix haute, c'est juste pour le titre visuel.
- Varie les approches : le piège invisible, le secret des ultra-riches, la fausse croyance populaire.
- Interdiction d'utiliser : "Aujourd'hui", "Bienvenue", "Dans cette vidéo", "Savais-tu que".
- {COMPLIANCE_INSTRUCTION}

FORMAT DE SORTIE (JSON) :
{{
  "analyse_agent": "Pourquoi ces hooks vont retenir l'attention.",
  "hooks": [
    {{
      "text": "Phrase du hook.",
      "pattern": "illusion | secret | choc",
      "raison": "Pourquoi ça marche."
    }}
  ]
}}
"""
        messages = [
            {"role": "system", "content": f"Produis uniquement du JSON valide. {ACCENT_INSTRUCTION}"},
            {"role": "user", "content": prompt},
        ]
        content = self._call_with_fallback(messages, temperature=1.0, json_mode=True)
        data = _safe_json_loads(content)

        if _script_missing_accents({"scenes": [{"text": h.get("text", "")} for h in data.get("hooks", [])]}):
            print("⚠️ Accents manquants détectés, nouvelle tentative Groq...")
            content = self._call_with_fallback(messages, temperature=1.0, json_mode=True)
            data = _safe_json_loads(content)

        return data.get("hooks")

    def get_newsjacking_topic(self, market_signals, previous_stats_list=None):
        if not market_signals:
            raise ValueError("Pas de signaux de marche disponibles pour le mode newsjacking.")

        market_instruction = _format_market_illustration(market_signals, "actualite des marches")
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet d'actualite")

        messages = [
            {
                "role": "system",
                "content": (
                    f"{PERSONA_INSTRUCTION} "
                    "Une actualité de marché vient de se produire. Transforme-la en LECON mystérieuse : "
                    "n'explique pas juste 'ce qui bouge', révèle CE QUE CA CACHE sur le système. "
                    "FORMAT EXIGÉ : Commence toujours par 'ARGENT #XX :'. "
                    "Réponds UNIQUEMENT avec un titre en français, une seule ligne, max 18 mots. "
                    f"{ACCENT_INSTRUCTION} {COMPLIANCE_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": (
                    "Transforme l'actualité de marché ci-dessous en sujet de vidéo révélation."
                    + market_instruction
                    + stats_instruction
                )
            }
        ]

        content = self._call_with_fallback(messages, temperature=0.85)
        return _clean_single_line_title(content)

    def record_topic_used(self, state, notion, niveau, angle, pillar, topic=None, hook_pattern=None):
        with _state_lock():
            state.setdefault("history", []).append({
                "notion": notion,
                "niveau": niveau,
                "angle": angle,
                "pillar": pillar,
                "topic": topic,
                "hook_pattern": hook_pattern,
                "date": datetime.now().isoformat(),
            })
            state["history"] = state["history"][-500:]
            _save_curriculum_state(state)

    def pick_best_hook(self, hooks, previous_stats_list=None, state=None):
        if not previous_stats_list or not state:
            return hooks[0]
        enriched_stats = _enrich_stats_with_local_pattern(previous_stats_list, state)
        if not any(s.get("pattern") for s in enriched_stats):
            return hooks[0]
        scored = sorted(hooks, key=lambda h: _score_hook(h, enriched_stats), reverse=True)
        return scored[0]

    def generate_script(self, topic, notion=None, angle=None, chosen_hook=None):
        return self.generate_script_with_target(topic, notion=notion, angle=angle, scene_count=11, chosen_hook=chosen_hook)

    def generate_script_with_target(self, topic, notion=None, angle=None, scene_count=11, chosen_hook=None):
        if scene_count < 6: raise ValueError("scene_count doit être >= 6.")

        hook_instruction = (
            "La scene 1 doit reprendre exactement ce hook : " + json.dumps(chosen_hook, ensure_ascii=False)
        ) if chosen_hook else "Scene 1 - hook : Accroche percutante et mystérieuse."

        skeleton_dict = {
            "title": topic,
            "notion_enseignee": notion or "",
            "visual_identity": "Consistent modern dark cinematic finance world, sleek corporate aesthetic, deep shadows with subtle neon accents, highly photorealistic",
            "audio_profile": "French premium narrator, confident, slightly mysterious, sharp, insider tone, natural pacing",
            "scenes": [
                {
                    "id": 1,
                    "text": "Phrase française.",
                    "voice_direction": "French premium narrator, intriguing, revealing a secret",
                    "pause_after_ms": 300,
                    "stock_search": "dark modern finance background",
                    "image_prompt": "Detailed English visual prompt following the modular structure, matching visual_identity strictly",
                    "mood": "intriguing",
                    "role": "hook"
                }
            ]
        }
        json_skeleton = json.dumps(skeleton_dict, ensure_ascii=False, indent=2)

        def build_prompt(compliance_block):
            lines = [
                PERSONA_INSTRUCTION,
                "",
                f"TITRE DE LA VIDÉO : {topic}",
                f"VERITABLE NOTION A ENSEIGNER : {notion}",
                "",
                "STRUCTURE NARRATIVE (Le format 'Révélation') :",
                f"- {hook_instruction}",
                "- Scene 2 - L'Illusion : Montre ce que 99% des gens croient à tort sur ce sujet.",
                "- Scene 3 - La Faille : Explique pourquoi cette croyance les maintient dans la 'rat race' ou leur fait perdre de l'argent.",
                f"- Scenes 4 à {scene_count - 3} - Le Mécanisme Caché (La réalité) : Décortique comment le système fonctionne vraiment pas à pas.",
                f"- Scene {scene_count - 2} - L'Exemple Chiffré : Un cas concret et frappant.",
                f"- Scene {scene_count - 1} - La Règle d'Or : Une phrase mémorable à retenir pour changer sa vision.",
                f"- Scene {scene_count} - Outro : Un call-to-action mystérieux ou une question ouverte (ex: 'Et toi, de quel côté es-tu ?').",
                "",
                "REGLES VISUELLES (MYSTERE FINANCIER) :",
                "- 'image_prompt' DOIT suivre l'ambiance définie (sombre, luxueux, financier, cinématique).",
                "- PAS de 3D, PAS de CGI, uniquement du photoréalisme.",
                "",
                compliance_block,
                VISUAL_CONSISTENCY_INSTRUCTION,
                "",
                "FORMAT EXIGÉ : Uniquement du JSON valide calqué sur ce squelette :"
            ]
            lines.append(json_skeleton)
            return "\n".join(lines)

        for attempt in range(2):
            compliance_block = COMPLIANCE_INSTRUCTION if attempt == 0 else COMPLIANCE_RETRY_INSTRUCTION
            prompt = build_prompt(compliance_block)
            messages = [
                {"role": "system", "content": f"Uniquement du JSON valide pour {scene_count} scènes. {ACCENT_INSTRUCTION}"},
                {"role": "user", "content": prompt}
            ]
            
            content = self._call_with_fallback(messages, temperature=0.7, json_mode=True)
            data = _safe_json_loads(content)
            
            if _script_missing_accents(data):
                print("⚠️ Accents manquants détectés, nouvelle tentative Groq...")
                content = self._call_with_fallback(messages, temperature=0.7, json_mode=True)
                data = _safe_json_loads(content)

            try:
                self._validate_script(data, scene_count)
                return data
            except ComplianceViolationError as e:
                print(f"🚫 Violation de conformité détectée : {e}")
                continue
                
        raise RuntimeError("Échec de génération après 2 tentatives.")

    def _normalize_word(self, text):
        text = str(text).lower().strip()
        text = text.replace("’", "").replace("'", "")
        text = re.sub(r"[^a-zàâçéèêëîïôûùüÿœ\- ]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _validate_script(self, data, scene_count):
        scenes = data.get("scenes")
        if not isinstance(scenes, list):
            raise ValueError("La reponse ne contient pas de tableau scenes.")
        if len(scenes) != scene_count:
            raise ValueError(f"Nombre de scenes invalide : {len(scenes)} au lieu de {scene_count}.")

        expected_ids = list(range(1, scene_count + 1))
        actual_ids = [scene.get("id") for scene in scenes]
        if actual_ids != expected_ids:
            raise ValueError(f"IDs de scenes invalides : {actual_ids}")

        allowed_roles = {
            "hook", "misconception", "illusion", "faille", "definition", 
            "mechanism", "analogy", "example", "summary", "cta", "regle", 
            "value", "tension", "context", "escalation", "reveal"
        }
        allowed_moods = {
            "confident", "sharp", "clear", "pedagogical", "engaging", 
            "revelatory", "intriguing", "ominous", "tense", "awe", 
            "scientific", "melancholic", "misconception", "illusion", "faille"
        }

        compliance_violations = []

        for scene in scenes:
            text = scene.get("text", "").strip()
            voice_direction = scene.get("voice_direction", "").strip()
            pause_after_ms = scene.get("pause_after_ms")
            emphasis = scene.get("tts_emphasis_word")
            role = scene.get("role")
            mood = scene.get("mood")
            stock_search = scene.get("stock_search", "").strip()
            image_prompt = scene.get("image_prompt", "").strip()

            if not text:
                raise ValueError(f"Scene {scene.get('id')} : text manquant.")
            if not voice_direction:
                raise ValueError(f"Scene {scene.get('id')} : voice_direction manquant.")

            if isinstance(pause_after_ms, float) and pause_after_ms.is_integer():
                pause_after_ms = int(pause_after_ms)
                scene["pause_after_ms"] = pause_after_ms
            if not isinstance(pause_after_ms, int) or not (180 <= pause_after_ms <= 450):
                raise ValueError(f"Scene {scene.get('id')} : pause_after_ms invalide ({pause_after_ms}).")

            # --- CORRECTION AUTOMATIQUE DES RÔLES ---
            if role:
                role = str(role).strip().lower().replace("l'", "").replace("la ", "").replace("le ", "")
                if role not in allowed_roles:
                    role = "mechanism"
                scene["role"] = role
            else:
                scene["role"] = "mechanism"

            # --- CORRECTION AUTOMATIQUE DES MOODS (ANTI-PLANTAGE) ---
            if mood:
                mood = str(mood).strip().lower()
                if mood not in allowed_moods:
                    mood = "intriguing"
                scene["mood"] = mood
            else:
                scene["mood"] = "intriguing"

            if not stock_search:
                scene["stock_search"] = "dark modern finance background"
            if not image_prompt:
                scene["image_prompt"] = "Detailed English visual prompt matching visual_identity strictly"

            text_lower = text.lower()
            for phrase in FORBIDDEN_COMPLIANCE_PHRASES:
                if phrase in text_lower:
                    compliance_violations.append({"scene_id": scene.get("id"), "phrase": phrase})

            if emphasis:
                normalized_text = self._normalize_word(text)
                normalized_emphasis = self._normalize_word(emphasis)
                text_words = normalized_text.split()
                if normalized_emphasis not in text_words:
                    print(
                        f"⚠️ Scene {scene.get('id')} : tts_emphasis_word='{emphasis}' absent du text. "
                        f"Emphase ignoree."
                    )
                    scene["tts_emphasis_word"] = None

        if "title" not in data or not str(data["title"]).strip():
            raise ValueError("Titre manquant.")
        if "visual_identity" not in data or not str(data["visual_identity"]).strip():
            raise ValueError("visual_identity manquant.")
        if "audio_profile" not in data or not str(data["audio_profile"]).strip():
            raise ValueError("audio_profile manquant.")

        if compliance_violations:
            raise ComplianceViolationError(compliance_violations)
