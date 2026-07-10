"""Map generic provider options onto a Pydantic AI model.

Native providers use the "provider:model" string form (Pydantic AI resolves
credentials from the provider's conventional env var, which we set from the
generic `api_key` option). A `base_url` switches to OpenAIChatModel against
any OpenAI-compatible endpoint (Ollama, OpenRouter, vLLM, ...).
"""

from __future__ import annotations

import os

from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from concierge.config import Settings

_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def _build(settings: Settings, model_name: str) -> Model | str:
    if settings.base_url:
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(
                base_url=settings.base_url,
                api_key=settings.api_key or "unused",
            ),
        )
    env_var = _API_KEY_ENV.get(settings.provider)
    if env_var and settings.api_key:
        os.environ[env_var] = settings.api_key
    return f"{settings.provider}:{model_name}"


def build_model(settings: Settings) -> Model | str:
    return _build(settings, settings.model)


def build_title_model(settings: Settings) -> Model | str:
    return _build(settings, settings.effective_title_model)
