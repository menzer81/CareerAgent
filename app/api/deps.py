"""FastAPI dependency injection helpers."""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.services.llm.base import BaseLLMProvider
from app.services.llm.openai_provider import OpenAIProvider


def get_llm_provider(settings: Settings = Depends(get_settings)) -> BaseLLMProvider | None:
    """Return LLM provider if configured, otherwise None (triggers rule-based fallback)."""
    if settings.llm_configured():
        return OpenAIProvider(settings)
    return None
