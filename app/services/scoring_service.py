"""Scoring engine — primary path uses LLM; falls back to rule-based scoring."""

import asyncio
import logging
import re
from difflib import SequenceMatcher

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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

_DELIM_RE = re.compile(r"[^a-z0-9]+")

_TERM_SYNONYMS = {
    "ai/ml": "ai ml",
    "mlops": "ml ops",
    "qa/qc": "qa qc",
    "sdlc": "software development lifecycle",
    "ci/cd": "continuous integration continuous delivery",
    "cloud-native": "cloud native",
    "manager of managers": "manager-of-managers",
}


def _management_oriented_role(req: JobRequirements) -> bool:
    managerial_terms = [*req.required_skills, *req.preferred_skills, *req.important_keywords]
    managerial_hits = sum(1 for term in managerial_terms if _is_managerial_skill(term))
    return bool(
        req.manager_of_managers_required
        or req.director_level_or_above
        or (req.min_team_size_managed or 0) >= 10
        or managerial_hits >= 3
    )


def _normalize_term(value: str) -> str:
    normalized = value.strip().lower()
    normalized = _TERM_SYNONYMS.get(normalized, normalized)
    normalized = _DELIM_RE.sub(" ", normalized)
    normalized = " ".join(normalized.split())
    return normalized


def _has_leadership_scope(profile: CandidateProfileData) -> bool:
    mgmt = profile.management_experience
    lexp = profile.leadership_experience
    return bool(
        (mgmt.total_years_managing and mgmt.total_years_managing >= 2)
        or lexp.manager_of_managers
        or mgmt.org_design_experience
    )


def _is_managerial_skill(term: str) -> bool:
    t = _normalize_term(term)
    managerial_keywords = (
        "agile",
        "scrum",
        "kanban",
        "software development lifecycle",
        "sdlc",
        "stakeholder",
        "capacity",
        "resource",
        "quality",
        "process",
        "delivery",
        "operations",
        "qa",
        "qc",
        "leadership",
        "reporting",
    )
    return any(k in t for k in managerial_keywords)


def _collect_candidate_skill_signals(profile: CandidateProfileData) -> list[str]:
    signals: list[str] = []

    signals.extend(profile.technologies)
    signals.extend(profile.industries)

    if profile.ai_transformation_experience:
        signals.extend(profile.ai_transformation_experience.highlights)

    if profile.ai_experience:
        signals.extend(profile.ai_experience.tools_and_frameworks)
        signals.extend(profile.ai_experience.ai_highlights)
        signals.extend(profile.ai_experience.agent_use_cases)
        signals.extend(profile.ai_experience.leadership_impact)

    if profile.management_experience:
        signals.extend(profile.management_experience.management_highlights)

    if profile.leadership_experience:
        signals.extend(profile.leadership_experience.leadership_highlights)

    for entry in profile.work_history:
        signals.append(entry.title)
        signals.append(entry.description)
        signals.extend(entry.technologies)
        signals.extend(entry.leadership_areas)
        signals.extend(entry.key_accomplishments)
        signals.extend(entry.industries)

    for cert in profile.certifications:
        signals.append(cert.name)

    for cloud in profile.cloud_platforms:
        signals.append(cloud.platform)
        signals.extend(cloud.areas)

    return [s for s in signals if s]


def _fuzzy_overlap(candidate_items: list[str], required_items: list[str]) -> tuple[float, list[str], list[str]]:
    """
    Return (ratio 0-1, matched_items, missing_items) using case-insensitive fuzzy matching.
    """
    if not required_items:
        return 1.0, [], []

    candidate_lower = [_normalize_term(s) for s in candidate_items if s]
    matched: list[str] = []
    missing: list[str] = []

    for req in required_items:
        req_lower = _normalize_term(req)
        found = any(
            (
                (len(req_lower) >= 4 and req_lower in cand)
                or (len(cand) >= 4 and cand in req_lower)
                or (len(req_lower) < 4 and req_lower in cand.split())
                or SequenceMatcher(None, req_lower, cand).ratio() > 0.8
            )
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
            # Soften this penalty for seasoned managers who may not have held
            # the title yet but have adjacent leadership scope.
            mgmt_years = profile.management_experience.total_years_managing or 0
            if mgmt_years >= 7 and profile.management_experience.executive_stakeholder_management:
                score -= 3
                missing.append("Director-level title not explicit (adjacent scope detected)")
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
    candidate_tech = _collect_candidate_skill_signals(profile)
    ratio, matched, missing = _fuzzy_overlap(candidate_tech, all_required)
    # For leadership-heavy jobs, reward managerial/process signal overlap.
    if all_required and _has_leadership_scope(profile):
        managerial_hits = sum(1 for skill in all_required if _is_managerial_skill(skill))
        if managerial_hits:
            ratio = min(1.0, ratio + (0.08 * managerial_hits / max(1, len(all_required))))
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
    for cloud in profile.cloud_platforms:
        candidate_cloud.extend(cloud.areas)
    for cert in profile.certifications:
        candidate_cloud.append(cert.name)
    ratio, matched, missing = _fuzzy_overlap(candidate_cloud, req.cloud_requirements)
    score = round(ratio * 100, 1)
    if (
        _has_leadership_scope(profile)
        and req.cloud_requirements
        and (req.director_level_or_above or req.manager_of_managers_required or (req.min_team_size_managed or 0) >= 20)
        and score < 55
    ):
        # Leadership roles often require cloud direction rather than deep
        # implementation of every listed platform.
        score = 55.0
    elif (
        _has_leadership_scope(profile)
        and _management_oriented_role(req)
        and len(req.cloud_requirements) >= 2
        and score < 45
    ):
        # For manager roles, partial cloud overlap (plus leadership background)
        # is often sufficient for initial screening.
        score = 45.0
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
    if ai_exp.copilot_champion:
        ai_signals.append("AI-assisted development")
    if ai_exp.organization_ai_adoption:
        ai_signals.append("organizational AI adoption")
    ai_signals.extend(ai_exp.ai_highlights)
    ai_signals.extend(ai_exp.agent_use_cases)
    ai_signals.extend(ai_exp.leadership_impact)
    ai_signals.extend(ai_exp.tools_and_frameworks)

    ratio, matched, missing = _fuzzy_overlap(ai_signals, req.ai_requirements)
    score = round(ratio * 100, 1)
    ai_req_norm = {_normalize_term(x) for x in req.ai_requirements}
    if (
        _has_leadership_scope(profile)
        and _management_oriented_role(req)
        and profile.ai_transformation_experience
        and ("ai ml" in ai_req_norm or "ml ops" in ai_req_norm or "automation" in ai_req_norm)
        and score < 50
    ):
        score = 50.0
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
    if score == 0.0 and (req.director_level_or_above or req.manager_of_managers_required or (req.min_team_size_managed or 0) >= 20):
        req_lower = {_normalize_term(x) for x in req.industry_domain}
        cand_lower = {_normalize_term(x) for x in candidate_industries}
        regulated_req = {"healthcare", "diagnostics", "pharmacy", "government", "banking", "fintech"}
        regulated_cand = {"compliance", "regulated", "government", "fintech", "payments"}
        if req_lower.intersection(regulated_req) and cand_lower.intersection(regulated_cand):
            score = 40.0
            matched.append("Regulated-industry adjacency")
    elif score == 0.0 and _management_oriented_role(req):
        req_lower = {_normalize_term(x) for x in req.industry_domain}
        cand_lower = {_normalize_term(x) for x in candidate_industries}
        if ({"healthcare", "diagnostics"}.intersection(req_lower)) and (
            {"compliance", "regulated", "payments", "fintech"}.intersection(cand_lower)
        ):
            score = 35.0
            matched.append("Healthcare-regulated adjacency")
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
        self.llm_scoring_timeout_seconds = get_settings().llm_scoring_timeout_seconds

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
            try:
                result = await asyncio.wait_for(
                    self.llm.score_and_analyze(profile, requirements, job_posting_id),
                    timeout=self.llm_scoring_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "LLM scoring timed out after %ds for job_posting_id=%d; falling back to rule-based scoring",
                    self.llm_scoring_timeout_seconds,
                    job_posting_id,
                )
                result = rule_based_score(profile, requirements, job_posting_id)
            except Exception as exc:
                logger.warning(
                    "LLM scoring failed for job_posting_id=%d; falling back to rule-based scoring: %s",
                    job_posting_id,
                    exc,
                )
                result = rule_based_score(profile, requirements, job_posting_id)
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
