import os
from dataclasses import dataclass
from typing import Iterable, Optional

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    env_var: str
    base_url: str
    model: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    provider: str
    model: str


class ProviderRegistry:
    def __init__(self):
        self._providers = {
            "groq": ProviderSpec(
                name="groq",
                env_var="GROQ_API_KEY",
                base_url="https://api.groq.com/openai/v1",
                model="llama-3.3-70b-versatile",
            ),
            "gemini": ProviderSpec(
                name="gemini",
                env_var="GEMINI_API_KEY",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                model="gemini-2.5-flash",
            ),
        }

    def get(self, provider: str) -> ProviderSpec:
        try:
            return self._providers[provider]
        except KeyError:
            raise ValueError(f"Provider inconnu: {provider}")

    def available(self, providers_order: Iterable[str]) -> list[ProviderSpec]:
        result = []
        for provider in providers_order:
            spec = self.get(provider)
            if os.getenv(spec.env_var):
                result.append(spec)
        return result

      
class LLMClient:
    def __init__(self, registry: Optional[ProviderRegistry] = None):
        self.registry = registry or ProviderRegistry()

    def _build_client(self, spec: ProviderSpec) -> OpenAI:
        api_key = os.getenv(spec.env_var)
        if not api_key:
            raise RuntimeError(f"Clé API absente pour {spec.name}")

        return OpenAI(
            base_url=spec.base_url,
            api_key=api_key,
        )

    def generate(
        self,
        messages: list[dict],
        temperature: float = 1.0,
        json_mode: bool = False,
        providers_order: Iterable[str] = ("groq", "gemini"),
        skip_providers: Optional[set[str]] = None,
    ) -> LLMResponse:
        skip_providers = skip_providers or set()
        last_error: Optional[Exception] = None

        for provider_name in providers_order:
            if provider_name in skip_providers:
                continue

            try:
                spec = self.registry.get(provider_name)
            except ValueError as exc:
                last_error = exc
                continue

            if not os.getenv(spec.env_var):
                continue

            try:
                client = self._build_client(spec)

                kwargs = {
                    "model": spec.model,
                    "messages": messages,
                    "temperature": temperature,
                }

                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                response = client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content

                if not content:
                    raise RuntimeError(f"Réponse vide retournée par {spec.name}")

                return LLMResponse(
                    content=content,
                    provider=spec.name,
                    model=spec.model,
                )

            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(
            f"Aucun provider disponible ou valide. Dernière erreur: {last_error}"
        )

    def call_with_fallback(
        self,
        messages: list[dict],
        temperature: float = 1.0,
        json_mode: bool = False,
        providers_order: Iterable[str] = ("groq", "gemini"),
        skip_providers: Optional[set[str]] = None,
    ) -> tuple[str, str]:
        result = self.generate(
            messages=messages,
            temperature=temperature,
            json_mode=json_mode,
            providers_order=providers_order,
            skip_providers=skip_providers,
        )
        return result.content, result.provider