"""Resume Content Generation Service.

Implements the "OpenAI Resume Generator" stage from the recommended
architecture: rewrites the executive summary and experience/accomplishment
bullets for a specific job, using an LLM when one is configured. When no LLM
is available (or the LLM call fails), falls back to the unmodified static
content already present in the candidate profile / accomplishment bank —
preserving today's behavior end-to-end without requiring an API key.
"""

from __future__ import annotations

import logging

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import (
    AccomplishmentEntry,
    GeneratedAccomplishmentBullet,
    GeneratedResumeContent,
    GeneratedWorkHistoryBullets,
    ResumeStrategy,
)
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


def _static_content(
    job_posting_id: int,
    profile: CandidateProfileData,
    selected_accomplishments: list[AccomplishmentEntry],
) -> GeneratedResumeContent:
    """Build content straight from the profile/accomplishment bank, unmodified."""
    experience_bullets = [
        GeneratedWorkHistoryBullets(company=entry.company, bullets=list(entry.key_accomplishments))
        for entry in profile.work_history
        if entry.key_accomplishments
    ]
    accomplishment_bullets = [
        GeneratedAccomplishmentBullet(
            id=acc.id,
            generated_text=f"{acc.title}: {acc.impact}" if acc.impact else acc.title,
        )
        for acc in selected_accomplishments
    ]
    return GeneratedResumeContent(
        job_posting_id=job_posting_id,
        executive_summary=profile.summary,
        experience_bullets=experience_bullets,
        accomplishment_bullets=accomplishment_bullets,
        generated_by="static",
    )


class ResumeContentGenerationService:
    """Generates tailored resume prose, falling back to static content when no LLM is available."""

    def __init__(self, llm: BaseLLMProvider | None = None) -> None:
        self.llm = llm

    async def generate(
        self,
        job_posting_id: int,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        strategy: ResumeStrategy,
        selected_accomplishments: list[AccomplishmentEntry],
    ) -> GeneratedResumeContent:
        if self.llm is None:
            return _static_content(job_posting_id, profile, selected_accomplishments)

        try:
            return await self.llm.generate_resume_content(
                job_posting_id, profile, requirements, strategy, selected_accomplishments
            )
        except Exception as exc:
            logger.warning(
                "LLM resume content generation failed for job_posting_id=%d; "
                "falling back to static content: %s",
                job_posting_id,
                exc,
            )
            return _static_content(job_posting_id, profile, selected_accomplishments)
