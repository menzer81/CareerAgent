"""Unit tests for the interview prep service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.job_analysis_repository import ScoringResultRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.scoring import (
    DimensionScore,
    FullAnalysisResult,
    GapAnalysis,
    Recommendation,
    ScoringBreakdown,
)
from app.services.interview_prep_service import InterviewPrepService
from tests.conftest import SAMPLE_PROFILE_DATA


def _make_scoring(job_posting_id: int) -> dict:
    return FullAnalysisResult(
        job_posting_id=job_posting_id,
        scoring=ScoringBreakdown(
            leadership_match=DimensionScore(
                score=85, explanation="Strong leadership", matched=["Manager of managers"], missing=[]
            ),
            technical_match=DimensionScore(
                score=72, explanation="Good technical overlap", matched=["Python", "AWS"], missing=["Kotlin"]
            ),
            cloud_match=DimensionScore(score=80, explanation="Cloud fit", matched=["AWS"], missing=["Azure"]),
            ai_match=DimensionScore(score=65, explanation="AI fit", matched=["LLM"], missing=[]),
            management_scope_match=DimensionScore(
                score=88, explanation="Scope fit", matched=["large org"], missing=[]
            ),
            industry_match=DimensionScore(score=60, explanation="Some domain fit", matched=["SaaS"], missing=[]),
            overall_score=76.3,
            recommendation=Recommendation.APPLY,
            recommendation_reasoning="Good alignment with manageable gaps.",
        ),
        gap_analysis=GapAnalysis(
            missing_experiences=[],
            missing_keywords=["Kotlin"],
            missing_certifications=[],
            missing_leadership_signals=[],
            strengths=["Manager of managers experience", "AWS leadership"],
            risks=["One required language gap"],
            resume_focus_areas=["Highlight platform modernization wins"],
        ),
    ).model_dump(mode="json")


class TestInterviewPrepService:
    @pytest.mark.asyncio
    async def test_builds_interview_prep_plan(self, db_session: AsyncSession):
        profile_repo = CandidateProfileRepository(db_session)
        job_repo = JobPostingRepository(db_session)
        scoring_repo = ScoringResultRepository(db_session)

        await profile_repo.upsert_profile("Jane Smith", SAMPLE_PROFILE_DATA)
        job = await job_repo.create_posting(raw_text="job text", title="Director of Engineering", company="Acme")
        await scoring_repo.upsert(job.id, _make_scoring(job.id))

        service = InterviewPrepService(db_session)
        prep = await service.build_prep(job.id)

        assert prep.job_posting_id == job.id
        assert prep.opening_pitch
        assert prep.priority_focus_areas
        assert prep.likely_questions
        assert prep.questions_to_ask_interviewer

    @pytest.mark.asyncio
    async def test_build_raises_when_scoring_missing(self, db_session: AsyncSession):
        profile_repo = CandidateProfileRepository(db_session)
        job_repo = JobPostingRepository(db_session)

        await profile_repo.upsert_profile("Jane Smith", SAMPLE_PROFILE_DATA)
        job = await job_repo.create_posting(raw_text="job text", title="Director of Engineering", company="Acme")

        service = InterviewPrepService(db_session)
        with pytest.raises(AnalysisNotFoundError):
            await service.build_prep(job.id)
