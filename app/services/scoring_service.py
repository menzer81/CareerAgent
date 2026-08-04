"""Scoring engine — primary path uses LLM; falls back to rule-based scoring."""

import logging
from difflib import SequenceMatcher

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.models.analysis import ScoringResult
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.job_analysis_repository import JobAnalysisRepository, ScoringResultRepository
from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.scoring import (
    DimensionScore,
    FullAnalysisResult,
    GapAnalysis,
    Recommendation,
    ScoringBreakdown,
)
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

# Scoring dimension weights (must sum to 1.0)
WEIGHTS = {
    "leadership": 0.20,
    "technical": 0.25,
    "cloud": 0.15,
    "ai": 0.10,
    "management_scope": 0.15,
    "industry": 0.15,
}


def _fuzzy_overlap(candidate_items: list[str], required_items: list[str]) -> tuple[float, list[str], list[str]]:
    """
    Return (ratio 0-1, matched_items, missing_items) using case-insensitive fuzzy matching.
    """
    if not required_items:
        return 1.0, [], []

    candidate_lower = [s.lower() for s in candidate_items]
    matched: list[str] = []
    missing: list[str] = []

    for req in required_items:
        req_lower = req.lower()
        found = any(
            req_lower in cand or cand in req_lower or SequenceMatcher(None, req_lower, cand).ratio() > 0.8
            for cand in candidate_lower
        )
        if found:
            matched.append(req)
        else:
            missing.append(req)

    ratio = len(matched) / len(required_items)
    return ratio, matched, missing


def _score_leadership(profile: CandidateProfileData, req: JobRequirements) -> DimensionScore:
    score = 50.0
    matched: list[str] = []
    missing: list[str] = []

    lexp = profile.leadership_experience

    if req.manager_of_managers_required:
        if lexp.manager_of_managers:
            score += 20
            matched.append("Manager of managers experience")
        else:
            score -= 20
            missing.append("Manager of managers experience required")

    if req.director_level_or_above:
        if lexp.director_level_or_above or lexp.vp_or_above:
            score += 15
            matched.append("Director-level or above experience")
        else:
            score -= 10
            missing.append("Director-level or above experience preferred")

    if req.min_team_size_managed and lexp.largest_team_managed:
        if lexp.largest_team_managed >= req.min_team_size_managed:
            score += 10
            matched.append(f"Managed teams of {lexp.largest_team_managed}+")
        else:
            score -= 10
            missing.append(f"Team size managed ({req.min_team_size_managed}) exceeds candidate's max")

    if req.p_and_l_responsibility:
        if lexp.p_and_l_responsibility:
            score += 5
            matched.append("P&L responsibility")
        else:
            missing.append("P&L responsibility mentioned in JD")

    # Bonus for executive presentations, cross-functional
    if lexp.board_presentations:
        score += 5
        matched.append("Board/executive presentation experience")
    if lexp.cross_functional_leadership:
        score += 5
        matched.append("Cross-functional leadership")

    score = max(0.0, min(100.0, score))
    explanation = (
        f"Leadership score based on manager-of-managers status, team size, and seniority level. "
        f"Matched {len(matched)} of {len(matched) + len(missing)} signals."
    )
    return DimensionScore(score=score, explanation=explanation, matched=matched, missing=missing)


def _score_technical(profile: CandidateProfileData, req: JobRequirements) -> DimensionScore:
    all_required = req.required_skills + req.preferred_skills
    candidate_tech = profile.technologies + [
        tech for entry in profile.work_history for tech in entry.technologies
    ]
    ratio, matched, missing = _fuzzy_overlap(candidate_tech, all_required)
    score = round(ratio * 100, 1)
    explanation = (
        f"Technical match: {len(matched)}/{len(all_required)} required/preferred skills found. "
        f"Based on fuzzy matching of candidate technologies against job requirements."
    )
    return DimensionScore(score=score, explanation=explanation, matched=matched, missing=missing)


def _score_cloud(profile: CandidateProfileData, req: JobRequirements) -> DimensionScore:
    if not req.cloud_requirements:
        return DimensionScore(
            score=75.0,
            explanation="No specific cloud requirements listed; neutral score applied.",
            matched=[],
            missing=[],
        )
    candidate_cloud = profile.cloud_platform_names + profile.technologies
    ratio, matched, missing = _fuzzy_overlap(candidate_cloud, req.cloud_requirements)
    score = round(ratio * 100, 1)
    explanation = f"Cloud match: {len(matched)}/{len(req.cloud_requirements)} cloud requirements met."
    return DimensionScore(score=score, explanation=explanation, matched=matched, missing=missing)


def _score_ai(profile: CandidateProfileData, req: JobRequirements) -> DimensionScore:
    if not req.ai_requirements:
        return DimensionScore(
            score=70.0,
            explanation="No specific AI requirements listed; neutral score applied.",
            matched=[],
            missing=[],
        )
    ai_exp = profile.ai_experience
    ai_signals = profile.technologies.copy()
    if ai_exp.worked_with_llms:
        ai_signals.append("LLM")
    if ai_exp.built_ai_products:
        ai_signals.append("AI product development")
    if ai_exp.rag_systems:
        ai_signals.append("RAG")
    if ai_exp.ai_agents:
        ai_signals.append("AI agents")
    ai_signals.extend(ai_exp.tools_and_frameworks)

    ratio, matched, missing = _fuzzy_overlap(ai_signals, req.ai_requirements)
    score = round(ratio * 100, 1)
    explanation = f"AI match: {len(matched)}/{len(req.ai_requirements)} AI requirements met."
    return DimensionScore(score=score, explanation=explanation, matched=matched, missing=missing)


def _score_management_scope(profile: CandidateProfileData, req: JobRequirements) -> DimensionScore:
    score = 60.0
    matched: list[str] = []
    missing: list[str] = []
    mgmt = profile.management_experience

    if mgmt.total_years_managing and mgmt.total_years_managing >= 5:
        score += 15
        matched.append(f"{mgmt.total_years_managing} years management experience")
    elif mgmt.total_years_managing:
        score += 5

    if mgmt.remote_team_management or mgmt.distributed_team_management:
        score += 10
        matched.append("Remote/distributed team management")

    if mgmt.org_design_experience:
        score += 10
        matched.append("Org design experience")

    if mgmt.executive_stakeholder_management:
        score += 5
        matched.append("Executive stakeholder management")

    if req.manager_of_managers_required and not profile.leadership_experience.manager_of_managers:
        score -= 20
        missing.append("Manager of managers required but not demonstrated")

    score = max(0.0, min(100.0, score))
    explanation = (
        f"Management scope based on years managing, remote experience, and org complexity."
    )
    return DimensionScore(score=score, explanation=explanation, matched=matched, missing=missing)


def _score_industry(profile: CandidateProfileData, req: JobRequirements) -> DimensionScore:
    if not req.industry_domain:
        return DimensionScore(
            score=70.0,
            explanation="No specific industry requirements listed; neutral score applied.",
            matched=[],
            missing=[],
        )
    candidate_industries = profile.industries + [
        ind for entry in profile.work_history for ind in entry.industries
    ]
    ratio, matched, missing = _fuzzy_overlap(candidate_industries, req.industry_domain)
    score = round(ratio * 100, 1)
    explanation = f"Industry match: {len(matched)}/{len(req.industry_domain)} domains aligned."
    return DimensionScore(score=score, explanation=explanation, matched=matched, missing=missing)


def _compute_overall(breakdown: dict[str, DimensionScore]) -> float:
    total = (
        breakdown["leadership"].score * WEIGHTS["leadership"]
        + breakdown["technical"].score * WEIGHTS["technical"]
        + breakdown["cloud"].score * WEIGHTS["cloud"]
        + breakdown["ai"].score * WEIGHTS["ai"]
        + breakdown["management_scope"].score * WEIGHTS["management_scope"]
        + breakdown["industry"].score * WEIGHTS["industry"]
    )
    return round(total, 1)


def _map_recommendation(overall: float) -> tuple[Recommendation, str]:
    if overall >= 85:
        return (
            Recommendation.STRONG_APPLY,
            f"Overall score of {overall:.0f} indicates an excellent match. "
            "Candidate's background strongly aligns with the role requirements.",
        )
    if overall >= 70:
        return (
            Recommendation.APPLY,
            f"Overall score of {overall:.0f} shows a solid match. "
            "A few gaps exist but the candidate's profile is competitive.",
        )
    if overall >= 55:
        return (
            Recommendation.STRETCH_OPPORTUNITY,
            f"Overall score of {overall:.0f} indicates a stretch. "
            "Notable gaps exist; applying is worthwhile but expectations should be calibrated.",
        )
    return (
        Recommendation.LOW_PRIORITY,
        f"Overall score of {overall:.0f} shows significant gaps. "
        "This role may not be the best use of application effort at this time.",
    )


def rule_based_score(
    profile: CandidateProfileData,
    requirements: JobRequirements,
    job_posting_id: int,
) -> FullAnalysisResult:
    """Compute scores without an LLM using heuristic rules."""
    leadership = _score_leadership(profile, requirements)
    technical = _score_technical(profile, requirements)
    cloud = _score_cloud(profile, requirements)
    ai = _score_ai(profile, requirements)
    management_scope = _score_management_scope(profile, requirements)
    industry = _score_industry(profile, requirements)

    breakdown = {
        "leadership": leadership,
        "technical": technical,
        "cloud": cloud,
        "ai": ai,
        "management_scope": management_scope,
        "industry": industry,
    }
    overall = _compute_overall(breakdown)
    recommendation, reasoning = _map_recommendation(overall)

    scoring = ScoringBreakdown(
        leadership_match=leadership,
        technical_match=technical,
        cloud_match=cloud,
        ai_match=ai,
        management_scope_match=management_scope,
        industry_match=industry,
        overall_score=overall,
        recommendation=recommendation,
        recommendation_reasoning=reasoning,
    )

    # Basic gap analysis from the rule-based scores
    missing_experiences: list[str] = []
    missing_keywords: list[str] = list(technical.missing[:10])
    missing_certifications: list[str] = []
    missing_leadership_signals: list[str] = list(leadership.missing)
    strengths = (
        [f for f in leadership.matched]
        + [f"Technical: {s}" for s in technical.matched[:5]]
    )
    risks: list[str] = []

    if overall < 70:
        risks.append(f"Overall score of {overall:.0f} is below the 'Apply' threshold.")
    if requirements.manager_of_managers_required and not profile.leadership_experience.manager_of_managers:
        missing_leadership_signals.append("Manager of managers experience not demonstrated")

    resume_focus = list(requirements.required_skills[:5])

    gap_analysis = GapAnalysis(
        missing_experiences=missing_experiences,
        missing_keywords=missing_keywords,
        missing_certifications=missing_certifications,
        missing_leadership_signals=missing_leadership_signals,
        strengths=strengths,
        risks=risks,
        resume_focus_areas=resume_focus,
    )

    return FullAnalysisResult(
        job_posting_id=job_posting_id,
        scoring=scoring,
        gap_analysis=gap_analysis,
    )


class ScoringService:
    def __init__(self, session: AsyncSession, llm: BaseLLMProvider | None) -> None:
        self.session = session
        self.profile_repo = CandidateProfileRepository(session)
        self.analysis_repo = JobAnalysisRepository(session)
        self.scoring_repo = ScoringResultRepository(session)
        self.llm = llm

    async def score_job(self, job_posting_id: int) -> ScoringResult:
        """Score a job posting against the candidate profile."""
        profile_record = await self.profile_repo.get_profile()
        if profile_record is None:
            raise NotFoundError("CandidateProfile", "singleton")

        analysis_record = await self.analysis_repo.get_by_job_id(job_posting_id)
        if analysis_record is None:
            raise AnalysisNotFoundError(job_posting_id)

        profile = CandidateProfileData.model_validate(profile_record.profile_data)
        requirements = JobRequirements.model_validate(analysis_record.requirements_data)

        if self.llm is not None:
            logger.info("Using LLM for scoring job_posting_id=%d", job_posting_id)
            result = await self.llm.score_and_analyze(profile, requirements, job_posting_id)
        else:
            logger.info("Using rule-based scoring for job_posting_id=%d", job_posting_id)
            result = rule_based_score(profile, requirements, job_posting_id)

        scoring_record = await self.scoring_repo.upsert(
            job_posting_id=job_posting_id,
            scoring_data=result.model_dump(),
        )
        return scoring_record

    async def get_score(self, job_posting_id: int) -> ScoringResult | None:
        return await self.scoring_repo.get_by_job_id(job_posting_id)
