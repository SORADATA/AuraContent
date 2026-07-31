import json
from typing import Optional

from modules.brain.llm_client import LLMClient
from modules.brain.models import BrainChannelConfig
from modules.brain.validators import script_missing_accents, validate_script_payload


class ContentBrain:
    def __init__(self, channel_config: BrainChannelConfig, llm_client: Optional[LLMClient] = None):
        self.channel_config = channel_config
        self.llm = llm_client or LLMClient()

    def get_trending_topic(self) -> str:
        messages = [
            {"role": "system", "content": self.channel_config.topic_system_prompt},
            {"role": "user", "content": self.channel_config.topic_user_prompt},
        ]
        content, _ = self.llm.call_with_fallback(
            messages=messages,
            temperature=1.2,
            json_mode=False,
            providers_order=self.channel_config.providers_order,
        )
        return content.strip().replace('"', "")

    def refine_topic_angle(self, raw_topic: str) -> str:
        messages = [
            {"role": "system", "content": self.channel_config.angle_system_prompt},
            {"role": "user", "content": raw_topic},
        ]
        content, _ = self.llm.call_with_fallback(
            messages=messages,
            temperature=0.8,
            json_mode=False,
            providers_order=self.channel_config.providers_order,
        )
        return content.strip().replace('"', "")

    def generate_hook_variants(self, topic: str, n: int = 5) -> list[dict]:
        if not self.channel_config.hook_prompt_builder:
            raise ValueError("hook_prompt_builder manquant dans la config de chaîne.")

        prompt = self.channel_config.hook_prompt_builder(topic, n)

        messages = [
            {"role": "system", "content": "Tu produis uniquement du JSON valide."},
            {"role": "user", "content": prompt},
        ]

        content, provider_used = self.llm.call_with_fallback(
            messages=messages,
            temperature=1.1,
            json_mode=True,
            providers_order=self.channel_config.providers_order,
        )
        data = json.loads(content)

        if self.channel_config.strict_accents and provider_used == "groq":
            temp_script = {"scenes": [{"text": hook.get("text", "")} for hook in data.get("hooks", [])]}
            if script_missing_accents(temp_script):
                content, _ = self.llm.call_with_fallback(
                    messages=messages,
                    temperature=1.1,
                    json_mode=True,
                    providers_order=self.channel_config.providers_order,
                    skip_providers={"groq"},
                )
                data = json.loads(content)

        hooks = data.get("hooks")
        if not isinstance(hooks, list) or len(hooks) != n:
            raise ValueError(
                f"Nombre de hooks invalide : {len(hooks) if isinstance(hooks, list) else 0} au lieu de {n}."
            )

        return hooks

    def generate_script(
        self,
        topic: str,
        scene_count: Optional[int] = None,
        chosen_hook: Optional[str] = None,
    ) -> dict:
        final_scene_count = scene_count or self.channel_config.default_scene_count

        if not self.channel_config.script_prompt_builder:
            raise ValueError("script_prompt_builder manquant dans la config de chaîne.")

        prompt = self.channel_config.script_prompt_builder(topic, final_scene_count, chosen_hook)

        messages = [
            {"role": "system", "content": "Tu produis uniquement du JSON valide."},
            {"role": "user", "content": prompt},
        ]

        content, provider_used = self.llm.call_with_fallback(
            messages=messages,
            temperature=0.75,
            json_mode=True,
            providers_order=self.channel_config.providers_order,
        )
        data = json.loads(content)

        if self.channel_config.strict_accents and provider_used == "groq" and script_missing_accents(data):
            content, _ = self.llm.call_with_fallback(
                messages=messages,
                temperature=0.75,
                json_mode=True,
                providers_order=self.channel_config.providers_order,
                skip_providers={"groq"},
            )
            data = json.loads(content)

        validate_script_payload(data, final_scene_count)
        return data