import os
import re
import json
import time  # 🛠️ AJOUT : Nécessaire pour la pause réseau
from openai import OpenAI
from dotenv import load_dotenv

try:
    from modules.utils.zernio_client import get_latest_videos_stats
except ImportError:
    print("⚠️ Module zernio_client introuvable. Création de données factices pour le test.")
    def get_latest_videos_stats(): return None

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
# Modèle plus stable et 100% compatible
GEMINI_MODEL = "gemini-1.5-flash"

ACCENTED_CHARS = "éèêëàâäùûüçîïôœ"

ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc). Exemples obligatoires : 'découvert' "
    "(jamais 'decouvert'), 'secrètes' (jamais 'secretes'), 'exploré' "
    "(jamais 'explore'), 'phénomène' (jamais 'phenomene'), 'révélation' "
    "(jamais 'revelation'), 'étrange' (jamais 'etrange'), 'théorie' "
    "(jamais 'theorie'). Verifie chaque mot avant de repondre."
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
Agis comme un Growth Hacker. Analyse brievement quels themes ou structures ont obtenu le plus ou le moins de vues.
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


def _clean_json_response(content):
    """
    Retire les eventuelles fences Markdown (```json ... ```) que le modele
    ajoute parfois malgre la consigne demandant du JSON brut.
    """
    if not content:
        return content

    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


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

    # 🛠️ CORRECTION : Fonction mise à jour avec boucle de retry et pause réseau
    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False, skip_providers=None):
        skip_providers = skip_providers or set()
        last_error = None
        max_retries = 2

        for attempt in range(max_retries):
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
                    print(f"✅ Reponse obtenue via {provider}")
                    return response.choices[0].message.content, provider

                except Exception as e:
                    print(f"⚠️ Echec avec {provider} (Cycle {attempt+1}/{max_retries}): {e}")
                    last_error = e
                    continue  # On passe au provider suivant

            # Si on arrive ici, c'est que Groq ET Gemini ont échoué
            if attempt < max_retries - 1:
                print("⏳ Micro-coupure réseau suspectée. Pause de 5s avant de tout retenter...")
                time.sleep(5)

        # Si même après les pauses tout échoue, on lève l'erreur
        raise RuntimeError(f"Aucun provider disponible après {max_retries} tentatives. Derniere erreur: {last_error}")

    def _call_json_with_retry(self, messages, temperature=1.0, max_json_retries=2, skip_providers=None):
        """
        Appelle le LLM en mode JSON, nettoie les eventuelles fences Markdown,
        et retente (avec un nouveau provider si possible) en cas de JSON
        malforme, plutot que de laisser un JSONDecodeError remonter brut.
        Retourne (data, provider_used).
        """
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
                continue

        raise ValueError(f"Impossible d'obtenir un JSON valide après {max_json_retries} tentatives : {last_error}")

    def get_trending_topic(self, previous_stats_list=None):
        stats_instruction = _format_stats_instruction(previous_stats_list, label="sujet")

        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es un strategiste de contenu viral. "
                    "Trouve un sujet de mini-documentaire court, captivant et inattendu. "
                    "Reponds UNIQUEMENT avec un seul titre en francais, sur UNE seule ligne, "
                    "sans guillemets, sans liste, sans justification, sans deuxieme proposition. "
                    "Maximum 18 mots. "
                    f"{ACCENT_INSTRUCTION}"
                )
            },
            {
                "role": "user",
                "content": (
                    "Donne un sujet viral totalement inédit et surprenant pour TikTok en français."
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
                    "Tu es un strategiste de contenu viral. "
                    "Reformule le sujet en un titre accrocheur, sans changer le theme. "
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
        # 🛠️ On reutilise le meme nettoyage que get_trending_topic pour eviter
        # de recuperer un bloc multi-lignes (justification + titre) au lieu du titre seul.
        return _clean_single_line_title(content)

    def generate_video_search_query(self, topic):
        """
        Demande à l'IA d'adapter le sujet en mots-clés de recherche vidéo
        optimisés pour YouTube (en anglais, format CGI / Unreal Engine / Cinematic).
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es un expert en recherche de vidéos cinématiques pour TikTok. "
                    "À partir du sujet fourni, génère une requête de recherche YouTube en anglais "
                    "pour trouver un fond visuel spectaculaire. "
                    "Tu DOIS obligatoirement inclure des termes comme 'CGI', 'Unreal Engine 5', "
                    "'dark fantasy', 'cinematic 3D render', 'vertical 9:16' ou 'mysterious atmosphere' "
                    "pour cibler des vidéos ultra-esthétiques et immersives (style shorts mystère). "
                    "Réponds UNIQUEMENT avec les mots-clés (6 mots maximum), sans guillemets, sans phrase."
                )
            },
            {
                "role": "user",
                "content": f"Sujet : {topic}"
            }
        ]
        content, _ = self._call_with_fallback(messages, temperature=0.7)
        return _clean_single_line_title(content).replace('"', '')

    def generate_hook_variants(self, topic, n=5, previous_stats_list=None):
        print(f"Generation de {n} hooks alternatifs pour: {topic}...")

        stats_instruction = _format_stats_instruction(previous_stats_list, label="niveau de mystere, le vocabulaire ou la structure des nouveaux hooks")

        prompt = f"""
Tu es un expert en hooks viraux pour TikTok, specialise dans le mystere et l'inexplique.

{stats_instruction}

SUJET :
{topic}

OBJECTIF :
Genere {n} hooks differents pour la meme histoire. Chaque hook doit arreter le scroll
en moins de 3 secondes et creer une promesse de resolution.

REGLES POUR CHAQUE HOOK :
- 12 a 18 mots, phrase complete en francais oral et naturel.
- Combine un fait concret (chiffre, lieu, date, anomalie) AVEC une ancre sensorielle
  ou emotionnelle (un son entendu, une image vue, une sensation, une confession
  a la premiere personne).
- Varie les patterns de viralite: question directe, statistique choc, confession
  personnelle, contre-intuition, mise en garde.
- N'utilise jamais "Aujourd'hui", "Savais-tu que", "Bienvenue", "Dans cette video".
- N'invente ni dates, ni chiffres, ni noms precis non verifiables.
- {ACCENT_INSTRUCTION}

FORMAT DE SORTIE :
Retourne uniquement un objet JSON valide, sans bloc Markdown.

{{
  "analyse_agent": "Une phrase courte (max 20 mots) expliquant comment tu as adapte tes hooks en fonction des stats fournies.",
  "hooks": [
    {{
      "text": "Phrase du hook.",
      "pattern": "question | statistique | confession | contre-intuition | mise_en_garde",
      "raison": "Une phrase expliquant pourquoi ce hook capte l'attention psychologiquement."
    }}
  ]
}}
"""
        messages = [
            {
                "role": "system",
                "content": f"Tu produis uniquement du JSON valide avec exactement {n} hooks. {ACCENT_INSTRUCTION}"
            },
            {
                "role": "user",
                "content": prompt
            },
        ]

        data, provider_used = self._call_json_with_retry(messages, temperature=1.1)

        if provider_used == "groq" and _script_missing_accents({
            "scenes": [{"text": h.get("text", "")} for h in data.get("hooks", [])]
        }):
            print("⚠️ Accents manquants detectes (Groq), nouvelle tentative via Gemini...")
            data, _ = self._call_json_with_retry(
                messages,
                temperature=1.1,
                skip_providers={"groq"}
            )

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

        print(f"Ecriture du script en francais pour : {topic} ({scene_count} scenes)...")

        hook_instruction = (
            f'La scene 1 doit reprendre exactement ou reformuler tres legerement ce hook deja valide : "{chosen_hook}"'
            if chosen_hook else
            "Scene 1 - hook : une phrase de 12 a 18 mots combinant un fait concret ET une ancre "
            "sensorielle ou emotionnelle (son, image, sensation, confession). Cree une promesse "
            "qui sera resolue dans l'avant-derniere scene."
        )

        prompt = f"""
Tu es scenariste en chef d'une chaine francophone de mini-documentaires
verticaux consacree aux mysteres, decouvertes, phenomenes inexpliques,
lieux oublies, sciences etranges et evenements historiques surprenants.

SUJET :
{topic}

OBJECTIF :
Creer une video TikTok, Reels ou Shorts captivante, credible, facile a
illustrer, et optimisee pour une narration vocale premium.

CONTRAINTE ABSOLUE :
Genere exactement {scene_count} scenes.

LANGUES :
- "text" : uniquement en francais naturel et oral, PARFAITEMENT ACCENTUE.
- "voice_direction" : uniquement en anglais, courte instruction premium pour guider un moteur TTS.
- "stock_search" : uniquement en anglais, mots-cles concrets.
- "image_prompt" : uniquement en anglais.
- "mood" et "role" : uniquement parmi les valeurs autorisees.

{ACCENT_INSTRUCTION}

STRUCTURE NARRATIVE :
- {hook_instruction}
- Scene 2 - tension :
  Explique pourquoi ce mystere est etrange, important ou difficile a expliquer.
- Scene 3 - contexte :
  Situe clairement l'epoque, le lieu ou les personnes concernees.
- Scenes 4 a {scene_count - 3} - enquete :
  Un nouvel indice, mecanisme, temoignage ou hypothese par scene. Chaque scene
  doit ajouter une tension nouvelle, jamais une simple repetition du fait precedent.
- Scene {scene_count - 2} - escalade :
  Presente l'indice le plus troublant ou l'explication qui semblait evidente
  et qui s'effondre.
- Scene {scene_count - 1} - revelation :
  Resous la promesse du hook avec la conclusion la plus credible. Si le sujet
  reste debattu, distingue clairement les faits des hypotheses.
- Scene {scene_count} - CTA polarisant :
  Pose une question ou affirmation qui divise volontairement l'audience en deux
  camps sur le mystere.
  Interdiction des CTA generiques comme "Abonne-toi pour plus de videos".

REGLES D'ECRITURE (RYTHME) :
- Chaque "text" contient une phrase complete de 12 a 22 mots, une seule idee
  principale par scene.
- Alterne systematiquement une phrase courte percutante (moins de 14 mots) et
  une phrase plus longue explicative, pour creer un rythme oral naturel.
- Une fois le texte de la scene ecrit, retire mentalement tout mot ou groupe de
  mots qui n'ajoute pas d'information ou de tension avant de le finaliser.
- Cree une transition logique explicite entre chaque scene.
- Ne commence jamais par : "Aujourd'hui", "Savais-tu que", "Bienvenue",
  "Dans cette video".
- Ne presente jamais une legende ou une hypothese comme un fait etabli.
- N'invente ni dates, ni chiffres, ni citations, ni noms de chercheurs.
- Pas de hashtags, d'emojis, de titres, de notes ou d'explications.

REGLES AUDIO :
- Chaque scene doit inclure "voice_direction" en anglais.
- "voice_direction" decrit comment un narrateur premium francais doit lire la phrase.
- Le rendu doit etre naturel, professionnel, elegant, clair, jamais caricatural.
- Autorise seulement de legeres nuances comme : intriguing, tense, revelatory, scientific, melancholic.
- Chaque scene doit inclure "pause_after_ms" avec une valeur entiere entre 180 et 450.
- Chaque scene peut inclure "tts_emphasis_word".
- Si "tts_emphasis_word" est present, il doit etre un mot exact du champ "text".
- "voice_direction" doit rester courte, utile, stable et compatible avec un moteur TTS premium.
- Exemple valide :
  "French premium narrator, calm, elegant, slightly deep, intriguing, controlled pacing"

REGLES VISUELLES :
Chaque scene doit etre comprehensible a partir de son image seule.

"stock_search" :
- Entre 3 et 7 mots-cles anglais, sujet reellement trouvable dans une banque
  de videos.
- Pas de termes abstraits comme "mystery", "truth" ou "secret" seuls.

"image_prompt" :
- Decrit une seule composition visuelle, pas une succession d'actions.
- Commence par le sujet principal concret, puis action ou etat, environnement,
  epoque si necessaire, cadrage, lumiere, ambiance et details utiles.
- Composition verticale 9:16, sujet principal dans la zone centrale.
- Prevoir de l'espace libre en haut et en bas pour les sous-titres.
- Style cinematographique realiste de mini-documentaire.
- Aucun texte, logo, filigrane, interface ou sous-titre dans l'image.
- Evite le gore et les visages deformes.
- Conserve la continuite des lieux, objets et personnages recurrents.
- N'utilise pas "Pixar", "Disney" ou le nom d'un artiste.

VALEURS AUTORISEES :
- "role" : "hook", "tension", "context", "value", "escalation", "reveal", "cta"
- "mood" : "ominous", "intriguing", "tense", "awe", "scientific", "melancholic", "revelatory"

FORMAT DE SORTIE :
Retourne uniquement un objet JSON valide, sans bloc Markdown.

{{
  "title": "Titre francais court et intrigant",
  "visual_identity": "One concise English sentence defining recurring visual continuity",
  "audio_profile": "French premium narrator, calm, elegant, slightly deep, natural, controlled pacing",
  "scenes": [
    {{
      "id": 1,
      "text": "Phrase francaise complete de douze a vingt-deux mots.",
      "voice_direction": "French premium narrator, calm, elegant, intriguing, controlled pacing",
      "pause_after_ms": 300,
      "tts_emphasis_word": "mot",
      "stock_search": "concrete English stock footage keywords",
      "image_prompt": "Detailed English visual prompt for one vertical cinematic shot",
      "mood": "ominous",
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
                    "Tu respectes strictement les langues, roles, longueurs, "
                    "le rythme alterne, les champs audio et le CTA polarisant. "
                    "Aucun texte hors du JSON. "
                    f"{ACCENT_INSTRUCTION}"
                ),
            },
            {
                "role": "user",
                "content": prompt
            },
        ]

        data, provider_used = self._call_json_with_retry(messages, temperature=0.75)

        if provider_used == "groq" and _script_missing_accents(data):
            print("⚠️ Accents manquants detectes dans le script (Groq), nouvelle tentative via Gemini...")
            data, _ = self._call_json_with_retry(
                messages,
                temperature=0.75,
                skip_providers={"groq"}
            )

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
        allowed_moods = {"ominous", "intriguing", "tense", "awe", "scientific", "melancholic", "revelatory"}

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

    print("📡 Récupération des statistiques Zernio pour l'Agent IA...")
    stats_historique = get_latest_videos_stats()

    topic = brain.get_trending_topic(previous_stats_list=stats_historique)
    print(f"\nSujet retenu : {topic}\n")

    hooks = brain.generate_hook_variants(topic, n=5, previous_stats_list=stats_historique)

    for i, h in enumerate(hooks, 1):
        print(f"{i}. [{h['pattern']}] {h['text']}")

    best_hook = hooks[0]["text"]
    print(f"\nHook choisi : {best_hook}\n")

    script_data = brain.generate_script(topic, chosen_hook=best_hook)

    # 🛠️ AJOUT : generation de la requete video, jusqu'ici jamais appelee
    # dans le pipeline malgre son role cle pour VideoScraper.
    video_query = brain.generate_video_search_query(topic)
    print(f"\n🎥 Requête vidéo générée : {video_query}\n")
    script_data["video_search_query"] = video_query

    with open("script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=4, ensure_ascii=False)

    print("Script saved to script.json")