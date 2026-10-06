import os
import time
import json
from openai import OpenAI
from dataclasses import dataclass
from typing import list, dict, Any
from config import settings
from utils.text_utils import _estimate_prompt_tokens, _clean_json_response


SAFETY_MARGIN_TOKENS = 400


@dataclass
class LLMClient:
    providers: list[dict[str, Any]]

    @classmethod
    def create_default(cls):
        """
        instancie LLMClient avec la config par defaut des variables d'environnement
        """
        return cls(providers=cls._build_providers_list())

    @classmethod
    def _build_providers_list(cls) -> list[dict[str, any]]:
        providers = []
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            for model in settings.GROQ_MODELS:
                providers.append({
                    "name": "Groq",
                    "model": model,
                    "base_url": "https://api.groq.com/openai/v1",
                    "api_key": groq_key
                })
        or_key = os.getenv("OPENROUTER_API_KEY")
        if or_key:
            for model in settings.OPENROUTER_ROUTING:
                providers.append({
                    "name": "OpenRouter",
                    "model": model,
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": or_key
                })
        if not providers:
            print(
                "⚠️ AVERTISSEMENT : Aucun fournisseur LLM configuré.Vérifiez vos clés dans le .env."
                )
        return providers

    def _extract_content(self, response):
        choices = getattr(response, "choices", None) or response.get("choices")
        choice0 = choices[0]
        message = getattr(choice0, "message", None) or choice0.get("message")
        content = getattr(message, "content", None) or message.get("content")
        return content.strip()

    def call_with_fallback(self, messages, temperature=1.0, json_mode=False,
                           max_completion_tokens=3000, hard_token_cap=7500):
        """Essaie chaque modèle de config.settings dans l'ordre défini"""
        last_error = None
        prompt_tokens_is = _estimate_prompt_tokens(messages)
        # On itère directement sur la liste générée par l'init
        for provider in self.providers:
            client = OpenAI(base_url=provider["base_url"], api_key=provider["api_key"])
            current_max_tokens = max_completion_tokens
            available = hard_token_cap - prompt_tokens_is - SAFETY_MARGIN_TOKENS
            if current_max_tokens > available:
                current_max_tokens = max(500, available)

            for attempt in range(3):
                try:
                    kwargs = {
                        "model": provider["model"],
                        "messages": messages,
                        "temperature": temperature,
                        "max_completion_tokens": current_max_tokens,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    response = client.chat.completions.create(**kwargs)
                    print(f"✅ Réponse obtenue via {provider['name']} ({provider['model']})")
                    return self._extract_content(response)

                except Exception as e:
                    # Gestion des erreurs (Rate limit, tokens, etc.)
                    last_error = e
                    print(f"⚠️ Échec {provider['name']} ({provider['model']}) : {e}")
                    time.sleep(2)
                    break
        raise RuntimeError(
            f"Échec total après utilisation de tous les modèles (Groq + OpenRouter).Dernière erreur:{last_error}"
            )

    def call_json_with_retry(self, messages, temperature=1.0, max_json_retries=2,
                             max_completion_tokens=6000, hard_token_cap=7500):
        # Appelle self.call_with_fallback sans avoir besoin de lui passer la config
        last_error = None
        for attempt in range(max_json_retries):
            content = self.call_with_fallback(
                messages, temperature=temperature, json_mode=True,
                max_completion_tokens=max_completion_tokens, hard_token_cap=hard_token_cap
            )
            try:
                data = json.loads(_clean_json_response(content))
                if isinstance(data, list):
                    data = {"scenes": data}
                return data
            except json.JSONDecodeError as e:
                last_error = e
                max_completion_tokens = min(max_completion_tokens + 1000, hard_token_cap)

        raise ValueError(f"Impossible d'obtenir un JSON valide : {last_error}")
