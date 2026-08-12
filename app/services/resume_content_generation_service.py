"""Resume Content Generation Service.

Implements the "OpenAI Resume Generator" stage from the recommended
architecture: rewrites the executive summary and experience/accomplishment
bullets for a specific job, using an LLM when one is configured. When no LLM
is available (or the LLM call fails), falls back to the unmodified static
content already present in the candidate profile / accomplishment bank --
preserving today's behavior end-to-end without requiring an API key.

After LLM generation, a hallucination-scrub pass replaces any accomplishment
bullet or experience bullet that contains numbers not traceable to the source
data with the safe static text, preventing fabricated metrics from reaching
the rendered resume.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData, WorkHistoryEntry
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
_COMPANY_NOISE = re.compile(r"[^a-z0-9\s]")
_COMPANY_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|corp|co|associates|group|solutions|services|technologies|tech)\b"
)
_SUMMARY_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_AI_TERM_PATTERN = re.compile(r"\b(ai|copilot|llm|agent(?:s)?|automation|machine learning|ml)\b", re.IGNORECASE)
_LEADERSHIP_TERM_PATTERN = re.compile(r"\b(lead|leadership|manager|management|director|vp|team|stakeholder)\b", re.IGNORECASE)
_MIN_SUMMARY_SENTENCES = 4
_MAX_SUMMARY_SENTENCES = 6
_MIN_AI_MENTIONS_WHEN_AI_HEAVY = 2


def _normalise_company(name: str) -> str:
    """Reduce a company name to a comparable token for fuzzy matching.

    Strips punctuation, common legal suffixes, and extra whitespace so that
    "J.J. Keller & Associates" and "J.J. Keller" both normalise to "jj keller".
    """
    lowered = name.lower()
    no_punct = _COMPANY_NOISE.sub(" ", lowered)
    no_suffix = _COMPANY_SUFFIXES.sub(" ", no_punct)
    return " ".join(no_suffix.split())


def _build_work_by_normalised_company(
    profile: CandidateProfileData,
) -> dict[str, WorkHistoryEntry]:
    """Index work history by normalised company name for fuzzy lookup."""
    return {_normalise_company(e.company): e for e in profile.work_history}


def _extract_numbers(text: str) -> set[str]:
    """Extract all numeric tokens from text, normalised to integer strings where possible.

    Strips commas (e.g. "1,300" → "1300") and trailing ".0" from whole-number
    floats (e.g. "30.0" → "30") so that Pydantic-coerced metric floats compare
    equal to the plain integers that appear in generated prose.
    """
    result: set[str] = set()
    for m in _NUMBER_PATTERN.findall(str(text)):
        normalised = m.replace(",", "")
        # Collapse whole-number floats: "30.0" → "30", "500.0" → "500"
        if "." in normalised:
            try:
                as_float = float(normalised)
                if as_float == int(as_float):
                    normalised = str(int(as_float))
            except ValueError:
                pass
        result.add(normalised)
    return result


def _source_numbers(
    acc: AccomplishmentEntry,
    work_entry: WorkHistoryEntry | None = None,
) -> set[str]:
    """All numbers legitimately present in this accomplishment's source data.

    Also includes numbers from the matching work history entry when provided,
    since generated bullets may correctly combine data from both sources
    (e.g. referencing both an accomplishment metric and a role's key_accomplishments).
    """
    numbers: set[str] = set()
    for text in [acc.title, acc.impact]:
        numbers |= _extract_numbers(text)
    for value in acc.metrics.values():
        numbers |= _extract_numbers(str(value))
    if work_entry is not None:
        numbers |= _source_numbers_for_work_entry(work_entry)
    return numbers


def _source_numbers_for_work_entry(entry: WorkHistoryEntry) -> set[str]:
    """All numbers legitimately present in a work history entry's source data."""
    numbers: set[str] = set()
    for text in entry.key_accomplishments:
        numbers |= _extract_numbers(text)
    numbers |= _extract_numbers(entry.description)
    for field in (entry.team_size, entry.direct_reports, entry.manager_reports,
                  entry.largest_org_influence, entry.projects_managed, entry.budget_usd):
        if field is not None:
            numbers |= _extract_numbers(str(field))
    return numbers


def _safe_static_bullet(acc: AccomplishmentEntry) -> str:
    return f"{acc.title}: {acc.impact}" if acc.impact else acc.title


def _sentence_count(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    parts = [segment.strip() for segment in _SUMMARY_SENTENCE_SPLIT.split(cleaned) if segment.strip()]
    return len(parts)


def _is_ai_heavy_or_equal(requirements: JobRequirements) -> bool:
    role_summary = (requirements.role_summary or "")
    ai_count = len(requirements.ai_requirements)
    ai_count += sum(1 for kw in requirements.important_keywords if _AI_TERM_PATTERN.search(kw))
    if _AI_TERM_PATTERN.search(role_summary):
        ai_count += 1

    leadership_count = len(requirements.leadership_requirements)
    leadership_count += sum(1 for kw in requirements.important_keywords if _LEADERSHIP_TERM_PATTERN.search(kw))
    if requirements.manager_of_managers_required or requirements.director_level_or_above:
        leadership_count += 1
    if _LEADERSHIP_TERM_PATTERN.search(role_summary):
        leadership_count += 1

    return ai_count > 0 and ai_count >= leadership_count


def _summary_quality_failures(summary: str, requirements: JobRequirements) -> list[str]:
    failures: list[str] = []
    sentence_count = _sentence_count(summary)
    if sentence_count < _MIN_SUMMARY_SENTENCES or sentence_count > _MAX_SUMMARY_SENTENCES:
        failures.append(
            f"sentence_count={sentence_count} (expected {_MIN_SUMMARY_SENTENCES}-{_MAX_SUMMARY_SENTENCES})"
        )

    if len((summary or "").strip()) < 80:
        failures.append("summary_too_short_chars")

    if _is_ai_heavy_or_equal(requirements):
        ai_mentions = len(_AI_TERM_PATTERN.findall(summary or ""))
        if ai_mentions < _MIN_AI_MENTIONS_WHEN_AI_HEAVY:
            failures.append(
                f"ai_mentions={ai_mentions} (expected >= {_MIN_AI_MENTIONS_WHEN_AI_HEAVY})"
            )

    return failures


async def _call_with_optional_summary_guidance(
    llm: BaseLLMProvider,
    job_posting_id: int,
    profile: CandidateProfileData,
    requirements: JobRequirements,
    strategy: ResumeStrategy,
    selected_accomplishments: list[AccomplishmentEntry],
    summary_guidance: str | None,
) -> GeneratedResumeContent:
    guided_method = getattr(llm, "generate_resume_content_with_guidance", None)
    if summary_guidance and callable(guided_method):
        return await guided_method(
            job_posting_id,
            profile,
            requirements,
            strategy,
            selected_accomplishments,
            summary_guidance,
        )
    return await llm.generate_resume_content(
        job_posting_id,
        profile,
        requirements,
        strategy,
        selected_accomplishments,
    )


def _scrub_hallucinated_bullets(
    content: GeneratedResumeContent,
    selected_accomplishments: list[AccomplishmentEntry],
    profile: CandidateProfileData,
) -> GeneratedResumeContent:
    """Replace bullets whose numbers can't be traced back to source data.

    Covers both accomplishment_bullets (keyed by id) and experience_bullets
    (keyed by company name). Any bullet containing a number absent from its
    source entry is swapped for the original static text so no invented
    metrics reach the rendered resume.
    """
    if content.generated_by != "llm":
        return content

    # --- accomplishment bullets ---
    acc_by_id = {acc.id: acc for acc in selected_accomplishments}
    work_by_norm = _build_work_by_normalised_company(profile)
    scrubbed_acc_bullets: list[GeneratedAccomplishmentBullet] = []
    any_scrubbed = False

    for bullet in content.accomplishment_bullets:
        acc = acc_by_id.get(bullet.id)
        if acc is None:
            scrubbed_acc_bullets.append(bullet)
            continue
        # Use normalised company lookup so "J.J. Keller" matches "J.J. Keller & Associates"
        matching_work = work_by_norm.get(_normalise_company(acc.company))
        fabricated = _extract_numbers(bullet.generated_text) - _source_numbers(acc, matching_work)
        if fabricated:
            safe_text = _safe_static_bullet(acc)
            logger.warning(
                "Hallucination in accomplishment '%s': fabricated number(s) %s -- "
                "replacing with static text. Fabricated: %r  Safe: %r",
                acc.id, sorted(fabricated), bullet.generated_text, safe_text,
            )
            scrubbed_acc_bullets.append(GeneratedAccomplishmentBullet(id=acc.id, generated_text=safe_text))
            any_scrubbed = True
        else:
            scrubbed_acc_bullets.append(bullet)

    # --- experience bullets ---
    scrubbed_exp_bullets: list[GeneratedWorkHistoryBullets] = []

    for exp in content.experience_bullets:
        work_entry = work_by_norm.get(_normalise_company(exp.company))
        if work_entry is None:
            scrubbed_exp_bullets.append(exp)
            continue

        source_nums = _source_numbers_for_work_entry(work_entry)
        clean_bullets: list[str] = []
        for bullet in exp.bullets:
            fabricated = _extract_numbers(bullet) - source_nums
            if fabricated:
                logger.warning(
                    "Hallucination in experience bullets for '%s': fabricated number(s) %s -- "
                    "dropping generated bullet. Fabricated: %r",
                    exp.company, sorted(fabricated), bullet,
                )
                any_scrubbed = True
            else:
                clean_bullets.append(bullet)

        # If all generated bullets were clean keep them; if any were scrubbed
        # drop the entire company entry so ResumeDocumentService falls back to
        # the raw key_accomplishments rather than a partially-scrubbed list.
        if len(clean_bullets) == len(exp.bullets):
            scrubbed_exp_bullets.append(exp)
        else:
            logger.warning(
                "One or more experience bullets for '%s' contained fabricated numbers; "
                "falling back to raw profile key_accomplishments for this role.",
                exp.company,
            )
            # Omit this company so the document service uses entry.key_accomplishments.

    if not any_scrubbed:
        return content

    return content.model_copy(update={
        "accomplishment_bullets": scrubbed_acc_bullets,
        "experience_bullets": scrubbed_exp_bullets,
    })


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
            content = await _call_with_optional_summary_guidance(
                self.llm,
                job_posting_id,
                profile,
                requirements,
                strategy,
                selected_accomplishments,
                None,
            )
            failures = _summary_quality_failures(content.executive_summary, requirements)
            if failures:
                logger.warning(
                    "Executive summary quality check failed for job_posting_id=%d (%s); retrying once with stricter guidance.",
                    job_posting_id,
                    "; ".join(failures),
                )
                retry_guidance = (
                    "Corrective guidance: executive_summary must be 4-6 sentences, include role fit, "
                    "leadership/delivery strengths, and job-relevant domain strengths grounded in candidate data. "
                    "If AI demand is greater than or equal to leadership demand, include at least two AI mentions."
                )
                retry_content = await _call_with_optional_summary_guidance(
                    self.llm,
                    job_posting_id,
                    profile,
                    requirements,
                    strategy,
                    selected_accomplishments,
                    retry_guidance,
                )
                retry_failures = _summary_quality_failures(retry_content.executive_summary, requirements)
                if retry_failures:
                    logger.warning(
                        "Executive summary quality retry failed for job_posting_id=%d (%s); falling back to static content.",
                        job_posting_id,
                        "; ".join(retry_failures),
                    )
                    return _static_content(job_posting_id, profile, selected_accomplishments)
                content = retry_content

            return _scrub_hallucinated_bullets(content, selected_accomplishments, profile)
        except Exception as exc:
            logger.warning(
                "LLM resume content generation failed for job_posting_id=%d; "
                "falling back to static content: %s",
                job_posting_id,
                exc,
            )
            return _static_content(job_posting_id, profile, selected_accomplishments)
