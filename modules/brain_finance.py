import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

print("⚠️ Zernio désactivé. L'Agent IA va travailler sans historique pour le moment.")

def get_latest_videos_stats():
    return None

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash"

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc). Exemples obligatoires : 'épargne' "
    "(jamais 'epargne'), 'intérêt' (jamais 'interet'), 'stratégie' "
    "(jamais 'strategie'), 'inflation' (jamais 'inflation'), 'bénéfice' "
    "(jamais 'benefice'), 'argent' (jamais 'argent'). Verifie chaque mot avant de repondre."
)


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
Agis comme un Growth Hacker financier. Analyse brievement quels themes ou structures ont obtenu le plus ou le moins de vues.
Sers-toi de cette deduction pour ajuster le {label} que tu vas generer.
"""

def _clean_single_line_title(text):
    if not text:
        return ""

    cleaned = text.replace('"', '').replace('“', '').replace('”', '').strip()
    lines = [line.strip(' -•\t') for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""

    first_line = lines[0]
    first_line = re.sub(r"\s+", " ", first_line).strip()
    return first_line

def _is_valid_topic_candidate(topic):
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

    return True

class ContentBrain:
    def _build_client(self, provider):
        if provider == "groq":
            groq_key = os.getenv("GROQ_API_KEY")
            if not groq_key:
                return None
            return OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key
            )

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

    def get_trending_topic(self, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")

        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es un strategiste de contenu financier viral. "
                    "Trouve un sujet d'éducation financière percutant, axé sur les secrets des banques, "
                    "l'anti-inflation, la bourse ou l'optimisation d'argent pour les jeunes et débutants. "
                    "Reponds UNIQUEMENT avec un seul titre en francais, sur UNE seule ligne, "
                    "sans guillemets, sans liste, sans justification, sans deuxieme proposition. "
                    "Maximum 18 mots. "
                    f"{ACCENT_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": (
                    "Donne un sujet financier viral, secret ou contre-intuitif totalement inédit pour TikTok en français."
                    + stats_instruction
                )
            }
        ]

        last_topic = ""
        for attempt in range(2):
            content, _ = self._call_with_fallback(messages, temperature=0.9)
            topic = _clean_single_line_title(content)
            last_topic = topic

            if _is_valid_topic_candidate(topic):
                return topic

            print(f"⚠️ Sujet invalide genere (tentative {attempt + 1}) : {topic}")

        raise ValueError(f"Impossible d'obtenir un sujet valide apres 2 tentatives : {last_topic}")

    def refine_topic_angle(self, raw_topic):
        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es un strategiste de contenu financier viral. "
                    "Reformule le sujet en un titre accrocheur axé sur l'argent ou l'investissement, sans changer le theme. "
                    "Reponds UNIQUEMENT avec le titre reformule. "
                    f"{ACCENT_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": f"Sujet brut / trend repere: {raw_topic}"
            }
        ]
        content, _ = self._call_with_fallback(messages, temperature=0.8)
        return content.strip().replace(chr(34), "")

    def generate_hook_variants(self, topic, n=5, previous_stats_list=None):
        print(f"Generation de {n} hooks alternatifs pour: {topic}...")

        stats_instruction = _format_stats_instruction(previous_stats_list, label="le niveau d'impact, la promesse financière ou la structure des nouveaux hooks")

        prompt = f"""
Tu es un expert en hooks viraux pour TikTok, specialise dans l'éducation financière percutante et les secrets d'argent qu'on cache aux débutants.

{stats_instruction}

SUJET :
{topic}

OBJECTIF :
Genere {n} hooks differents pour la meme video. Chaque hook doit arreter le scroll
en moins de 3 secondes et creer une promesse de valeur ou un choc financier.

REGLES POUR CHAQUE HOOK :
- 12 a 18 mots, phrase complete en francais oral et naturel.
- Combine un fait financier concret (chiffre, taux, livret, erreur d'argent) AVEC une promesse forte
  ou une révélation (ce que les banques cachent, comment devenir riche jeune, doubler son épargne).
- Varie les patterns de viralite: question directe, statistique choc, confession
  personnelle d'investissement, contre-intuition, mise en garde bancaire.
- N'utilise jamais "Aujourd'hui", "Savais-tu que", "Bienvenue", "Dans cette video".
- N'invente ni dates, ni chiffres impossibles.
- {ACCENT_INSTRUCTION}

FORMAT DE SORTIE :
Retourne uniquement un objet JSON valide, sans bloc Markdown.

{{
  "analyse_agent": "Une phrase courte (max 20 mots) expliquant comment tu as adapte tes hooks en fonction des stats fournies.",
  "hooks": [
    {{
      "text": "Phrase du hook.",
      "pattern": "question | statistique | confession | contre-intuition | mise_en_garde",
      "raison": "Une phrase expliquant pourquoi ce hook capte l'attention financièrement."
    }}
  ]
}}
"""
        messages = [
            {
                "role": "system",
                "content": f"Tu produis uniquement du JSON valide avec exactement {n} hooks financiers. {ACCENT_INSTRUCTION}"
            },
            {
                "role": "user",
                "content": prompt
            },
        ]

        content, provider_used = self._call_with_fallback(
            messages,
            temperature=1.1,
            json_mode=True
        )
        data = json.loads(content)

        if provider_used == "groq" and _script_missing_accents({
            "scenes": [{"text": h.get("text", "")} for h in data.get("hooks", [])]
        }):
            print("⚠️ Accents manquants detectes (Groq), nouvelle tentative via Gemini...")
            content, _ = self._call_with_fallback(
                messages,
                temperature=1.1,
                json_mode=True,
                skip_providers={"groq"}
            )
            data = json.loads(content)

        analyse = data.get("analyse_agent", "")
        if analyse:
            print(f"\n🧠 Réflexion de l'Agent IA : {analyse}\n")

        hooks = data.get("hooks")
        if not isinstance(hooks, list) or len(hooks) != n:
            raise ValueError(
                f"Nombre de hooks invalide: {len(hooks) if isinstance(hooks, list) else 0} au lieu de {n}."
            )

        return hooks

    def generate_script(self, topic, chosen_hook=None):
        return self.generate_script_with_target(topic, scene_count=11, chosen_hook=chosen_hook)

    def generate_script_with_target(self, topic, scene_count=11, chosen_hook=None):
        if scene_count < 6:
            raise ValueError("scene_count doit etre superieur ou egal a 6.")

        print(f"Ecriture du script de finance en francais pour : {topic} ({scene_count} scenes)...")

        hook_instruction = (
            f'La scene 1 doit reprendre exactement ou reformuler tres legerement ce hook deja valide : "{chosen_hook}"'
            if chosen_hook else
            "Scene 1 - hook : une phrase de 12 a 18 mots combinant une réalité financière choqueante ou un secret d'argent. Cree une promesse résolue avant la fin."
        )

        prompt = f"""
Tu es redacteur en chef d'une chaine francophone d'éducation financière moderne, axée sur les secrets des banques, l'anti-inflation, l'investissement intelligent et la liberté financière pour les débutants.

SUJET :
{topic}

OBJECTIF :
Creer une video TikTok, Reels ou Shorts captivante, ultra-actionnable, credible, facile a
illustrer, et optimisee pour une narration vocale premium.

CONTRAINTE ABSOLUE :
Genere exactement {scene_count} scenes.

LANGUES :
- "text" : uniquement en francais naturel et oral, PARFAITEMENT ACCENTUE.
- "voice_direction" : uniquement en anglais, courte instruction premium pour guider un moteur TTS.
- "stock_search" : uniquement en anglais, mots-cles concrets orientés finance/bourse/bureau/argent.
- "image_prompt" : uniquement en anglais.
- "mood" et "role" : uniquement parmi les valeurs autorisees.

{ACCENT_INSTRUCTION}

STRUCTURE NARRATIVE FINANCIERE :
- {hook_instruction}
- Scene 2 - tension :
  explique le piège classique ou l'erreur que tout le monde fait (ex: laisser l'argent sur un livret A).
- Scene 3 - contexte :
  pose les chiffres réels ou la règle du système financier actuel.
- Scenes 4 a {scene_count - 3} - stratégie / action :
  donne un tuyau précis par scene (bourse, intérêts composés, automatisation, immobilier, ETF). Chaque scene apporte une vraie valeur actionnable.
- Scene {scene_count - 2} - escalade :
  montre pourquoi ceux qui n'agissent pas perdent du pouvoir d'achat face à l'inflation.
- Scene {scene_count - 1} - revelation :
  donne la solution finale ou l'action exacte à poser dès aujourd'hui pour inverser la tendance.
- Scene {scene_count} - CTA polarisant :
  pose une question ou affirmation financière qui divise ou pousse à commenter (ex: "Tu penses vraiment que ton banquier veut ton bien ? Dis-le-moi en commentaire.").
  Interdiction des CTA generiques comme "Abonne-toi pour plus de videos".

REGLES D'ECRITURE (RYTHME) :
- Chaque "text" contient une phrase complete de 12 a 22 mots, une seule idee principale par scene.
- Alterne systematiquement une phrase courte percutante (moins de 14 mots) et une phrase plus longue explicative.
- Cree une transition logique explicite entre chaque scene.
- Ne commence jamais par : "Aujourd'hui", "Savais-tu que", "Bienvenue", "Dans cette video".
- N'invente pas de promesses illégales d'enrichissement rapide sans effort, reste sur de l'éducation financière solide et maligne.
- Pas de hashtags, d'emojis, de titres, de notes ou d'explications.

REGLES AUDIO :
- Chaque scene doit inclure "voice_direction" en anglais.
- "voice_direction" decrit comment un narrateur premium francais doit lire la phrase (ex: confident, sharp, professional, persuasive, engaging).
- Chaque scene doit inclure "pause_after_ms" avec une valeur entiere entre 180 et 450.
- Chaque scene peut inclure "tts_emphasis_word".

REGLES VISUELLES :
Chaque scene doit etre comprehensible a partir de son image ou de sa video de stock (ambiances de bureau, ordinateurs avec graphiques, applications bancaires propres, pièces, portefeuilles, trading propre, style minimaliste).

"stock_search" :
- Entre 3 et 7 mots-cles anglais, orientés finance (ex: "person looking at smartphone stock market app", "saving money coin piggy bank", "modern clean office laptop charts").

"image_prompt" :
- Decrit une seule composition visuelle propre et professionnelle.
- Composition verticale 9:16, espace libre en haut et en bas pour les sous-titres.
- Style cinematographique realiste, eclairage soigné, aucun texte ni logo.

VALEURS AUTORISEES :
- "role" : "hook", "tension", "context", "value", "escalation", "reveal", "cta"
- "mood" : "confident", "sharp", "persuasive", "engaging", "scientific", "revelatory"

FORMAT DE SORTIE :
Retourne uniquement un objet JSON valide, sans bloc Markdown.

{{
  "title": "Titre francais financier court et percutant",
  "visual_identity": "One concise English sentence defining recurring clean financial visual continuity",
  "audio_profile": "French premium narrator, confident, sharp, professional, persuasive, natural pacing",
  "scenes": [
    {{
      "id": 1,
      "text": "Phrase francaise complete de douze a vingt-deux mots.",
      "voice_direction": "French premium narrator, confident, sharp, engaging",
      "pause_after_ms": 300,
      "tts_emphasis_word": "mot",
      "stock_search": "concrete English finance stock footage keywords",
      "image_prompt": "Detailed English visual prompt for one vertical cinematic financial shot",
      "mood": "persuasive",
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
                    "Tu respectes strictement les regles d'education financière, les rôles, et le CTA polarisant. "
                    "Aucun texte hors du JSON. "
                    f"{ACCENT_INSTRUCTION}"
                ),
            },
            {
                "role": "user",
                "content": prompt
            },
        ]

        content, provider_used = self._call_with_fallback(
            messages,
            temperature=0.75,
            json_mode=True
        )
        data = json.loads(content)

        if provider_used == "groq" and _script_missing_accents(data):
            print("⚠️ Accents manquants detectes dans le script (Groq), nouvelle tentative via Gemini...")
            content, _ = self._call_with_fallback(
                messages,
                temperature=0.75,
                json_mode=True,
                skip_providers={"groq"}
            )
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

        allowed_roles = {"hook", "tension", "context", "value", "escalation", "reveal", "cta"}
        allowed_moods = {"confident", "sharp", "persuasive", "engaging", "scientific", "revelatory"}

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

            if emphasis:
                normalized_text = text.lower()
                normalized_emphasis = str(emphasis).strip().lower()

                words = re.findall(r"[\wÀ-ÿœŒ'-]+", normalized_text)

                if normalized_emphasis not in words:
                    print(
                        f"⚠️ Scene {scene.get('id')} : "
                        f"tts_emphasis_word='{emphasis}' absent du text. Emphase ignoree."
                    )
                    scene["tts_emphasis_word"] = None

        if "title" not in data or not str(data["title"]).strip():
            raise ValueError("Titre manquant.")
        if "visual_identity" not in data or not str(data["visual_identity"]).strip():
            raise ValueError("visual_identity manquant.")
        if "audio_profile" not in data or not str(data["audio_profile"]).strip():
            raise ValueError("audio_profile manquant.")


if __name__ == "__main__":
    brain = ContentBrain()

    print("📡 Récupération des statistiques Zernio pour l'Agent Finance...")
    stats_historique = get_latest_videos_stats()

    topic = brain.get_trending_topic(previous_stats_list=stats_historique)
    print(f"\nSujet financier retenu : {topic}\n")

    hooks = brain.generate_hook_variants(topic, n=5, previous_stats_list=stats_historique)

    for i, h in enumerate(hooks, 1):
        print(f"{i}. [{h['pattern']}] {h['text']}")

    best_hook = hooks[0]["text"]
    print(f"\nHook choisi : {best_hook}\n")

    script_data = brain.generate_script(topic, chosen_hook=best_hook)

    with open("script_finance.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=4, ensure_ascii=False)

    print("Script finance saved to script_finance.json")
