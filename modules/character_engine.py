import json
from modules.brain import ContentBrain
from constants_mimolune import SPEAKERS

class KidsScriptwriter(ContentBrain):
    """
    Reutilise le moteur Groq/Gemini de ContentBrain (voir modules/brain.py)
    mais genere une comptine pour enfants au lieu d'un script viral.
    """

    def generate_comptine(self, theme, scene_count=8):
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

### FORMAT DE SORTIE (JSON strict, objet avec "theme" et "scenes") :
{{
    "theme": "{theme}",
    "scenes": [
        {{
            "id": 1,
            "speaker": "mimolune",
            "text": "Texte francais rime ici...",
            "background": "english prompt for image generation, kids illustration style, vibrant pastel colors",
            "action": "dance"
        }}
    ]
}}

Genere exactement {scene_count} scenes. "speaker" doit etre une valeur parmi : {SPEAKERS}.
La derniere scene doit etre un au revoir joyeux de Mimolune invitant a revenir ("action": "wave").
"""

        messages = [
            {
                "role": "system",
                "content": (
                    f"Tu es un generateur qui repond uniquement avec un objet JSON valide "
                    f"contenant 'theme' et 'scenes' (exactement {scene_count} scenes). "
                    "Contenu strictement adapte aux enfants de 2 a 6 ans, en francais."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        content = self._call_with_fallback(messages, temperature=1.0, json_mode=True)
        
        # --- AJOUT SÉCURITÉ : Nettoyage des balises Markdown ---
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        # --------------------------------------------------------

        data = json.loads(content)

        scenes = data.get("scenes", [])
        if len(scenes) != scene_count:
            print(f"    ⚠️ Attendu {scene_count} scenes, recu {len(scenes)} — poursuite quand meme.")

        return data


if __name__ == "__main__":
    # --- AJOUT SÉCURITÉ : Passer une config vide pour le test ---
    writer = KidsScriptwriter(config={}) 
    script = writer.generate_comptine("Les couleurs de l'arc-en-ciel")
    
    with open("comptine.json", "w", encoding="utf-8") as f:
        json.dump(script, f, indent=4, ensure_ascii=False)
    print("✅ Comptine sauvegardee dans comptine.json")