ACCENT_INSTRUCTION = (
    "IMPERATIF ORTHOGRAPHE : le francais doit etre parfaitement accentue "
    "(é, è, ê, à, ù, ç, ô, î etc). Exemples obligatoires : 'découvert' "
    "(jamais 'decouvert'), 'bénéfice' (jamais 'benefice'), 'intérêt' "
    "(jamais 'interet'), 'inflation' (garder les accents si requis), 'marché' "
    "(jamais 'marche'), 'crédit' (jamais 'credit'). Verifie chaque mot avant de repondre."
)


def build_script_prompt(topic: str, scene_count: int, chosen_hook: str | None = None) -> str:
    hook_instruction = (
        f'La scene 1 doit reprendre exactement ou reformuler tres legerement ce hook deja valide : "{chosen_hook}"'
        if chosen_hook else
        "Scene 1 - hook : une phrase de 12 a 18 mots combinant un chiffre choc ou un fait economique concret "
        "AVEC une ancre d'urgence ou de curiosite (une somme d'argent perdue/gagnees, un mecanisme cache). "
        "Cree une promesse qui sera resolue dans l'avant-derniere scene."
    )

    return f"""
Tu es analyste financier et scenariste en chef d'une chaine francophone de mini-documentaires
verticaux consacree a la finance, l'economie, la bourse, l'histoire de l'argent,
les systemes monetaires et les strategies d'enrichissement inattendues.

SUJET :
{topic}

OBJECTIF :
Creer une video TikTok, Reels ou Shorts captivante, credible, basee sur des faits reels,
facile a illustrer, et optimisee pour une narration vocale premium.

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
  Explique pourquoi cette situation financiere ou ce choix economique est critique, surprenant ou dangereux.
- Scene 3 - contexte :
  Situe clairement l'epoque, le marché, le contexte macroeconomique ou les acteurs concernes.
- Scenes 4 a {scene_count - 3} - enquete :
  Un nouvel indicateur, mécanisme de marché, faille ou décision stratégique par scene. Chaque scene
  doit ajouter une tension nouvelle, jamais une simple repetition du fait precedent.
- Scene {scene_count - 2} - escalade :
  Presente le retournement de situation le plus marquant ou le risque caché qui se concrétise.
- Scene {scene_count - 1} - revelation :
  Resous la promesse du hook avec la conclusion economique ou la lecon financiere la plus logique.
- Scene {scene_count} - CTA polarisant :
  Pose une question ou une affirmation économique qui divise volontairement l'audience
  (ex: investissement risqué vs sécurité, vision du capitalisme).
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
- Ne presente jamais une hypothese spéculative comme une verité absolue.
- N'invente ni dates, ni chiffres précis, ni montants faux.
- Pas de hashtags, d'emojis, de titres, de notes ou d'explications.

REGLES AUDIO :
- Chaque scene doit inclure "voice_direction" en anglais.
- "voice_direction" decrit comment un narrateur premium francais doit lire la phrase.
- Le rendu doit etre professionnel, percutant, analytique, sur de lui, jamais caricatural.
- Autorise seulement de legeres nuances comme : sharp, analytical, tense, serious, confident.
- Chaque scene doit inclure "pause_after_ms" avec une valeur entiere entre 180 et 450.
- Chaque scene peut inclure "tts_emphasis_word".
- Si "tts_emphasis_word" est present, il doit etre un mot exact du champ "text".
- "voice_direction" doit rester courte, utile, stable et compatible avec un moteur TTS premium.
- Exemple valide :
  "French premium narrator, sharp, confident, analytical pacing"

REGLES VISUELLES :
Chaque scene doit etre comprehensible a partir de son image seule.

"stock_search" :
- Entre 3 et 7 mots-cles anglais, sujet reellement trouvable dans une banque de videos
  (ex: stock market charts, modern glass office, counting money, digital banking).
- Pas de termes abstraits comme "wealth", "future" ou "success" seuls.

"image_prompt" :
- Decrit une seule composition visuelle, pas une succession d'actions.
- Commence par le sujet principal concret, puis action ou etat, environnement,
  epoque si necessaire, cadrage, lumiere, ambiance et details utiles.
- Composition verticale 9:16, sujet principal dans la zone centrale.
- Prevoir de l'espace libre en haut et en bas pour les sous-titres.
- Style cinematographique realiste, professionnel et moderne (ambiance Wall Street / tech).
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
  "title": "Titre francais court et percutant axe finance",
  "visual_identity": "One concise English sentence defining recurring clean corporate or trading visual continuity",
  "audio_profile": "French premium narrator, sharp, confident, professional, analytical pacing",
  "scenes": [
    {{
      "id": 1,
      "text": "Phrase francaise complete de douze a vingt-deux mots.",
      "voice_direction": "French premium narrator, sharp, confident, analytical pacing",
      "pause_after_ms": 300,
      "tts_emphasis_word": "mot",
      "stock_search": "concrete English stock footage keywords",
      "image_prompt": "Detailed English visual prompt for one vertical cinematic financial shot",
      "mood": "tense",
      "role": "hook"
    }}
  ]
}}
"""