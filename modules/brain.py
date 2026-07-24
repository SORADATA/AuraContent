import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class ContentBrain:
    def get_trending_topic(self):
        print("🔍 Recherche d'un nouveau sujet tendance...")
        groq_key = os.getenv("CROQ_API_KEY") or os.getenv("GROQ_API_KEY")

        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Tu es un strategiste de contenu viral. Trouve de toi-meme un sujet de mini-documentaire court, captivant et inattendu. INTERDICTION STRICTE de choisir l'Egypte, les pharaons ou les pyramides. Reponds UNIQUEMENT avec le titre du sujet en francais, sans guillemets, sans introduction."},
                {"role": "user", "content": "Donne un sujet viral totalement inedit et surprenant pour TikTok en francais."}
            ],
            temperature=1.2
        )
        topic = response.choices[0].message.content.strip().replace('"', '')
        print(f"🎯 Sujet selectionne : {topic}")
        return topic

    def generate_script(self, topic):
        print(f"📝 Writing multi-platform short script in French with Groq for: {topic}...")

        groq_key = os.getenv("CROQ_API_KEY") or os.getenv("GROQ_API_KEY")

        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key
        )

        prompt = f"""
You are the lead scriptwriter for a high-retention faceless short-form video channel (TikTok, Reels, Shorts).
Topic: {topic}

### LANGUAGE RULES:
- The voiceover "text" MUST be entirely in French.
- "visual_1" and "visual_2" search/prompt terms MUST remain in English.

### MANDATORY NARRATIVE STRUCTURE (respect this order strictly):
1. Scene 1 (HOOK, id=1): A shocking claim, a precise number, or a question that creates an information gap.
   FORBIDDEN openers: "Aujourd'hui on va parler de", "Savais-tu que", "Bienvenue".
   Must set up a promise that gets resolved later. Max 8 words.
2. Scene 2 (TENSION): Why this matters, raise stakes or curiosity.
3. Scenes 3 to (N-2) (VALUE): One surprising fact or mechanism per scene.
4. Last two scenes (TWIST + CTA): A reversal or payoff, then a direct call to action
   (e.g. "Abonne-toi pour la suite" / a question inviting comments). The CTA must be
   its own final scene.

### PACING RULE:
- Each scene "text" must be between 6 and 14 words MAXIMUM. Short punchy sentences only.

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

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only a valid JSON object containing a 'scenes' array. The text must be strictly in French. Respect the pacing rule (6-14 words per scene) and the narrative structure strictly."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        return data.get("scenes", data) if isinstance(data, dict) else data


if __name__ == "__main__":
    brain = ContentBrain()
    topic = brain.get_trending_topic()
    script = brain.generate_script(topic)
    with open("script.json", "w") as f:
        json.dump(script, f, indent=4)
        print("✅ Script saved to script.json")