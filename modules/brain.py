import os
import json
from google import genai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class ContentBrain:
    def get_trending_topic(self):
        return "Le mystère des pyramides d'Égypte"

    def generate_script(self, topic):
        print(f"📝 Writing script for: {topic}...")
        
        prompt = f"""
    You are the lead scriptwriter for a high-retention "Edutainment" YouTube Shorts channel.
    Topic: {topic}

    ### GOAL:
    Create a script where every sentence has a "Visual Switch". 
    To keep retention high, we need TWO different stock videos for every single scene.

    ### 1. SCRIPT REQUIREMENTS (The Voiceover):
    - **Perspective:** Strictly **3rd Person** ("Scientists found...", "The ocean hides...").
    - **Tone:** Engaging, fast-paced, logical. No fluff.
    - **Structure:** 4 Scenes total.

    ### OUTPUT FORMAT (Strict JSON):
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

        # --- TENTATIVE 1 : Essayer Gemini ---
        try:
            print("🔄 Tentative avec l'API Gemini...")
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
                clean_text = response.text.replace('```json', '').replace('```', '').strip()
                return json.loads(clean_text)
        except Exception as e:
            print(f"⚠️ Échec Gemini (Quota ou Erreur) : {e}")

        # --- TENTATIVE 2 : Repli sur OpenAI (GPT-4o-mini) si Gemini échoue ---
        try:
            print("🔄 Bascule automatique sur l'API OpenAI (GPT-4o-mini)...")
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                client = OpenAI(api_key=openai_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Return ONLY a valid JSON array matching the requested structure."},
                        {"role": "user", "content": prompt}
                    ]
                )
                content = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
                return json.loads(content)
        except Exception as e:
            print(f"⚠️ Échec OpenAI : {e}")

        # --- SECOURS ULTIME : Données statiques si tout le reste plante ---
        print("🚨 Toutes les IA ont échoué. Utilisation du script de secours par défaut.")
        return [
            {
                "id": 1,
                "text": "Au cœur des sables d'Égypte, les pyramides cachent encore des secrets millénaires.",
                "visual_1": "egyptian pyramids aerial drone",
                "visual_2": "desert sand wind cinematic",
                "mood": "intriguing"
            }
        ]
