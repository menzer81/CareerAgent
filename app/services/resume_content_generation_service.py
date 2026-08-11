"""Resume Content Generation Service.

Implements the "OpenAI Resume Generator" stage from the recommended
architecture: rewrites the executive summary and experience/accomplishment
bullets for a specific job, using an LLM when one is configured. When no LLM
is available (or the LLM call fails), falls back to the unmodified static
content already present in the candidate profile / accomplishment bank —
preserving today's behavior end-to-end without requiring an API key.

After LLM generation, a hallucination-scrub pass replaces any accomplishment
bullet that contains numbers not traceable to the source data with the safe
static text, preventing fabricated metrics from reaching the rendered resume.
"""

from __future__ import annotations

import logging
import re

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

_NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")


def _extract_numbers(text: str) -> set[str]:
    return {m.replace(",", "") for m in _NUMBER_PATTERN.findall(text)}


def _source_numbers(acc: AccomplishmentEntry) -> set[str]:
    """All numbers legitimately present in this accomplishment's source data."""
    numbers: set[str] = set()
    for text in [acc.title, acc.impact]:
        numbers |= _extract_numbers(text)
    for value in acc.metrics.values():
        numbers |= _extract_numbers(str(value))
    return numbers


def _safe_static_bullet(acc: AccomplishmentEntry) -> str:
    return f"{acc.title}: {acc.impact}" if acc.impact else acc.title


def _scrub_hallucinated_bullets(
    content: GeneratedResumeContent,
    selected_accomplishments: list[AccomplishmentEntry],
) -> GeneratedResumeContent:
    """Replace any accomplishment bullet whose numbers can't be traced to source data.

    Numbers that appear in generated text but are absent from the accomplishment's
    title, impact, and metrics dict are fabrications. The entire bullet is swapped
    for the safe static text so no invented metrics reach the rendered resume.
    """
    if content.generated_by != "llm":
        return content

    acc_by_id = {acc.id: acc for acc in selected_accomplishments}
    scrubbed_bullets: list[GeneratedAccomplishmentBullet] = []
    any_scrubbed = False

    for bullet in content.accomplishment_bullets:
        acc = acc_by_id.get(bullet.id)
        if acc is None:
            scrubbed_bullets.append(bullet)
            continue

        generated_numbers = _extract_numbers(bullet.generated_text)
        fabricated = generated_numbers - _source_numbers(acc)

        if fabricated:
            safe_text = _safe_static_bullet(acc)
            logger.warning(
                "Hallucination detected in accomplishment '%s': fabricated number(s) %s — "
                "replacing generated bullet with static text. "
                "Fabricated: %r  Safe: %r",
                acc.id,
                sorted(fabricated),
                bullet.generated_text,
                safe_text,
            )
            scrubbed_bullets.append(GeneratedAccomplishmentBullet(id=acc.id, generated_text=safe_text))
            any_scrubbed = True
        else:
            scrubbed_bullets.append(bullet)

    if not any_scrubbed:
        return content

    return content.model_copy(update={"accomplishment_bullets": scrubbed_bullets})


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
            generated_text=_safe_static_bullet(acc),
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
            content = await self.llm.generate_resume_content(
                job_posting_id, profile, requirements, strategy, selected_accomplishments
            )
            return _scrub_hallucinated_bullets(content, selected_accomplishments)
        except Exception as exc:
            logger.warning(
                "LLM resume content generation failed for job_posting_id=%d; "
                "falling back to static content: %s",
                job_posting_id,
                exc,
            )
            return _static_content(job_posting_id, profile, selected_accomplishments)
