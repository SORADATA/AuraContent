import os
import json
from google import genai
from dotenv import load_dotenv

# Load API Key
client = genai.Client(api_key="AIzaSyCk4YYTASWxy1R5x_UE4KUPNT_Hbgd0pDQ")

class ContentBrain:
    def get_trending_topic(self):
        """
        In a full build, this would scrape Google Trends or Twitter.
        For now, we ask Gemini to pick a viral niche topic.
        """
        prompts = "Give me 1 specific, viral, and engaging topic for a YouTube Short. It should be a 'Did you know' fact or a 'Engaging News'. return ONLY the topic name."
        response = client.models.generate_content(model='gemini-3-flash-preview', contents=prompts)
        topic = response.text.strip()
        print(f"🎯 Selected Topic: {topic}")
        return topic

    def generate_script(self, topic):
        """
        Generates a structured JSON script with visual cues.
        """
        print(f"📝 Writing script for: {topic}...")
        
        prompt = f"""
        You are an expert visual storyteller and YouTube Shorts scriptwriter. 
        Topic: {topic}
        
        ### CRITICAL REQUIREMENTS:
        1. **Perspective:** Write strictly in **3rd Person** (e.g., "Scientists have discovered..." or "The ocean hides..."). Do NOT use "You" or "I".
        2. **Tone:** Organic, cinematic, and engaging. It should feel like a mini-documentary, not a sales pitch.
        3. **Length:** Create exactly **8 to 9 scenes**.
        4. **Visual Strategy:** The 'keywords' must be optimized for **Stock Footage** search engines (Pexels).
           - Use clear, descriptive nouns (e.g., "dark forest drone shot", "time lapse city traffic", "only phrase").
           - Avoid specific people or complex actions that stock footage won't have.
        
        ### STRUCTURE GUIDE (30-45 Seconds Total):
        - **Scene 1 (The Hook):** A visually striking statement that grabs attention instantly.
        - **Scene 2-3 (The Setup):** Establish the context or the mystery.
        - **Scene 4-7 (The Reveal):** The core interesting fact or twist.
        - **Scene 8-9 (Conclusion):** A satisfying wrap-up with a subtle call to action.
        
        ### OUTPUT FORMAT (Strict JSON):
        [
            {{
                "id": 1,
                "text": "Deep beneath the Antarctic ice, something massive has just been detected.",
                "keywords": "Antarctica ice aerial drone cinematic",
                "mood": "mysterious" 
            }},
            {{
                "id": 2,
                "text": "For centuries, explorers believed this frozen wasteland was completely empty.",
                "keywords": "blizzard snow storm whiteout",
                "mood": "serious"
            }}
        ]
        """

        response = client.models.generate_content(model='gemini-3-flash-preview', contents=prompt)
        
        # Clean the response to ensure it's valid JSON (sometimes AI adds markdown)
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        
        try:
            script_data = json.loads(clean_text)
            return script_data
        except json.JSONDecodeError:
            print("❌ Error parsing JSON. Raw output:")
            print(clean_text)
            return None
        
# --- TESTING THE MODULE ---
if __name__ == "__main__":
    brain = ContentBrain()
    topic = brain.get_trending_topic()
    script = brain.generate_script(topic)
    
    # Save to file to verify
    with open("script.json", "w") as f:
        json.dump(script, f, indent=4)
        print("✅ Script saved to script.json")