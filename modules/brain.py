import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class ContentBrain:
    def get_trending_topic(self):
        print("🔍 Recherche d'un sujet tendance...")
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("CROQ_API_KEY")
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a viral content strategist. Return ONLY a single, engaging, and fascinating short documentary topic (e.g. 'Le saviez-vous' or mystery style). Give just the title in French, nothing else."},
                {"role": "user", "content": "Give me a viral topic for a YouTube Short."}
            ]
        )
        topic = response.choices[0].message.content.strip().replace('"', '')
        print(f"🎯 Sujet sélectionné : {topic}")
        return topic

    def generate_script(self, topic):
        print(f"📝 Writing script with Groq (Llama 3 - Open Source) for: {topic}...")
        
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY")
        )
        
        # On demande un objet JSON avec une clé "scenes" pour respecter le format de Groq
        prompt = f"""
    You are the lead scriptwriter for a high-retention "Edutainment" YouTube Shorts channel.
    Topic: {topic}

    ### GOAL:
    Create a script where every sentence has a "Visual Switch". 
    To keep retention high, we need TWO different stock videos for every single scene.

    ### OUTPUT FORMAT (Strict JSON Object with a "scenes" array):
    {{
        "scenes": [
            {{
                "id": 1,
                "text": "Au cœur des sables d'Égypte, les pyramides cachent des secrets.",
                "visual_1": "egyptian pyramids aerial drone",
                "visual_2": "desert sand wind cinematic",
                "mood": "intriguing" 
            }}
        ]
    }}
    """

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON object containing a 'scenes' array."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        
        # Extrait la liste des scènes de l'objet JSON retourné
        return data.get("scenes", data) if isinstance(data, dict) else data

if __name__ == "__main__":
    brain = ContentBrain()
    topic = brain.get_trending_topic()
    script = brain.generate_script(topic)
    with open("script.json", "w") as f:
        json.dump(script, f, indent=4)
        print("✅ Script saved to script.json")
