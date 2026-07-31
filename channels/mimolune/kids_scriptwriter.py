import json
import re
from modules.brain import ContentBrain
from constants_mimolune import SPEAKERS


class KidsScriptwriter(ContentBrain):
    """
    Reutilise le moteur Groq/Gemini de ContentBrain (voir modules/brain.py)
    mais genere une comptine pour enfants au lieu d'un script viral.
    """

    def _extract_json_text(self, response):
        if isinstance(response, tuple):
            response = response[0]

        if isinstance(response, (bytes, bytearray)):
            response = response.decode("utf-8", errors="replace")

        if not isinstance(response, str):
            raise TypeError(
                f"Réponse inattendue: json attendu sous forme de texte, reçu {type(response).__name__}"
            )

        text = response.strip()

        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        if not text.startswith("{"):
            object_match = re.search(r"(\{.*\})", text, re.DOTALL)
            if object_match:
                text = object_match.group(1).strip()

        return text

    def _validate_scene(self, scene, expected_id, expected_action=None):
        if not isinstance(scene, dict):
            raise ValueError(f"Scene {expected_id}: objet JSON attendu.")

        speaker = scene.get("speaker")
        if speaker not in SPEAKERS:
            raise ValueError(
                f"Scene {expected_id}: speaker invalide '{speaker}'. Valeurs autorisées: {SPEAKERS}"
            )

        text = scene.get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Scene {expected_id}: champ 'text' manquant ou vide.")

        scene_prompt = scene.get("scene_prompt", "")
        if not isinstance(scene_prompt, str) or not scene_prompt.strip():
            raise ValueError(f"Scene {expected_id}: champ 'scene_prompt' manquant ou vide.")

        action = scene.get("action")
        if action not in ("dance", "wave"):
            raise ValueError(
                f"Scene {expected_id}: action invalide '{action}', attendu 'dance' ou 'wave'."
            )

        if expected_action and action != expected_action:
            print(
                f"    ⚠️ Scene {expected_id}: action attendue '{expected_action}', reçue '{action}'."
            )

    def generate_comptine(self, theme, scene_count=8):
        theme = (theme or "").strip()
        if not theme:
            theme = "une journée joyeuse avec Mimolune"

        print(f"🎵 Ecriture de la comptine pour : {theme} ({scene_count} scenes)...")

        prompt = f"""
Tu es parolier pour une chaine de comptines pour enfants (2 a 6 ans) sur TikTok.
Theme de la comptine : {theme}
Personnage principal : Mimolune, une petite lune ronde et joyeuse.
Personnages secondaires possibles : fruit_fraise, fruit_banane.

### REGLES DE CONTENU (STRICTES) :
- Aucune violence, aucune peur, aucun element effrayant. Contenu 100% positif et bienveillant.
- Le texte est entierement en francais, avec des rimes simples (schema AABB de preference).
- Chaque ligne fait entre 6 et 12 mots, facile a chanter pour un enfant.
- Mimolune parle dans au moins la moitie des scenes. Les scenes restantes sont reparties
  entre les personnages secondaires.
- Alterne les valeurs de "action" entre "dance" (mouvement rapide et joyeux) et "wave"
  (mouvement doux, scene plus calme).
- Reponds avec du JSON brut uniquement.
- Ne mets pas de balises markdown.
- N'ajoute aucune explication avant ou apres le JSON.

### FORMAT DE SORTIE (JSON strict, objet avec "theme" et "scenes") :
{{
    "theme": "{theme}",
    "scenes": [
        {{
            "id": 1,
            "speaker": "mimolune",
            "text": "Texte francais rime ici...",
            "scene_prompt": "english prompt describing the character AND the full scene together for AI video animation, e.g. 'Mimolune the round joyful moon character dances happily in a colorful rainbow garden, kids illustration style, vibrant pastel colors, cinematic gentle motion'",
            "action": "dance"
        }}
    ]
}}

<<<<<<< HEAD:channels/mimolune/kids_scriptwriter.py
Genere exactement {scene_count} scenes. "speaker" doit etre une valeur parmi : {SPEAKERS}.
Le champ "scene_prompt" doit TOUJOURS decrire le personnage ET le decor ensemble, jamais le decor seul,
et doit inclure une description du mouvement correspondant a "action" (danse joyeuse ou geste doux).
La derniere scene doit etre un au revoir joyeux de Mimolune invitant a revenir ("action": "wave").
=======
Genere exactement {scene_count} scenes.
"speaker" doit etre une valeur parmi : {SPEAKERS}.
Le champ "scene_prompt" doit TOUJOURS decrire le personnage ET le decor ensemble, jamais le decor seul,
et doit inclure une description du mouvement correspondant a "action" (danse joyeuse ou geste doux).
La derniere scene doit etre un au revoir joyeux de Mimolune invitant a revenir avec "speaker": "mimolune" et "action": "wave".
>>>>>>> Main:modules/kids_scriptwriter.py
"""

        messages = [
            {
                "role": "system",
                "content": (
                    f"Tu es un generateur qui repond uniquement avec un objet JSON valide "
                    f"contenant 'theme' et 'scenes' (exactement {scene_count} scenes). "
                    "Contenu strictement adapte aux enfants de 2 a 6 ans, en francais. "
                    "Aucun markdown. Aucun texte hors JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        response = self._call_with_fallback(messages, temperature=1.0, json_mode=True)
        content = self._extract_json_text(response)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON invalide reçu du modèle : {e}\nContenu brut:\n{content}") from e

        if not isinstance(data, dict):
            raise ValueError("Le JSON retourné doit etre un objet.")

        if "theme" not in data:
            data["theme"] = theme

        scenes = data.get("scenes", [])
        if not isinstance(scenes, list):
            raise ValueError("Le champ 'scenes' doit etre une liste.")

        if len(scenes) != scene_count:
            print(f"    ⚠️ Attendu {scene_count} scenes, recu {len(scenes)} — poursuite quand meme.")

        mimolune_count = 0

        for i, scene in enumerate(scenes, start=1):
            expected_action = "wave" if i == scene_count else ("dance" if i % 2 == 1 else "wave")

            if "id" not in scene or not isinstance(scene["id"], int):
                scene["id"] = i

            self._validate_scene(scene, expected_id=i, expected_action=expected_action)

            if scene["speaker"] == "mimolune":
                mimolune_count += 1

        if scenes:
            last_scene = scenes[-1]
            last_scene["speaker"] = "mimolune"
            last_scene["action"] = "wave"

        minimum_mimolune = max(1, scene_count // 2)
        if mimolune_count < minimum_mimolune:
            print(
                f"    ⚠️ Mimolune parle seulement dans {mimolune_count} scenes sur {scene_count}."
            )

        return data


if __name__ == "__main__":
    writer = KidsScriptwriter()
    script = writer.generate_comptine("Les couleurs de l'arc-en-ciel")
    with open("comptine.json", "w", encoding="utf-8") as f:
        json.dump(script, f, indent=4, ensure_ascii=False)
    print("✅ Comptine sauvegardee dans comptine.json")
