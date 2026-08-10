"""Resume Data Model Service (Recommendation 1).

Assembles the intermediate, renderer-agnostic ``ResumeDataModel`` — pure
business-logic output (what to say, not how to format it) — from the job
requirements, candidate profile, resume strategy, achievement selection, and
keyword coverage report. Everything here is a pointer back into the candidate
profile / accomplishment bank; nothing is invented.
"""

from __future__ import annotations

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import (
    AccomplishmentEntry,
    AchievementSelectionResult,
    KeywordCoverageReport,
    ResumeDataModel,
    ResumeStrategy,
)

_LONG_RESUME_THRESHOLD = 6


class ResumeDataModelService:
    """Builds the ``ResumeDataModel`` from upstream pipeline outputs."""

    def build(
        self,
        job_posting_id: int,
        requirements: JobRequirements,
        profile: CandidateProfileData,
        strategy: ResumeStrategy,
        selection: AchievementSelectionResult,
        coverage: KeywordCoverageReport,
        accomplishments: list[AccomplishmentEntry] | None = None,
    ) -> ResumeDataModel:
        selected_work_history = [entry.company for entry in profile.work_history]

        candidate_skills_lower = {t.lower() for t in profile.technologies}
        required_skills = requirements.required_skills + requirements.preferred_skills
        skills_to_highlight = [
            skill for skill in required_skills if skill.lower() in candidate_skills_lower
        ]
        # Always include emphasized themes that are demonstrable (already candidate skills).
        for theme in strategy.emphasize:
            if theme not in skills_to_highlight:
                skills_to_highlight.append(theme)

        # Companies not tied to any selected accomplishment are candidates to shorten,
        # excluding the current role which should always stay prominent.
        selected_ids = set(selection.selected_accomplishment_ids)
        companies_with_selected_accomplishments = {
            acc.company.lower() for acc in (accomplishments or []) if acc.id in selected_ids
        }

        def _company_is_featured(company: str) -> bool:
            company_lower = company.lower()
            return any(
                featured in company_lower or company_lower in featured
                for featured in companies_with_selected_accomplishments
            )

        roles_to_shorten = [
            entry.company
            for entry in profile.work_history
            if not entry.is_current and not _company_is_featured(entry.company)
        ]

        resume_length = (
            "3-page" if len(profile.work_history) > _LONG_RESUME_THRESHOLD else "2-page"
        )

        return ResumeDataModel(
            job_posting_id=job_posting_id,
            executive_summary=profile.summary,
            selected_work_history=selected_work_history,
            selected_accomplishments=selection.selected_accomplishment_ids,
            skills_to_highlight=skills_to_highlight,
            keywords_to_include=coverage.matched_keywords,
            roles_to_shorten=roles_to_shorten,
            resume_length=resume_length,
        )
