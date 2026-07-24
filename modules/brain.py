import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()

def _get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Create a .env file or set the environment variable before running.")
    return genai.Client(api_key=api_key)

class ContentBrain:
    def get_trending_topic(self):
        prompts = "Give me 1 specific, viral, and engaging topic for a Short Documentary. It should be a 'Engaging Did you know' fact or a 'Fun/intriguing Engaging News'. return ONLY the topic name."
        client = _get_client()
        # Modèle forcé en 1.5-flash
        response = client.models.generate_content(model='gemini-1.5-flash', contents=prompts)
        topic = response.text.strip()
        print(f"🎯 Selected Topic: {topic}")
        return topic

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
    - **Structure:** 8-9 Scenes total.
    - **Flow:** Hook -> Context -> Mechanism (How it works) -> Twist -> Outro.

    ### 2. VISUAL REQUIREMENTS (Dual Visuals):
    - For EVERY scene, provide TWO distinct search terms:
      - **visual_1:** Matches the *start* of the sentence.
      - **visual_2:** Matches the *end* of the sentence or provides a reaction/context.
    - **Strictly Literal:** If the text is "The economy crashed," do NOT search "sad man". Search "Stock market red chart".

    ### OUTPUT FORMAT (Strict JSON):
    [
        {{
            "id": 1,
            "text": "In 1995, fourteen wolves were released into Yellowstone Park, and they changed the rivers.",
            "visual_1": "wolves running snow aerial",
            "visual_2": "river flowing forest drone",
            "mood": "intriguing" 
        }},
        {{
            "id": 2,
            "text": "It sounds impossible, but the biology is actually simple math.",
            "visual_1": "person shocked looking at camera",
            "visual_2": "blackboard math equations chalk",
            "mood": "educational"
        }}
    ]
    """

        client = _get_client()
        # 🔥 MODIFICATION ICI : On force gemini-1.5-flash pour éviter le blocage de quota du 2.0
        response = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
        
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        
        try:
            script_data = json.loads(clean_text)
            return script_data
        except json.JSONDecodeError:
            print("❌ Error parsing JSON. Raw output:")
            print(clean_text)
            return None
        
if __name__ == "__main__":
    brain = ContentBrain()
    topic = brain.get_trending_topic()
    script = brain.generate_script(topic)
    
    with open("script.json", "w") as f:
        json.dump(script, f, indent=4)
        print("✅ Script saved to script.json")
