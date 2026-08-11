"""Fallback/chained LLM provider.

Tries providers in order for each operation. This allows local-first operation
(Ollama/LM Studio) with cloud fallback (OpenAI/Azure/OpenRouter) when the local
model is unavailable or returns invalid output.
"""

import logging

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import AccomplishmentEntry, GeneratedResumeContent, ResumeStrategy
from app.schemas.scoring import FullAnalysisResult
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class FallbackLLMProvider(BaseLLMProvider):
    def __init__(self, providers: list[BaseLLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackLLMProvider requires at least one provider")
        self.providers = providers

    async def extract_job_requirements(self, job_text: str) -> JobRequirements:
        last_error: Exception | None = None
        for idx, provider in enumerate(self.providers, start=1):
            try:
                return await provider.extract_job_requirements(job_text)
            except Exception as exc:  # pragma: no cover - defensive fallback behavior
                last_error = exc
                logger.warning("LLM extract failed on provider %d/%d: %s", idx, len(self.providers), exc)
        assert last_error is not None
        raise last_error

    async def score_and_analyze(
        self,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        job_posting_id: int,
    ) -> FullAnalysisResult:
        last_error: Exception | None = None
        for idx, provider in enumerate(self.providers, start=1):
            try:
                return await provider.score_and_analyze(profile, requirements, job_posting_id)
            except Exception as exc:  # pragma: no cover - defensive fallback behavior
                last_error = exc
                logger.warning("LLM scoring failed on provider %d/%d: %s", idx, len(self.providers), exc)
        assert last_error is not None
        raise last_error

    async def generate_resume_content(
        self,
        job_posting_id: int,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        strategy: ResumeStrategy,
        selected_accomplishments: list[AccomplishmentEntry],
    ) -> GeneratedResumeContent:
        last_error: Exception | None = None
        for idx, provider in enumerate(self.providers, start=1):
            try:
                return await provider.generate_resume_content(
                    job_posting_id, profile, requirements, strategy, selected_accomplishments
                )
            except Exception as exc:  # pragma: no cover - defensive fallback behavior
                last_error = exc
                logger.warning(
                    "LLM resume content generation failed on provider %d/%d: %s",
                    idx,
                    len(self.providers),
                    exc,
                )
        assert last_error is not None
        raise last_error
