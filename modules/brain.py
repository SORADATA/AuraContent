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
                {"role": "system", "content": "Tu es un stratège de contenu viral. Trouve de toi-même un sujet de mini-documentaire court, captivant et inattendu. INTERDICTION STRICTE de choisir l'Égypte, les pharaons ou les pyramides. Réponds UNIQUEMENT avec le titre du sujet en français, sans guillemets, sans introduction."},
                {"role": "user", "content": "Donne un sujet viral totalement inédit et surprenant pour TikTok en français."}
            ],
            temperature=1.2
        )
        topic = response.choices[0].message.content.strip().replace('"', '')
        print(f"🎯 Sujet sélectionné : {topic}")
        return topic

    def generate_script(self, topic):
        print(f"📝 Writing multi-platform short script in French with Groq for: {topic}...")
        
        groq_key = os.getenv("CROQ_API_KEY") or os.getenv("GROQ_API_KEY")
        
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key
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
