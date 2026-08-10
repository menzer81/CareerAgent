"""Resume Quality Scoring Service (Recommendation 8, Sprint 3).

Lets the system evaluate a generated resume/strategy before presenting it,
rather than relying solely on the upstream job-match score.
"""

from __future__ import annotations

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import KeywordCoverageReport, ResumeQualityScore

_QUALITY_WEIGHTS = {
    "keyword_coverage": 0.35,
    "leadership_signal_strength": 0.25,
    "ai_relevance": 0.20,
    "manager_of_managers_alignment": 0.20,
}


def _score_leadership_signal_strength(
    profile: CandidateProfileData, requirements: JobRequirements
) -> float:
    lexp = profile.leadership_experience
    score = 50.0
    if requirements.director_level_or_above and (lexp.director_level_or_above or lexp.vp_or_above):
        score += 20
    if requirements.manager_of_managers_required and lexp.manager_of_managers:
        score += 20
    if lexp.cross_functional_leadership:
        score += 5
    if lexp.board_presentations:
        score += 5
    return max(0.0, min(100.0, score))


def _score_ai_relevance(profile: CandidateProfileData, requirements: JobRequirements) -> float:
    if not requirements.ai_requirements:
        return 70.0
    ai_exp = profile.ai_experience
    signals = sum(
        [
            ai_exp.worked_with_llms,
            ai_exp.built_ai_products,
            ai_exp.ai_agents,
            ai_exp.organization_ai_adoption,
            bool(ai_exp.tools_and_frameworks),
        ]
    )
    return max(0.0, min(100.0, 40.0 + signals * 12.0))


def _score_manager_of_managers_alignment(
    profile: CandidateProfileData, requirements: JobRequirements
) -> float:
    if not requirements.manager_of_managers_required:
        return 100.0
    return 100.0 if profile.leadership_experience.manager_of_managers else 30.0


class ResumeQualityScoringService:
    """Scores overall resume/strategy quality across a few key dimensions."""

    def score(
        self,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        coverage: KeywordCoverageReport,
    ) -> ResumeQualityScore:
        keyword_coverage = coverage.coverage_percent
        leadership_signal_strength = _score_leadership_signal_strength(profile, requirements)
        ai_relevance = _score_ai_relevance(profile, requirements)
        manager_of_managers_alignment = _score_manager_of_managers_alignment(profile, requirements)

        overall = (
            keyword_coverage * _QUALITY_WEIGHTS["keyword_coverage"]
            + leadership_signal_strength * _QUALITY_WEIGHTS["leadership_signal_strength"]
            + ai_relevance * _QUALITY_WEIGHTS["ai_relevance"]
            + manager_of_managers_alignment * _QUALITY_WEIGHTS["manager_of_managers_alignment"]
        )

        return ResumeQualityScore(
            keyword_coverage=round(keyword_coverage, 1),
            leadership_signal_strength=round(leadership_signal_strength, 1),
            ai_relevance=round(ai_relevance, 1),
            manager_of_managers_alignment=round(manager_of_managers_alignment, 1),
            overall_resume_quality=round(overall, 1),
        )
