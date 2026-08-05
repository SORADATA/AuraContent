import os
import re
import json
import time
from openai import OpenAI
from dotenv import load_dotenv

try:
    from modules.utils.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Création de données factices pour le test.")
    def get_latest_videos_stats():
        return None

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc)."
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


def _script_missing_accents(script_data):
    scenes = script_data.get("scenes", [])
    if not scenes:
        return False
    full_text = " ".join(s.get("text", "") for s in scenes if isinstance(s, dict))
    return _has_missing_accents(full_text)


def _format_stats_instruction(previous_stats_list, label="hooks"):
    if not previous_stats_list:
        return ""

    stats_text = "\n".join([
        f'- Titre : "{s["title"]}" | Vues : {s["views"]} | Likes : {s["likes"]}'
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
            return OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=gemini_key)

        return None

    def _model_for(self, provider):
        return GROQ_MODEL if provider == "groq" else GEMINI_MODEL

    def _extract_content(self, response, provider):
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        if not choices:
            raise ValueError(f"Réponse inattendue du provider {provider}: {response}")

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
            raise ValueError(f"Contenu vide du provider {provider}: {response}")

        return content

    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False, skip_providers=None):
        skip_providers = skip_providers or set()
        last_error = None

        for attempt in range(2):
            for provider in ("groq", "gemini"):
                if provider in skip_providers:
                    continue

                client = self._build_client(provider)
                if client is None:
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
                    content = self._extract_content(response, provider)
                    print(f"✅ Reponse obtenue via {provider}")
                    return content, provider

                except Exception as e:
                    print(f"⚠️ Echec avec {provider} (Cycle {attempt + 1}/2): {e}")
                    last_error = e

            if attempt == 0:
                print("⏳ Micro-coupure réseau suspectée. Pause de 5s avant de tout retenter...")
                time.sleep(5)

        raise RuntimeError(f"Aucun provider disponible après 2 tentatives. Derniere erreur: {last_error}")

    def _call_json_with_retry(self, messages, temperature=1.0, max_json_retries=2, skip_providers=None):
        skip_providers = set(skip_providers or set())
        last_error = None

        for attempt in range(max_json_retries):
            content, provider_used = self._call_with_fallback(
                messages,
                temperature=temperature,
                json_mode=True,
                skip_providers=skip_providers
            )
            try:
                data = json.loads(_clean_json_response(content))
                return data, provider_used
            except json.JSONDecodeError as e:
                last_error = e
                print(f"⚠️ JSON malformé reçu (tentative {attempt + 1}/{max_json_retries}), nouvelle tentative...")

        raise ValueError(f"Impossible d'obtenir un JSON valide après {max_json_retries} tentatives : {last_error}")

    def get_trending_topic(self, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")
        messages = [
            {"role": "system", "content": f"Tu es un strategiste de contenu viral. Reponds uniquement avec un seul titre en francais, une seule ligne, sans guillemets, maximum 18 mots. {ACCENT_INSTRUCTION}"},
            {"role": "user", "content": "Donne un sujet viral totalement inédit et surprenant pour TikTok en français." + stats_instruction},
        ]

        last_topic = ""
        for attempt in range(2):
            content, _ = self._call_with_fallback(messages, temperature=0.9)
            topic = _clean_single_line_title(content)
            last_topic = topic
            if topic and 4 <= len(topic.split()) <= 18:
                return topic
            print(f"⚠️ Sujet invalide genere (tentative {attempt + 1}) : {topic}")

        raise ValueError(f"Impossible d'obtenir un sujet valide apres 2 tentatives : {last_topic}")

    def refine_topic_angle(self, raw_topic):
        messages = [
            {"role": "system", "content": f"Tu reformules le sujet en un titre accrocheur, sans changer le theme. Reponds uniquement avec le titre reformule. {ACCENT_INSTRUCTION}"},
            {"role": "user", "content": f"Sujet brut / trend repere: {raw_topic}"},
        ]
        content, _ = self._call_with_fallback(messages, temperature=0.8)
        return _clean_single_line_title(content)

    def generate_video_search_query(self, topic):
        messages = [
            {"role": "system", "content": "Tu génères une requête YouTube en anglais, 6 mots max, sans phrase. Inclure CGI, Unreal Engine 5, dark fantasy, cinematic 3D render ou mysterious atmosphere."},
            {"role": "user", "content": f"Sujet : {topic}"},
        ]
        content, _ = self._call_with_fallback(messages, temperature=0.7)
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
            {"role": "system", "content": f"Tu produis uniquement du JSON valide avec exactement {n} hooks. {ACCENT_INSTRUCTION}"},
            {"role": "user", "content": prompt},
        ]

        data, provider_used = self._call_json_with_retry(messages, temperature=1.1)

        hooks = data.get("hooks")
        if not isinstance(hooks, list):
            raise ValueError("Champ hooks invalide.")

        normalized_hooks = []
        for h in hooks:
            if isinstance(h, str):
                text = h.strip()
                if text:
                    normalized_hooks.append({"text": text, "pattern": "question", "raison": ""})
            elif isinstance(h, dict):
                text = str(h.get("text", "")).strip()
                if text:
                    normalized_hooks.append({
                        "text": text,
                        "pattern": str(h.get("pattern", "question")).strip(),
                        "raison": str(h.get("raison", "")).strip()
                    })

        if len(normalized_hooks) < n:
            raise ValueError(f"Nombre de hooks invalide: {len(normalized_hooks)} au lieu de {n}.")

        return normalized_hooks[:n]

    def generate_script(self, topic, chosen_hook=None):
        return self.generate_script_with_target(topic, scene_count=11, chosen_hook=chosen_hook)

    def generate_script_with_target(self, topic, scene_count=11, chosen_hook=None):
        hook_instruction = f'La scene 1 doit reprendre légèrement ce hook : "{chosen_hook}"' if chosen_hook else "Scene 1 hook."
        prompt = f"""
SUJET:
{topic}

GENERE EXACTEMENT {scene_count} scenes.

Retourne JSON avec:
title, visual_identity, audio_profile, scenes.
Chaque scene doit contenir:
id, text, voice_direction, pause_after_ms, stock_search, image_prompt, mood, role.
"""

        messages = [
            {"role": "system", "content": f"Tu produis uniquement du JSON valide. La cle scenes contient exactement {scene_count} scenes. {ACCENT_INSTRUCTION}"},
            {"role": "user", "content": prompt},
        ]

        data, provider_used = self._call_json_with_retry(messages, temperature=0.75)

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
                scene.setdefault("mood", "intriguing")
                scene.setdefault("role", "value")

        if provider_used == "groq" and _script_missing_accents(data):
            print("⚠️ Accents manquants detectes dans le script (Groq), nouvelle tentative via Gemini...")
            data, _ = self._call_json_with_retry(messages, temperature=0.75, skip_providers={"groq"})
            scenes = data.get("scenes", [])
            for idx, scene in enumerate(scenes, start=1):
                if isinstance(scene, dict):
                    scene.setdefault("id", idx)

        self._validate_script(data, scene_count)
        return data

    def _validate_script(self, data, scene_count):
        scenes = data.get("scenes")
        if not isinstance(scenes, list):
            raise ValueError("La reponse ne contient pas de tableau scenes.")
        if len(scenes) != scene_count:
            raise ValueError(f"Nombre de scenes invalide : {len(scenes)} au lieu de {scene_count}.")

        for idx, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                raise ValueError(f"Scene {idx} invalide.")
            scene.setdefault("id", idx)

        allowed_roles = {"hook", "tension", "context", "value", "escalation", "reveal", "cta"}
        allowed_moods = {"ominous", "intriguing", "tense", "awe", "scientific", "melancholic", "revelatory"}

        for scene in scenes:
            if not scene.get("text"):
                raise ValueError(f"Scene {scene.get('id')} : text manquant.")
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

        if not str(data.get("title", "")).strip():
            data["title"] = topic
        if not str(data.get("visual_identity", "")).strip():
            data["visual_identity"] = "Consistent cinematic vertical documentary world."
        if not str(data.get("audio_profile", "")).strip():
            data["audio_profile"] = "French premium narrator, calm, elegant, slightly deep, natural, controlled pacing"