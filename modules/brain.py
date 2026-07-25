import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.5-flash"


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

    def _call_with_fallback(self, messages, temperature=1.0, json_mode=False):
        """
        Essaie Groq en premier. Si la cle est absente ou que l'appel echoue
        (quota, erreur reseau, timeout...), bascule automatiquement sur Gemini.
        """
        last_error = None

        for provider in ("groq", "gemini"):
            client = self._build_client(provider)
            if client is None:
                print(f"⚠️  Cle API absente pour {provider}, on passe au suivant...")
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
                return response.choices[0].message.content

            except Exception as e:
                print(f"❌ Echec avec {provider}: {e}")
                last_error = e
                continue

        raise RuntimeError(f"Aucun provider disponible (Groq et Gemini ont echoue). Derniere erreur: {last_error}")

    def get_trending_topic(self):
        print("🔍 Recherche d'un nouveau sujet tendance...")

        messages = [
            {"role": "system", "content": "Tu es un strategiste de contenu viral. Trouve de toi-meme un sujet de mini-documentaire court, captivant et inattendu. Reponds UNIQUEMENT avec le titre du sujet en francais, sans guillemets, sans introduction."},
            {"role": "user", "content": "Donne un sujet viral totalement inedit et surprenant pour TikTok en francais."}
        ]

        content = self._call_with_fallback(messages, temperature=1.2)
        topic = content.strip().replace('"', "")
        print(f"🎯 Sujet selectionne : {topic}")
        return topic

    def refine_topic_angle(self, raw_topic):
        """
        Prend un sujet brut/trend TikTok saisi par l'utilisateur et le reformule
        en un angle accrocheur pour un script viral, sans changer le sujet de fond.
        """
        print(f"🔧 Reformulation de l'angle pour: {raw_topic}...")

        messages = [
            {"role": "system", "content": "Tu es un strategiste de contenu viral. Reformule le sujet donne par l'utilisateur en un titre accrocheur et precis pour une video courte, en francais. Garde le sujet de fond identique, ne change pas le theme. Reponds UNIQUEMENT avec le titre reformule, sans guillemets, sans explication."},
            {"role": "user", "content": f"Sujet brut / trend repere: {raw_topic}"}
        ]

        content = self._call_with_fallback(messages, temperature=0.8)
        refined = content.strip().replace('"', "")
        print(f"    ✅ Angle affine : {refined}")
        return refined

    def generate_script(self, topic):
        return self.generate_script_with_target(topic, scene_count=11)

    def generate_script_with_target(self, topic, scene_count=11):
        print(f"📝 Ecriture du script en francais pour: {topic} ({scene_count} scenes)...")

        prompt = f"""
You are the lead scriptwriter for a high-retention faceless short-form video channel (TikTok, Reels, Shorts).
Topic: {topic}

### LANGUAGE RULES:
- The voiceover "text" MUST be entirely in French.
- "visual_1" and "visual_2" search/prompt terms MUST remain in English.

### SCENE COUNT:
- Generate exactly {scene_count} scenes.

### MANDATORY NARRATIVE STRUCTURE (respect this order strictly):
1. Scene 1 (HOOK, id=1): A shocking claim, a precise number, or a question that creates an information gap.
   FORBIDDEN openers: "Aujourd'hui on va parler de", "Savais-tu que", "Bienvenue".
   Must set up a promise that gets resolved later. Keep it punchy, max 10 words.
2. Scene 2 (TENSION): Why this matters, raise stakes or curiosity.
3. Scenes 3 to (N-2) (VALUE): One surprising fact or mechanism per scene, with enough
   context to feel complete, not just a fragment.
4. Last two scenes (TWIST + CTA): A reversal or payoff, then a direct call to action
   (e.g. "Abonne-toi pour la suite" / a question inviting comments). The CTA must be
   its own final scene.

### PACING RULE:
- Each scene "text" must be a complete, natural French sentence between 12 and 22 words.
- Avoid short choppy fragments. Each scene should give the narrator enough to say for
  a comfortable 4 to 7 second voiceover at a normal speaking pace.

### OUTPUT FORMAT (Strict JSON Object with a "scenes" array):
{{
    "scenes": [
        {{
            "id": 1,
            "text": "Texte de la voix off en francais ici...",
            "visual_1": "english search keywords for pexels",
            "visual_2": "english search keywords for pexels",
            "mood": "intriguing",
            "role": "hook"
        }}
    ]
}}

Valid "role" values: "hook", "tension", "value", "twist", "cta".
"""

        messages = [
            {"role": "system", "content": f"You are a helpful assistant that outputs only a valid JSON object containing a 'scenes' array with exactly {scene_count} scenes. The text must be strictly in French. Respect the pacing rule (12-22 words per scene, complete sentences) strictly."},
            {"role": "user", "content": prompt}
        ]

        content = self._call_with_fallback(messages, temperature=1.0, json_mode=True)
        data = json.loads(content)
        scenes = data.get("scenes", data) if isinstance(data, dict) else data
        return scenes


if __name__ == "__main__":
    brain = ContentBrain()
    topic = brain.get_trending_topic()
    script = brain.generate_script(topic)
    with open("script.json", "w") as f:
        json.dump(script, f, indent=4)
        print("✅ Script saved to script.json")