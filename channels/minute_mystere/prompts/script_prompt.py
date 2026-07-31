ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc). Exemples obligatoires : 'découvert' "
    "(jamais 'decouvert'), 'secrètes' (jamais 'secretes'), 'exploré' "
    "(jamais 'explore'), 'phénomène' (jamais 'phenomene'), 'révélation' "
    "(jamais 'revelation'), 'étrange' (jamais 'etrange'), 'théorie' "
    "(jamais 'theorie'). Verifie chaque mot avant de repondre."
)


def build_script_prompt(topic: str, scene_count: int, chosen_hook: str | None = None) -> str:
    hook_instruction = (
        f'La scene 1 doit reprendre exactement ou reformuler tres legerement ce hook deja valide : "{chosen_hook}"'
        if chosen_hook else
        "Scene 1 - hook : une phrase de 12 a 18 mots combinant un fait concret ET une ancre "
        "sensorielle ou emotionnelle (son, image, sensation, confession). Cree une promesse "
        "qui sera resolue dans l'avant-derniere scene."
    )

    return f"""
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