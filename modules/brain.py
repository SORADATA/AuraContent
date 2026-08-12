import os
import re
import json
import time
from openai import OpenAI
from dotenv import load_dotenv

try:
    from modules.utils.client_http.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Création de données factices pour le test.")

    def get_latest_videos_stats():
        return None

load_dotenv()

# On utilise uniquement Groq car Gemini pose des problèmes de quota
GROQ_MODEL = "llama-3.3-70b-versatile"

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc)."
)

# === CORRECTIF : consigne anti meta-IA ===
# Empêche le LLM de faire référence à lui-même, à l'IA, à la technologie
# de génération, etc. Le sujet/script doit rester 100% centré sur le
# mystère/l'histoire racontée, jamais sur l'outil qui la produit.
NO_META_AI_INSTRUCTION = (
    "INTERDICTION ABSOLUE : ne jamais mentionner l'intelligence artificielle, "
    "l'IA, un algorithme, une technologie de generation de contenu, ou tout "
    "aspect meta concernant la creation de la video elle-meme. Le sujet et le "
    "texte doivent parler uniquement du mystere/de l'histoire reelle, jamais "
    "de l'outil ou de la methode utilisee pour le raconter."
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


# === CORRECTIF : filet de sécurité anti-IA après génération ===
# Certains mots peuvent quand même passer malgré la consigne (le LLM
# n'est jamais garanti à 100%). On les détecte et on nettoie/relance.
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

                # 🛑 Pause de sécurité pour réguler les TPM (Tokens Per Minute) et éviter le Rate Limit
                time.sleep(4)
                return content

            except Exception as e:
                print(f"⚠️ Echec avec Groq (Tentative {attempt + 1}/3): {e}")
                last_error = e
                # Pause prolongée en cas d'erreur de connexion / surcharge
                time.sleep(8)

        raise RuntimeError(f"Erreur critique Groq après 3 tentatives. Dernière erreur: {last_error}")

    def _call_json_with_retry(self, messages, temperature=1.0, max_json_retries=2):
        last_error = None

        for attempt in range(max_json_retries):
            content = self._call_with_fallback(
                messages,
                temperature=temperature,
                json_mode=True
            )
            try:
                data = json.loads(_clean_json_response(content))
                return data
            except json.JSONDecodeError as e:
                last_error = e
                print(f"⚠️ JSON malformé reçu (tentative {attempt + 1}/{max_json_retries}), nouvelle tentative...")

        raise ValueError(f"Impossible d'obtenir un JSON valide après {max_json_retries} tentatives : {last_error}")

    def get_trending_topic(self, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")
        messages = [
            {"role": "system", "content": (
                "Tu es un strategiste de contenu viral. Reponds uniquement avec un seul titre "
                "en francais, une seule ligne, sans guillemets, maximum 18 mots. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION}"
            )},
            {"role": "user", "content": (
                "Donne un sujet viral totalement inédit et surprenant pour TikTok en français, "
                "portant sur un mystere, un lieu ou un fait historique reel."
                + stats_instruction
            )},
        ]

        last_topic = ""
        # CORRECTIF : on passe de 2 à 3 tentatives pour laisser une marge
        # supplémentaire si le filtre anti-IA rejette une génération.
        for attempt in range(3):
            content = self._call_with_fallback(messages, temperature=0.9)
            topic = _clean_single_line_title(content)
            last_topic = topic

            if _contains_ai_mention(topic):
                print(f"⚠️ Sujet rejeté (mention IA détectée, tentative {attempt + 1}) : {topic}")
                continue

            if topic and 4 <= len(topic.split()) <= 18:
                return topic
            print(f"⚠️ Sujet invalide genere (tentative {attempt + 1}) : {topic}")

        raise ValueError(f"Impossible d'obtenir un sujet valide apres 3 tentatives : {last_topic}")

    def refine_topic_angle(self, raw_topic):
        messages = [
            {"role": "system", "content": (
                "Tu reformules le sujet en un titre accrocheur, sans changer le theme. "
                f"Reponds uniquement avec le titre reformule. {ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION}"
            )},
            {"role": "user", "content": f"Sujet brut / trend repere: {raw_topic}"},
        ]
        content = self._call_with_fallback(messages, temperature=0.8)
        refined = _clean_single_line_title(content)

        # CORRECTIF : si la reformulation introduit une mention IA, on garde le sujet brut.
        if _contains_ai_mention(refined):
            print(f"⚠️ Reformulation rejetée (mention IA détectée) : {refined} → on garde le sujet brut.")
            return _clean_single_line_title(raw_topic)

        return refined

    def generate_video_search_query(self, topic):
        messages = [
            {"role": "system", "content": "Tu génères une requête de recherche visuelle en anglais, 6 mots max, sans phrase. Inclure des termes comme photorealistic, historical documentary, real photography, dark mysterious atmosphere. INTERDICTION ABSOLUE d'utiliser les mots CGI, 3D, render ou Unreal Engine."},
            {"role": "user", "content": f"Sujet : {topic}"},
        ]
        content = self._call_with_fallback(messages, temperature=0.7)
        return _clean_single_line_title(content).replace('"', '')

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
                f"Tu produis uniquement du JSON valide avec exactement {n} hooks. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION}"
            )},
            {"role": "user", "content": prompt},
        ]

        data = self._call_json_with_retry(messages, temperature=1.1)

        hooks = data.get("hooks")
        if not isinstance(hooks, list):
            raise ValueError("Champ hooks invalide.")

        normalized_hooks = []
        for h in hooks:
            if isinstance(h, str):
                text = h.strip()
                # CORRECTIF : on filtre les hooks qui mentionnent l'IA malgré la consigne
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

        if len(normalized_hooks) < n:
            raise ValueError(f"Nombre de hooks invalide: {len(normalized_hooks)} au lieu de {n}.")

        normalized_hooks = normalized_hooks[:n]
        if not normalized_hooks:
            normalized_hooks = [{"text": topic, "pattern": "default", "raison": ""}]
        return normalized_hooks

    def generate_script(self, topic, chosen_hook=None):
        return self.generate_script_with_target(topic, scene_count=11, chosen_hook=chosen_hook)

    def generate_script_with_target(self, topic, scene_count=11, chosen_hook=None):
        hook_instruction = f'La scene 1 doit reprendre ce hook : "{chosen_hook}"' if chosen_hook else "Scene 1: Accroche choc."

        prompt = f"""
SUJET:
{topic}

{hook_instruction}

REGLES STRICTES DE NARRATION ET VISUEL (POUR ÉVITER LES INTROS VIDES ET LA 3D) :
1. Interdiction de faire de longs discours d'introduction ou des bandes-annonces vides ("Nous allons vous raconter...").
2. Dès la scène 2, entre DIRECTEMENT dans le vif du sujet en racontant de vrais faits historiques, des détails précis ou une anecdote concrète et surprenante.
3. Le milieu de la vidéo doit développer l'histoire en profondeur (les faits, les mystères, les rebondissements).
4. Les dernières scènes doivent apporter une conclusion claire ou une révélation, pas s'arrêter en plein milieu.
5. Pour la clé 'image_prompt', décris des décors sous forme de photographies réelles, style documentaire historique, ambiance sombre et mystérieuse. Interdiction formelle d'utiliser des termes liés à la synthèse (CGI, Unreal Engine, 3D render).
6. Si la scène se déroule dans un vrai lieu en France (monument, ville, château, île, etc.), donne le nom précis dans 'location_name' (ex: "Château de Chambord", "Île de Saint-Cado"). Si c'est juste de l'ambiance ou abstrait, laisse vide ("").
7. Pour la clé 'voice_type', choisis "narrator" pour l'ambiance globale/les faits, ou "witness" pour dynamiser (citations, avis, phrases choc). Alterne intelligemment pour garder l'audience captivée.
8. Interdiction absolue de mentionner l'intelligence artificielle, l'IA, un algorithme, ou tout aspect meta lié a la creation de la video. Chaque scene doit parler uniquement du mystere/de l'histoire reelle, jamais de la maniere dont la video a ete produite.

GENERE EXACTEMENT {scene_count} scenes.

Retourne un JSON avec les clés :
title, visual_identity, audio_profile, scenes.
Chaque scene dans le tableau 'scenes' doit contenir :
id, text, voice_direction, pause_after_ms, stock_search, image_prompt, location_name, voice_type, mood, role.
"""

        messages = [
            {"role": "system", "content": (
                f"Tu produis uniquement du JSON valide. La cle scenes contient exactement {scene_count} scenes. "
                f"{ACCENT_INSTRUCTION} {NO_META_AI_INSTRUCTION}"
            )},
            {"role": "user", "content": prompt},
        ]

        data = self._call_json_with_retry(messages, temperature=0.7)

        scenes = data.get("scenes", [])
        if not isinstance(scenes, list):
            raise ValueError("La reponse ne contient pas de tableau scenes.")

        for idx, scene in enumerate(scenes, start=1):
            if isinstance(scene, dict):
                scene.setdefault("id", idx)
                scene.setdefault("voice_direction", "French premium narrator, calm, elegant, intriguing, controlled pacing")
                scene.setdefault("pause_after_ms", 300)
                scene.setdefault("stock_search", "cinematic vertical background")
                scene.setdefault("image_prompt", "Vertical 9:16 cinematic scene")
                scene.setdefault("location_name", "")
                scene.setdefault("voice_type", "narrator")  # Valeur par défaut
                scene.setdefault("mood", "intriguing")
                scene.setdefault("role", "value")

        self._validate_script(data, scene_count, topic)
        return data

    def _validate_script(self, data, scene_count, topic):
        scenes = data.get("scenes")
        if not isinstance(scenes, list):
            raise ValueError("La reponse ne contient pas de tableau scenes.")
        if len(scenes) != scene_count:
            raise ValueError(f"Nombre de scenes invalide : {len(scenes)} au lieu de {scene_count}.")

        allowed_roles = {"hook", "tension", "context", "value", "escalation", "reveal", "cta"}
        allowed_moods = {"ominous", "intriguing", "tense", "awe", "scientific", "melancholic", "revelatory"}

        for scene in scenes:
            if not isinstance(scene, dict):
                raise ValueError("Une scène n'est pas un dictionnaire valide.")
            if not scene.get("text"):
                raise ValueError(f"Scene {scene.get('id')} : text manquant.")

            # CORRECTIF : on nettoie/rejette toute scène qui a quand même glissé
            # une mention d'IA malgré les consignes du prompt.
            if _contains_ai_mention(scene.get("text", "")):
                raise ValueError(
                    f"Scene {scene.get('id')} : mention d'IA/technologie detectee dans le texte "
                    f"('{scene['text'][:80]}...'), regeneration necessaire."
                )

            if not scene.get("voice_direction"):
                scene["voice_direction"] = "French premium narrator, calm, elegant, intriguing, controlled pacing"
            pause_after_ms = scene.get("pause_after_ms")
            if not isinstance(pause_after_ms, int):
                scene["pause_after_ms"] = 300
            if scene.get("role") not in allowed_roles:
                scene["role"] = "value"
            if scene.get("mood") not in allowed_moods:
                scene["mood"] = "intriguing"
            if not scene.get("stock_search"):
                scene["stock_search"] = "cinematic vertical background"
            if not scene.get("image_prompt"):
                scene["image_prompt"] = "Vertical 9:16 cinematic scene"
            if "location_name" not in scene:
                scene["location_name"] = ""
            if scene.get("voice_type") not in {"narrator", "witness"}:
                scene["voice_type"] = "narrator"

        if not str(data.get("title", "")).strip():
            data["title"] = topic
        if not str(data.get("visual_identity", "")).strip():
            data["visual_identity"] = "Consistent cinematic vertical documentary world."
        if not str(data.get("audio_profile", "")).strip():
            data["audio_profile"] = "French premium narrator, calm, elegant, slightly deep, natural, controlled pacing"
