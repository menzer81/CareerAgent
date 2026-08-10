"""Interview preparation generation service (Sprint 3 remainder)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.career_documents_repository import InterviewPrepRepository
from app.repositories.job_analysis_repository import ScoringResultRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.career_documents import InterviewPrepPlan, InterviewQuestion
from app.schemas.scoring import FullAnalysisResult


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _build_pitch(profile: CandidateProfileData, title: str, company: str) -> str:
    return (
        f"I am excited about the {title} opportunity at {company}. "
        f"I bring {profile.current_title} leadership experience and a track record of "
        "building high-performing engineering teams, improving delivery outcomes, and "
        "driving cross-functional execution."
    )


def _build_likely_questions(result: FullAnalysisResult) -> list[InterviewQuestion]:
    scoring = result.scoring
    questions: list[InterviewQuestion] = []

    for skill in scoring.technical_match.matched[:3]:
        questions.append(
            InterviewQuestion(
                category="Technical Depth",
                question=f"Can you walk me through your hands-on experience with {skill}?",
                rationale=f"{skill} appears as a direct technical match in the role analysis.",
                talking_points=[
                    f"Share a concrete project where {skill} was critical.",
                    "Quantify delivery, quality, or business impact.",
                ],
            )
        )

    for signal in scoring.leadership_match.matched[:2]:
        questions.append(
            InterviewQuestion(
                category="Leadership",
                question=f"Tell me about a time you demonstrated {signal}.",
                rationale="Leadership alignment is a major factor in this role's recommendation.",
                talking_points=[
                    "Frame the situation and organizational context.",
                    "Describe decisions, trade-offs, and measurable outcomes.",
                ],
            )
        )

    for gap in scoring.technical_match.missing[:2]:
        questions.append(
            InterviewQuestion(
                category="Gap Mitigation",
                question=f"This role asks for {gap}. How would you close that gap quickly?",
                rationale="The scoring output flags this as a missing technical signal.",
                talking_points=[
                    "Connect adjacent experience you already have.",
                    "Offer a practical 30-60-90 day ramp plan.",
                ],
            )
        )

    if not questions:
        questions = [
            InterviewQuestion(
                category="Leadership",
                question="Tell me about a high-impact leadership decision you made under pressure.",
                rationale="Leadership scope is central to engineering management hiring decisions.",
                talking_points=[
                    "Describe the context, constraints, and trade-offs.",
                    "Quantify team or business outcomes from the decision.",
                ],
            ),
            InterviewQuestion(
                category="Execution",
                question="How do you align engineering execution with business priorities?",
                rationale="Role fit depends on translating strategy into delivery outcomes.",
                talking_points=[
                    "Explain planning cadence and prioritization framework.",
                    "Show an example of measurable impact.",
                ],
            ),
        ]

    return questions[:8]


def _build_questions_to_ask(result: FullAnalysisResult) -> list[str]:
    gaps = result.gap_analysis
    questions = [
        "What are the most critical outcomes expected in the first 90 days?",
        "How is success measured for this role across delivery, people, and business impact?",
    ]
    if gaps.missing_keywords:
        questions.append(
            "Which of the preferred technologies are truly day-one requirements versus learn-on-the-job?"
        )
    if gaps.missing_leadership_signals:
        questions.append(
            "How is leadership scope structured today, and where are the biggest organizational bottlenecks?"
        )
    return _dedupe_preserve_order(questions)


class InterviewPrepService:
    def __init__(self, session: AsyncSession) -> None:
        self.profile_repo = CandidateProfileRepository(session)
        self.job_repo = JobPostingRepository(session)
        self.scoring_repo = ScoringResultRepository(session)
        self.prep_repo = InterviewPrepRepository(session)

    async def build_prep(self, job_posting_id: int) -> InterviewPrepPlan:
        profile_record = await self.profile_repo.get_profile()
        if profile_record is None:
            raise NotFoundError("CandidateProfile", "singleton")

        job = await self.job_repo.get(job_posting_id)
        if job is None:
            raise NotFoundError("JobPosting", job_posting_id)

        scoring_record = await self.scoring_repo.get_by_job_id(job_posting_id)
        if scoring_record is None:
            raise AnalysisNotFoundError(job_posting_id)

        profile = CandidateProfileData.model_validate(profile_record.profile_data)
        result = FullAnalysisResult.model_validate(scoring_record.scoring_data)

        title = job.title or "Engineering Leadership Role"
        company = job.company or "the company"
        scoring = result.scoring
        gap = result.gap_analysis

        focus_areas = _dedupe_preserve_order(
            [
                *scoring.leadership_match.matched[:2],
                *scoring.technical_match.matched[:2],
                *gap.resume_focus_areas[:3],
            ]
        )[:6]

        risk_points = _dedupe_preserve_order(
            [
                *gap.risks[:3],
                *[f"Prepare concrete narrative for missing keyword: {k}" for k in gap.missing_keywords[:3]],
            ]
        )

        prep = InterviewPrepPlan(
            job_posting_id=job_posting_id,
            recommendation=scoring.recommendation,
            overall_score=scoring.overall_score,
            opening_pitch=_build_pitch(profile, title, company),
            priority_focus_areas=focus_areas,
            likely_questions=_build_likely_questions(result),
            risk_mitigation_points=risk_points,
            questions_to_ask_interviewer=_build_questions_to_ask(result),
        )

        await self.prep_repo.upsert(job_posting_id, prep.model_dump(mode="json"))
        return prep

    async def get_prep(self, job_posting_id: int) -> InterviewPrepPlan | None:
        record = await self.prep_repo.get_by_job_id(job_posting_id)
        if record is None:
            return None
        return InterviewPrepPlan.model_validate(record.prep_data)
