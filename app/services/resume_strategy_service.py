"""Resume Strategy Service.

Decides *how* to frame a resume for a given job: which persona to present,
which themes/skills to emphasize, and — just as important — what to soften
or leave out (Recommendation 3: resume quality is often determined by what
is removed).
"""

from __future__ import annotations

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import AchievementSelectionResult, ResumePersona, ResumeStrategy
from app.services.achievement_selection_service import (
    DEFAULT_BOOST_MULTIPLIER,
    requirement_signals,
)

_PERSONA_THEMES: dict[ResumePersona, list[str]] = {
    ResumePersona.AI_TRANSFORMATION_LEADER: [
        "AI Transformation",
        "Developer Productivity",
        "Change Leadership",
    ],
    ResumePersona.ENGINEERING_TURNAROUND_SPECIALIST: [
        "Team Turnaround",
        "Culture Rebuilding",
        "Stakeholder Trust",
    ],
    ResumePersona.COMPLIANCE_GOVERNANCE_LEADER: [
        "Compliance Automation",
        "Risk Governance",
        "Audit Readiness",
    ],
    ResumePersona.TECHNICAL_DELIVERY_LEADER: [
        "Delivery Execution",
        "Technical Leadership",
        "Engineering Excellence",
    ],
    ResumePersona.GROWTH_ENGINEERING_LEADER: [
        "Scaling Teams",
        "Organizational Growth",
        "Engineering Enablement",
    ],
    ResumePersona.CLOUD_TRANSFORMATION_LEADER: [
        "Cloud Migration",
        "Cloud Enablement",
        "Infrastructure Modernization",
    ],
    ResumePersona.DIRECTOR_TRACK_CANDIDATE: [
        "Manager of Managers",
        "Organizational Leadership",
        "Executive Stakeholder Management",
    ],
}

_LOW_RELEVANCE_THRESHOLD = 50.0
_MAX_DEEMPHASIZED_TECH = 3


def select_persona(requirements: JobRequirements) -> ResumePersona:
    """Pick the resume persona that best fits a job's requirements (Recommendation 6)."""
    text = (requirements.role_summary or "").lower()
    keywords = [k.lower() for k in requirements.important_keywords]
    industries = [i.lower() for i in requirements.industry_domain]
    ai_reqs = [a.lower() for a in requirements.ai_requirements]

    compliance_signals = {"compliance", "soc 2", "soc2", "iso 27001", "governance", "audit"}
    if (
        any(sig in kw for kw in keywords + industries for sig in compliance_signals)
        or "compliance" in text
    ):
        return ResumePersona.COMPLIANCE_GOVERNANCE_LEADER

    if ai_reqs or any("ai" in kw or "copilot" in kw or "llm" in kw for kw in keywords) or "ai" in text.split():
        return ResumePersona.AI_TRANSFORMATION_LEADER

    if any(w in text for w in ("turnaround", "underperform", "rebuild", "restructur")):
        return ResumePersona.ENGINEERING_TURNAROUND_SPECIALIST

    if any(w in text for w in ("hypergrowth", "scale", "scaling", "growth stage", "rapid growth")):
        return ResumePersona.GROWTH_ENGINEERING_LEADER

    if requirements.director_level_or_above or requirements.manager_of_managers_required:
        return ResumePersona.DIRECTOR_TRACK_CANDIDATE

    if requirements.cloud_requirements or any(
        w in kw for kw in keywords + industries for w in ("cloud", "aws", "azure", "migration")
    ):
        return ResumePersona.CLOUD_TRANSFORMATION_LEADER

    return ResumePersona.TECHNICAL_DELIVERY_LEADER


def _build_emphasize(requirements: JobRequirements) -> list[str]:
    emphasize: list[str] = []
    if requirements.manager_of_managers_required or requirements.director_level_or_above:
        emphasize.append("manager-of-managers")
    if requirements.ai_requirements:
        emphasize.append("AI Transformation")
    if requirements.p_and_l_responsibility:
        emphasize.append("P&L ownership")
    if requirements.cloud_requirements:
        emphasize.append("cloud enablement")
    return emphasize


def _build_exclusions(
    requirements: JobRequirements,
    profile: CandidateProfileData,
    selection: AchievementSelectionResult,
) -> tuple[list[str], list[str]]:
    """Recommendation 3: what to deemphasize (soften) vs. omit (leave out)."""
    signals_lower = {s.lower() for s in requirement_signals(requirements)}

    unmatched_tech = [
        tech for tech in profile.technologies if tech.lower() not in signals_lower
    ][:_MAX_DEEMPHASIZED_TECH]
    deemphasize = ["legacy technologies"] if unmatched_tech else []
    deemphasize.extend(unmatched_tech)

    low_relevance_ids = [
        r.id
        for r in selection.rankings
        if r.id not in selection.selected_accomplishment_ids
        and r.ranking_score < _LOW_RELEVANCE_THRESHOLD
    ]
    omit = ["low-relevance accomplishments"] + low_relevance_ids if low_relevance_ids else []

    return deemphasize, omit


class ResumeStrategyService:
    """Builds a ``ResumeStrategy`` from job requirements, profile, and achievement selection."""

    def build_strategy(
        self,
        job_posting_id: int,
        requirements: JobRequirements,
        profile: CandidateProfileData,
        selection: AchievementSelectionResult,
        boost_multiplier: float = DEFAULT_BOOST_MULTIPLIER,
    ) -> ResumeStrategy:
        persona = select_persona(requirements)
        key_themes = list(_PERSONA_THEMES[persona])

        # Surface up to two important job keywords not already represented as themes.
        for kw in requirements.important_keywords:
            if len(key_themes) >= 5:
                break
            if kw.lower() not in {t.lower() for t in key_themes}:
                key_themes.append(kw)

        emphasize = _build_emphasize(requirements)
        deemphasize, omit = _build_exclusions(requirements, profile, selection)

        return ResumeStrategy(
            job_posting_id=job_posting_id,
            persona=persona,
            key_themes=key_themes,
            emphasize=emphasize,
            deemphasize=deemphasize,
            omit=omit,
            boosted_accomplishment_ids=selection.boosted_accomplishment_ids,
            boost_multiplier=boost_multiplier,
        )
