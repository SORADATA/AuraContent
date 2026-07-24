import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class ContentBrain:
    def get_trending_topic(self):
        print("🔍 Recherche d'un nouveau sujet tendance...")
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("CROQ_API_KEY")
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Tu es un stratège de contenu viral. Choisis un sujet totalement différent de l'Égypte ou des pyramides (oriente-toi vers l'espace, les profondeurs de l'océan, une invention insolite, un mystère de la psychologie humaine ou une légende urbaine moderne). Réponds UNIQUEMENT avec le titre du sujet en français, sans guillemets, sans introduction."},
                {"role": "user", "content": "Donne un sujet court, percutant et inattendu pour TikTok."}
            ],
            temperature=1.2  # 🚀 Température poussée pour garantir un nouveau sujet à chaque fois
        )
        topic = response.choices[0].message.content.strip().replace('"', '')
        print(f"🎯 Sujet sélectionné : {topic}")
        return topic

    def generate_script(self, topic):
        print(f"📝 Writing multi-platform short script in French with Groq for: {topic}...")
        
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("CROQ_API_KEY")
        )
        
        prompt = f"""
    You are the lead scriptwriter for a high-retention short-form video channel (TikTok, Instagram Reels, YouTube Shorts).
    Topic: {topic}

    ### IMPORTANT RULES:
    - **Language:** The voiceover "text" MUST be entirely in **French**.
    - **Visuals:** The "visual_1" and "visual_2" search terms MUST remain in **English** (for Pexels search compatibility).

    ### GOAL:
    Create a script where every sentence has a "Visual Switch". 
    To keep retention high on TikTok and Shorts, we need TWO different stock videos for every single scene.

    ### OUTPUT FORMAT (Strict JSON Object with a "scenes" array):
    {{
        "scenes": [
            {{
                "id": 1,
                "text": "Texte de la voix off en français ici...",
                "visual_1": "english search keywords for pexels",
                "visual_2": "english search keywords for pexels",
                "mood": "intriguing" 
            }}
        ]
    }}
    """

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only a valid JSON object containing a 'scenes' array. The text must be strictly in French."},
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
