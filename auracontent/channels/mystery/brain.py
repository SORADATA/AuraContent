from core.base_brain import BaseBrain


class MysteryBrain(BaseBrain):
    channel_name = "mystery"

    def build_script_prompt(self, topic, scene_count, chosen_hook, correction_feedback):
        # Ici vous mettez vos règles strictes: VERACITY_INSTRUCTION, ACCENT_INSTRUCTION...
        system_msg = "Tu es un narrateur d'histoires mystérieuses..."
        user_msg = f"Sujet: {topic}\nFais {scene_count} scènes.\n{correction_feedback}"
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]

    def check_script_logic(self, topic, data):
        # Ici vous appelez votre WikidataChecker et le fact_check_script !
        issues = []
        geo_issues = self._check_wikidata_locations(data["scenes"])
        if geo_issues:
            issues.extend(geo_issues)
        return issues