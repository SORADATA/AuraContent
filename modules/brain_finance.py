"""
ContentBrain Finance v4 — curriculum auto-extensible base sur des piliers.

Nouveaute vs v3 :
- CURRICULUM_FINANCE (liste figee) devient une liste de DEPART sous des
  PILLARS larges et permanents.
- Quand toutes les notions recentes ont ete traitees, le brain genere lui-meme
  de nouvelles sous-notions via LLM dans le pilier le moins couvert, et les
  sauvegarde definitivement dans curriculum_finance_state.json.
  => Le curriculum ne s'epuise jamais.
- Si meme l'expansion echoue (LLM indisponible), une notion deja traitee peut
  revenir, mais TOUJOURS avec un angle different (mythe, etude de cas,
  comparaison, question d'audience...) pour ne jamais sonner repetitif.
"""

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

PEDAGOGY_INSTRUCTION = (
    "PRIORITE PEDAGOGIQUE : cette video doit apprendre une notion financiere "
    "reelle et transferable, pas seulement divertir. A la fin, le spectateur "
    "doit pouvoir expliquer le concept a quelqu'un d'autre avec ses propres mots. "
    "Utilise une analogie simple et concrete pour la notion abordee. "
    "Privilegie la clarte a la sophistication : une seule idee centrale par video."
)


# ----------------------------------------------------------------------
# PILIERS : themes larges et PERMANENTS. Ne s'epuisent jamais par design.
# Chaque pilier contient des notions de depart ; le brain en genere d'autres
# tout seul quand necessaire (voir expand_curriculum_with_llm).
# ----------------------------------------------------------------------
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

CURRICULUM_STATE_PATH = "curriculum_finance_state.json"
RECENT_WINDOW = 15  # nb de dernieres notions a ne pas repeter avant expansion/recyclage
RECYCLE_COOLDOWN_DAYS = 21  # delai mini avant de reutiliser une notion avec un nouvel angle


def _flatten_curriculum(pillars=None):
    pillars = pillars or CONTENT_PILLARS
    flat = []
    for pillar_key, pillar_data in pillars.items():
        for entry in pillar_data["seed_notions"]:
            flat.append({**entry, "pillar": pillar_key})
    return flat


def _load_curriculum_state():
    if not os.path.exists(CURRICULUM_STATE_PATH):
        return {"generated_notions": [], "history": []}
    try:
        with open(CURRICULUM_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"generated_notions": [], "history": []}


def _save_curriculum_state(state):
    try:
        with open(CURRICULUM_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"⚠️ Impossible d'ecrire l'etat du curriculum : {e}")


def _get_full_curriculum(state):
    return _flatten_curriculum() + state.get("generated_notions", [])


def _pillar_with_least_coverage(state):
    """Retourne le pilier le moins souvent traite dans l'historique recent,
    pour equilibrer les themes enseignes sur la duree."""
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


def _score_hook(hook, previous_stats_list):
    if not previous_stats_list:
        return 0
    best_patterns = {}
    for stat in previous_stats_list:
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
            return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)
        if provider == "gemini":
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                return None
            return OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
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

    # ------------------------------------------------------------------
    # EXPANSION AUTOMATIQUE DU CURRICULUM
    # ------------------------------------------------------------------
    def expand_curriculum_with_llm(self, pillar_key, existing_notions, n=8):
        """Genere n nouvelles sous-notions dans un pilier donne, distinctes
        des notions deja existantes. Ce qui rend le curriculum infini."""
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
            content, _ = self._call_with_fallback(messages, temperature=0.9, json_mode=True)
            data = json.loads(content)
            notions = data.get("notions", [])
            return [
                {"notion": n_["notion"], "niveau": n_.get("niveau", "debutant"), "pillar": pillar_key}
                for n_ in notions if n_.get("notion")
            ]
        except Exception as e:
            print(f"⚠️ Echec de l'expansion du curriculum via LLM : {e}")
            return []

    def _pick_recycled_notion_with_new_angle(self, state):
        """Dernier recours : reutilise une ancienne notion mais impose un
        angle jamais utilise pour elle, et respecte un delai minimum."""
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
        """
        Coeur du systeme anti-epuisement :
        1. Cherche une notion non traitee recemment.
        2. Si tout a ete traite, genere de nouvelles notions via LLM dans le
           pilier le moins couvert (curriculum grandit tout seul, pour de bon).
        3. Si l'expansion echoue, recycle une vieille notion avec un angle
           inedit plutot que de planter.
        """
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
        """MODE PRINCIPAL : pioche une notion (fraiche ou recyclee avec angle
        neuf) et genere un titre accrocheur pour l'enseigner."""
        notion_entry, angle, state = self.pick_curriculum_notion()
        notion = notion_entry["notion"]
        niveau = notion_entry.get("niveau", "intermediaire")

        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")
        market_instruction = _format_market_illustration(market_signals, notion)

        angle_instruction = (
            f"ANGLE IMPOSE POUR CETTE VIDEO : {angle.replace('_', ' ')}. "
            "Le titre doit refleter clairement cet angle, pas juste redire la notion."
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es prof de finance personnelle sur TikTok. Ta mission est "
                    "d'enseigner une notion precise de facon claire et memorable, "
                    "pas de faire du buzz vide. "
                    "Transforme la notion fournie en titre accrocheur mais honnete, "
                    "qui donne envie d'apprendre, en respectant l'angle impose. "
                    "Reponds UNIQUEMENT avec un seul titre en francais, sur UNE seule ligne, "
                    "sans guillemets, sans liste, sans justification. Maximum 18 mots. "
                    f"{ACCENT_INSTRUCTION} {PEDAGOGY_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Notion a enseigner (niveau {niveau}) : {notion}\n"
                    f"{angle_instruction}\n"
                    "Transforme cette notion en titre de video TikTok accrocheur et honnete."
                    + stats_instruction
                    + market_instruction
                )
            }
        ]

        last_topic = ""
        for attempt in range(2):
            content, _ = self._call_with_fallback(messages, temperature=0.85)
            topic = _clean_single_line_title(content)
            last_topic = topic
            if _is_valid_topic_candidate(topic):
                return {
                    "topic": topic, "notion": notion, "niveau": niveau,
                    "angle": angle, "pillar": notion_entry.get("pillar"), "state": state,
                }
            print(f"⚠️ Sujet invalide genere (tentative {attempt + 1}) : {topic}")

        raise ValueError(f"Impossible d'obtenir un sujet valide apres 2 tentatives : {last_topic}")

    def record_topic_used(self, state, notion, niveau, angle, pillar):
        """A appeler apres publication reussie pour alimenter l'historique
        anti-repetition et le suivi de couverture des piliers."""
        state.setdefault("history", []).append({
            "notion": notion,
            "niveau": niveau,
            "angle": angle,
            "pillar": pillar,
            "date": datetime.now().isoformat(),
        })
        state["history"] = state["history"][-500:]
        _save_curriculum_state(state)

    # ------------------------------------------------------------------
    # MODE PONCTUEL : reaction a l'actualite de marche (inchange)
    # ------------------------------------------------------------------
    def get_newsjacking_topic(self, market_signals, previous_stats_list=None):
        if not market_signals:
            raise ValueError("Pas de signaux de marche disponibles pour le mode newsjacking.")

        market_instruction = _format_market_illustration(market_signals, "actualite des marches")
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet d'actualite")

        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es prof de finance personnelle. Une actualite de marche vient "
                    "de se produire. Transforme-la en LEÇON pour les debutants : "
                    "n'explique pas juste 'ce qui bouge', explique CE QUE CA APPREND "
                    "sur le fonctionnement des marches ou de l'argent en general. "
                    "Reponds UNIQUEMENT avec un titre en francais, une seule ligne, max 18 mots. "
                    f"{ACCENT_INSTRUCTION} {PEDAGOGY_INSTRUCTION} {COMPLIANCE_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": (
                    "Transforme l'actualite de marche ci-dessous en sujet de video "
                    "pedagogique (pas juste informatif)."
                    + market_instruction
                    + stats_instruction
                )
            }
        ]

        content, _ = self._call_with_fallback(messages, temperature=0.85)
        return _clean_single_line_title(content)

    def generate_hook_variants(self, topic, notion=None, angle=None, n=5, previous_stats_list=None):
        print(f"Generation de {n} hooks pedagogiques pour: {topic}...")

        stats_instruction = _format_stats_instruction(
            previous_stats_list, label="le niveau de clarte pedagogique et la structure des hooks"
        )
        notion_line = f"NOTION ENSEIGNEE : {notion}\n" if notion else ""
        angle_line = f"ANGLE IMPOSE : {angle.replace('_', ' ')}\n" if angle else ""

        prompt = f"""
Tu es prof de finance personnelle qui excelle a rendre des concepts arides
captivants sur TikTok, sans jamais sacrifier l'exactitude pedagogique.

{stats_instruction}

{notion_line}{angle_line}SUJET / TITRE :
{topic}

OBJECTIF :
Genere {n} hooks differents pour la meme video pedagogique, tous alignes sur
l'angle impose. Chaque hook doit arreter le scroll en moins de 3 secondes ET
annoncer clairement ce que le spectateur va APPRENDRE.

REGLES POUR CHAQUE HOOK :
- 12 a 18 mots, phrase complete en francais oral et naturel.
- Doit creer une envie d'apprendre : une question qui revele une lacune, un
  malentendu courant a corriger, ou une comparaison qui simplifie.
- Varie les patterns : question directe, statistique choc, erreur courante,
  contre-intuition, mise en garde.
- N'utilise jamais "Aujourd'hui", "Savais-tu que", "Bienvenue", "Dans cette video".
- N'invente ni chiffre impossible ni promesse de gain garanti.
- {ACCENT_INSTRUCTION}
- {COMPLIANCE_INSTRUCTION}

FORMAT DE SORTIE :
Retourne uniquement un objet JSON valide, sans bloc Markdown.

{{
  "analyse_agent": "Une phrase courte (max 20 mots) expliquant l'ajustement pedagogique fait.",
  "hooks": [
    {{
      "text": "Phrase du hook.",
      "pattern": "question | statistique | erreur_courante | contre-intuition | mise_en_garde",
      "raison": "Une phrase expliquant pourquoi ce hook donne envie d'apprendre."
    }}
  ]
}}
"""
        messages = [
            {
                "role": "system",
                "content": f"Tu produis uniquement du JSON valide avec exactement {n} hooks pedagogiques. {ACCENT_INSTRUCTION}"
            },
            {"role": "user", "content": prompt},
        ]

        content, provider_used = self._call_with_fallback(messages, temperature=1.05, json_mode=True)
        data = json.loads(content)

        if provider_used == "groq" and _script_missing_accents({
            "scenes": [{"text": h.get("text", "")} for h in data.get("hooks", [])]
        }):
            print("⚠️ Accents manquants detectes (Groq), nouvelle tentative via Gemini...")
            content, _ = self._call_with_fallback(messages, temperature=1.05, json_mode=True, skip_providers={"groq"})
            data = json.loads(content)

        analyse = data.get("analyse_agent", "")
        if analyse:
            print(f"\n🧠 Réflexion de l'Agent IA : {analyse}\n")

        hooks = data.get("hooks")
        if not isinstance(hooks, list) or len(hooks) != n:
            raise ValueError(f"Nombre de hooks invalide: {len(hooks) if isinstance(hooks, list) else 0} au lieu de {n}.")

        return hooks

    def pick_best_hook(self, hooks, previous_stats_list=None):
        if not previous_stats_list:
            return hooks[0]
        scored = sorted(hooks, key=lambda h: _score_hook(h, previous_stats_list), reverse=True)
        return scored[0]

    def generate_script(self, topic, notion=None, angle=None, chosen_hook=None):
        return self.generate_script_with_target(topic, notion=notion, angle=angle, scene_count=11, chosen_hook=chosen_hook)

    def generate_script_with_target(self, topic, notion=None, angle=None, scene_count=11, chosen_hook=None):
        if scene_count < 6:
            raise ValueError("scene_count doit etre superieur ou egal a 6.")

        print(f"Ecriture du script pedagogique pour : {topic} ({scene_count} scenes)...")

        hook_instruction = (
            f'La scene 1 doit reprendre exactement ou reformuler tres legerement ce hook deja valide : "{chosen_hook}"'
            if chosen_hook else
            "Scene 1 - hook : une phrase de 12 a 18 mots qui annonce clairement ce que le spectateur va apprendre."
        )
        notion_line = f"NOTION CENTRALE A ENSEIGNER : {notion}\n" if notion else ""
        angle_line = f"ANGLE IMPOSE : {angle.replace('_', ' ')}\n" if angle else ""

        prompt = f"""
Tu es prof de finance personnelle, redacteur en chef d'une chaine francophone
d'education financiere dont la mission est d'ENSEIGNER durablement, pas
seulement d'informer sur l'actualite.

{notion_line}{angle_line}TITRE :
{topic}

OBJECTIF :
Creer une video TikTok pedagogique ou, a la fin, le spectateur peut expliquer
la notion avec ses propres mots. Le divertissement sert la comprehension,
jamais l'inverse.

CONTRAINTE ABSOLUE :
Genere exactement {scene_count} scenes.

LANGUES :
- "text" : uniquement en francais naturel et oral, PARFAITEMENT ACCENTUE.
- "voice_direction" : uniquement en anglais.
- "stock_search" : uniquement en anglais, mots-cles concrets finance/bureau/argent.
- "image_prompt" : uniquement en anglais.
- "mood" et "role" : uniquement parmi les valeurs autorisees.

{ACCENT_INSTRUCTION}
{COMPLIANCE_INSTRUCTION}
{PEDAGOGY_INSTRUCTION}

STRUCTURE NARRATIVE PEDAGOGIQUE (methode : erreur -> mecanisme -> analogie -> application) :
- {hook_instruction}
- Scene 2 - erreur courante :
  montre le malentendu ou l'erreur que la plupart des gens font sur cette notion.
- Scene 3 - definition simple :
  donne une definition claire de la notion en une phrase, sans jargon inutile.
- Scenes 4 a {scene_count - 4} - mecanisme :
  explique pas a pas comment ca fonctionne reellement, une idee par scene.
- Scene {scene_count - 3} - analogie concrete :
  utilise une comparaison de la vie quotidienne pour ancrer la notion durablement.
- Scene {scene_count - 2} - exemple applique :
  donne un exemple chiffre generique et realiste (ou l'exemple de marche fourni
  si pertinent) pour montrer la notion en action.
- Scene {scene_count - 1} - synthese actionnable :
  resume en une phrase memorable ce qu'il faut retenir et faire concretement.
- Scene {scene_count} - CTA pedagogique :
  pose une question qui verifie la comprehension ou invite a partager son
  experience personnelle sur cette notion.
  Interdiction des CTA generiques comme "Abonne-toi pour plus de videos".

REGLES D'ECRITURE (RYTHME) :
- Chaque "text" contient une phrase complete de 12 a 22 mots, une seule idee principale par scene.
- Alterne systematiquement une phrase courte percutante (moins de 14 mots) et une phrase plus longue explicative.
- Cree une transition logique explicite entre chaque scene.
- Ne commence jamais par : "Aujourd'hui", "Savais-tu que", "Bienvenue", "Dans cette video".
- N'invente jamais de promesse d'enrichissement rapide ni de rendement garanti.
- Pas de hashtags, d'emojis, de titres, de notes ou d'explications hors JSON.

REGLES AUDIO :
- Chaque scene doit inclure "voice_direction" en anglais.
- Chaque scene doit inclure "pause_after_ms" avec une valeur entiere entre 180 et 450.
- Chaque scene peut inclure "tts_emphasis_word".

REGLES VISUELLES :
"stock_search" : 3 a 7 mots-cles anglais orientes finance/education.
"image_prompt" : une seule composition visuelle propre et professionnelle, verticale 9:16, espace libre en haut/bas pour sous-titres, style realiste, aucun texte ni logo.

VALEURS AUTORISEES :
- "role" : "hook", "misconception", "definition", "mechanism", "analogy", "example", "summary", "cta"
- "mood" : "confident", "sharp", "clear", "pedagogical", "engaging", "revelatory"

FORMAT DE SORTIE :
Retourne uniquement un objet JSON valide, sans bloc Markdown.

{{
  "title": "Titre francais pedagogique court et accrocheur",
  "notion_enseignee": "{notion or ''}",
  "angle": "{angle or ''}",
  "visual_identity": "One concise English sentence defining recurring clean educational visual continuity",
  "audio_profile": "French premium narrator, confident, sharp, clear, pedagogical, natural pacing",
  "compliance_note": "Contenu educatif general, ne constitue pas un conseil en investissement personnalise.",
  "scenes": [
    {{
      "id": 1,
      "text": "Phrase francaise complete de douze a vingt-deux mots.",
      "voice_direction": "French premium narrator, confident, clear, engaging",
      "pause_after_ms": 300,
      "tts_emphasis_word": "mot",
      "stock_search": "concrete English finance education stock footage keywords",
      "image_prompt": "Detailed English visual prompt for one vertical cinematic educational shot",
      "mood": "pedagogical",
      "role": "hook"
    }}
  ]
}}
"""
        messages = [
            {
                "role": "system",
                "content": (
                    "Tu produis uniquement du JSON valide. "
                    f"La cle scenes contient exactement {scene_count} scenes. "
                    "Tu respectes strictement la structure pedagogique erreur->mecanisme->analogie->application. "
                    "Aucun texte hors du JSON. "
                    f"{ACCENT_INSTRUCTION} {COMPLIANCE_INSTRUCTION} {PEDAGOGY_INSTRUCTION}"
                ),
            },
            {"role": "user", "content": prompt},
        ]

        content, provider_used = self._call_with_fallback(messages, temperature=0.7, json_mode=True)
        data = json.loads(content)

        if provider_used == "groq" and _script_missing_accents(data):
            print("⚠️ Accents manquants detectes dans le script (Groq), nouvelle tentative via Gemini...")
            content, _ = self._call_with_fallback(messages, temperature=0.7, json_mode=True, skip_providers={"groq"})
            data = json.loads(content)

        self._validate_script(data, scene_count)
        return data

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

        allowed_roles = {"hook", "misconception", "definition", "mechanism", "analogy", "example", "summary", "cta"}
        allowed_moods = {"confident", "sharp", "clear", "pedagogical", "engaging", "revelatory"}
        forbidden_phrases = [
            "achete cette action", "achete maintenant", "c'est une valeur sure",
            "rendement garanti", "gain garanti", "investis dans", "tu dois investir",
        ]

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
            if not isinstance(pause_after_ms, int) or not (180 <= pause_after_ms <= 450):
                raise ValueError(f"Scene {scene.get('id')} : pause_after_ms invalide ({pause_after_ms}).")
            if role not in allowed_roles:
                raise ValueError(f"Scene {scene.get('id')} : role invalide ({role}).")
            if mood not in allowed_moods:
                raise ValueError(f"Scene {scene.get('id')} : mood invalide ({mood}).")
            if not stock_search:
                raise ValueError(f"Scene {scene.get('id')} : stock_search manquant.")
            if not image_prompt:
                raise ValueError(f"Scene {scene.get('id')} : image_prompt manquant.")

            text_lower = text.lower()
            for phrase in forbidden_phrases:
                if phrase in text_lower:
                    print(f"⚠️ Scene {scene.get('id')} : formulation a risque de conformite detectee ('{phrase}').")

            if emphasis:
                normalized_text = text.lower()
                normalized_emphasis = str(emphasis).strip().lower()
                words = re.findall(r"[\wÀ-ÿœŒ'-]+", normalized_text)
                if normalized_emphasis not in words:
                    print(f"⚠️ Scene {scene.get('id')} : tts_emphasis_word='{emphasis}' absent du text. Emphase ignoree.")
                    scene["tts_emphasis_word"] = None

        if "title" not in data or not str(data["title"]).strip():
            raise ValueError("Titre manquant.")
        if "visual_identity" not in data or not str(data["visual_identity"]).strip():
            raise ValueError("visual_identity manquant.")
        if "audio_profile" not in data or not str(data["audio_profile"]).strip():
            raise ValueError("audio_profile manquant.")


if __name__ == "__main__":
    brain = ContentBrain()

    print("📡 Récupération des statistiques Zernio...")
    stats_historique = get_latest_videos_stats()

    print("📚 Selection d'une notion du curriculum (auto-extensible)...")
    result = brain.get_pedagogical_topic(
        previous_stats_list=stats_historique,
        market_signals=None,  # mettre get_market_signals() ici seulement si tu veux un exemple d'actu
    )
    topic = result["topic"]
    notion = result["notion"]
    niveau = result["niveau"]
    angle = result["angle"]
    pillar = result["pillar"]
    state = result["state"]

    print(f"\nPilier : {CONTENT_PILLARS.get(pillar, {}).get('label', pillar)}")
    print(f"Notion enseignee : {notion}")
    print(f"Angle : {angle}")
    print(f"Titre retenu : {topic}\n")

    hooks = brain.generate_hook_variants(topic, notion=notion, angle=angle, n=5, previous_stats_list=stats_historique)

    for i, h in enumerate(hooks, 1):
        print(f"{i}. [{h['pattern']}] {h['text']}")

    best_hook_data = brain.pick_best_hook(hooks, previous_stats_list=stats_historique)
    best_hook = best_hook_data["text"]
    print(f"\nHook choisi (pattern: {best_hook_data['pattern']}) : {best_hook}\n")

    script_data = brain.generate_script(topic, notion=notion, angle=angle, chosen_hook=best_hook)

    with open("script_finance.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=4, ensure_ascii=False)

    # IMPORTANT : n'enregistrer dans l'historique qu'apres validation/publication
    # reelle de la video, pas juste apres generation du script.
    brain.record_topic_used(state, notion, niveau, angle, pillar)

    print("Script finance saved to script_finance.json")
    print("⚠️ Relis le compliance_note et les scenes avant publication.")
