import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class ContentBrain:
    def get_trending_topic(self):
        return "Le mystère des pyramides d'Égypte"

    def generate_script(self, topic):
        print(f"📝 Writing script with Groq (Llama 3 - Open Source) for: {topic}...")
        
        # Groq est 100% gratuit et utilise une API compatible OpenAI
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY")
        )
        
        prompt = f"""
    You are the lead scriptwriter for a high-retention "Edutainment" YouTube Shorts channel.
    Topic: {topic}

    ### GOAL:
    Create a script where every sentence has a "Visual Switch". 
    To keep retention high, we need TWO different stock videos for every single scene.

    ### OUTPUT FORMAT (Strict JSON Array):
    [
        {{
            "id": 1,
            "text": "Au cœur des sables d'Égypte, les pyramides cachent des secrets.",
            "visual_1": "egyptian pyramids aerial drone",
            "visual_2": "desert sand wind cinematic",
            "mood": "intriguing" 
        }}
    ]
    """

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile", # Modèle open source ultra performant et gratuit sur Groq
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
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
