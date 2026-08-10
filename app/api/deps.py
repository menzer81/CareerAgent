"""FastAPI dependency injection helpers."""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.services.llm.base import BaseLLMProvider
from app.services.llm.fallback_provider import FallbackLLMProvider
from app.services.llm.openai_provider import OpenAIProvider


def get_llm_provider(settings: Settings = Depends(get_settings)) -> BaseLLMProvider | None:
    """Return configured LLM provider(s), or None for rule-based fallback.

    Modes:
    - single: backward-compatible behavior (legacy OPENAI_* or one explicit local/cloud target)
    - local_first: try local provider then cloud fallback
    - cloud_first: try cloud provider then local fallback
    """
    providers: list[BaseLLMProvider] = []

    local_provider: BaseLLMProvider | None = None
    cloud_provider: BaseLLMProvider | None = None

    if settings.local_llm_configured():
        local_provider = OpenAIProvider(
            settings,
            api_key=settings.local_openai_api_key or "ollama",
            base_url=settings.local_openai_base_url,
            model=settings.local_openai_model,
            provider_name="local",
        )

    if settings.cloud_llm_configured():
        cloud_provider = OpenAIProvider(
            settings,
            api_key=settings.cloud_openai_api_key,
            base_url=settings.cloud_openai_base_url,
            model=settings.cloud_openai_model,
            provider_name="cloud",
        )

    mode = (settings.llm_routing_mode or "single").lower()
    if mode == "local_first":
        if local_provider:
            providers.append(local_provider)
        if cloud_provider:
            providers.append(cloud_provider)
    elif mode == "cloud_first":
        if cloud_provider:
            providers.append(cloud_provider)
        if local_provider:
            providers.append(local_provider)
    else:
        # single mode: prefer explicit local/cloud, else legacy OPENAI_* settings
        if local_provider:
            providers.append(local_provider)
        elif cloud_provider:
            providers.append(cloud_provider)

    if not providers and settings.openai_api_key:
        providers.append(OpenAIProvider(settings))

    if not providers:
        return None
    if len(providers) == 1:
        return providers[0]
    return FallbackLLMProvider(providers)
