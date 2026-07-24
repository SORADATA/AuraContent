import json

class ContentBrain:
    def get_trending_topic(self):
        return "Le mystère des pyramides d'Égypte"

    def generate_script(self, topic):
        print(f"📝 Using pre-compiled script for: {topic}...")
        # Un script pré-formaté aux normes exigées par ton Compositeur
        return [
            {
                "id": 1,
                "text": "Au cœur des sables d'Égypte, les pyramides cachent encore des secrets millénaires.",
                "visual_1": "egyptian pyramids aerial drone",
                "visual_2": "desert sand wind cinematic",
                "mood": "intriguing"
            },
            {
                "id": 2,
                "text": "Comment des blocs de plusieurs tonnes ont-ils pu être assemblés avec une telle précision ?",
                "visual_1": "ancient hieroglyphics close up",
                "visual_2": "stone blocks pyramid construction",
                "mood": "mystery"
            },
            {
                "id": 3,
                "text": "Les archéologues continuent de sonder les profondeurs à la recherche de chambres secrètes.",
                "visual_1": "archaeologist cave flashlight",
                "visual_2": "dark tunnel ancient tomb",
                "mood": "educational"
            },
            {
                "id": 4,
                "text": "Une chose est sûre : le génie de ces bâtisseurs défie le temps et notre compréhension.",
                "visual_1": "sunset over pyramids timelapse",
                "visual_2": "sphinx giza panoramic view",
                "mood": "cinematic"
            }
        ]

if __name__ == "__main__":
    brain = ContentBrain()
    topic = brain.get_trending_topic()
    script = brain.generate_script(topic)
    with open("script.json", "w") as f:
        json.dumps(script, f, indent=4)
        print("✅ Script saved to script.json")
