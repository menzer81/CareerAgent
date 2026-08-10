"""Unit tests for the cover letter service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.job_analysis_repository import JobAnalysisRepository, ScoringResultRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.analysis import JobRequirements
from app.schemas.career_documents import CoverLetterStyle, CoverLetterTone
from app.schemas.scoring import (
    DimensionScore,
    FullAnalysisResult,
    GapAnalysis,
    Recommendation,
    ScoringBreakdown,
)
from app.services.cover_letter_service import CoverLetterService
from tests.conftest import SAMPLE_PROFILE_DATA


def _make_scoring(job_posting_id: int) -> dict:
    return FullAnalysisResult(
        job_posting_id=job_posting_id,
        scoring=ScoringBreakdown(
            leadership_match=DimensionScore(score=90, explanation="Strong", matched=["MoM"], missing=[]),
            technical_match=DimensionScore(score=75, explanation="Solid", matched=["Python", "AWS"], missing=[]),
            cloud_match=DimensionScore(score=80, explanation="Good", matched=["AWS"], missing=[]),
            ai_match=DimensionScore(score=70, explanation="Good", matched=["LLM"], missing=[]),
            management_scope_match=DimensionScore(score=85, explanation="Good", matched=["Scale"], missing=[]),
            industry_match=DimensionScore(score=65, explanation="Some", matched=["SaaS"], missing=[]),
            overall_score=79.4,
            recommendation=Recommendation.APPLY,
            recommendation_reasoning="Strong enough to pursue.",
        ),
        gap_analysis=GapAnalysis(
            missing_experiences=[],
            missing_keywords=[],
            missing_certifications=[],
            missing_leadership_signals=[],
            strengths=["Led platform transformation", "Scaled teams"],
            risks=[],
            resume_focus_areas=["Highlight leadership impact"],
        ),
    ).model_dump(mode="json")


class TestCoverLetterService:
    @pytest.mark.asyncio
    async def test_builds_cover_letter_markdown(self, db_session: AsyncSession):
        profile_repo = CandidateProfileRepository(db_session)
        job_repo = JobPostingRepository(db_session)
        analysis_repo = JobAnalysisRepository(db_session)
        scoring_repo = ScoringResultRepository(db_session)

        await profile_repo.upsert_profile("Jane Smith", SAMPLE_PROFILE_DATA)
        job = await job_repo.create_posting(raw_text="job text", title="Engineering Director", company="Acme")
        await analysis_repo.upsert(job.id, JobRequirements(ai_requirements=["LLM"]).model_dump(mode="json"))
        await scoring_repo.upsert(job.id, _make_scoring(job.id))

        service = CoverLetterService(db_session)
        letter = await service.build_letter(job.id)

        assert letter.job_posting_id == job.id
        assert "Engineering Director" in letter.subject_line
        assert letter.markdown.startswith("# ")
        assert letter.signature == "Jane Smith"
        assert letter.tone == CoverLetterTone.PROFESSIONAL
        assert letter.style == CoverLetterStyle.CONCISE

    @pytest.mark.asyncio
    async def test_builds_cover_letter_with_custom_tone_and_style(self, db_session: AsyncSession):
        profile_repo = CandidateProfileRepository(db_session)
        job_repo = JobPostingRepository(db_session)
        analysis_repo = JobAnalysisRepository(db_session)
        scoring_repo = ScoringResultRepository(db_session)

        await profile_repo.upsert_profile("Jane Smith", SAMPLE_PROFILE_DATA)
        job = await job_repo.create_posting(raw_text="job text", title="Engineering Director", company="Acme")
        await analysis_repo.upsert(job.id, JobRequirements(ai_requirements=["LLM"]).model_dump(mode="json"))
        await scoring_repo.upsert(job.id, _make_scoring(job.id))

        service = CoverLetterService(db_session)
        letter = await service.build_letter(
            job.id,
            tone=CoverLetterTone.CONFIDENT,
            style=CoverLetterStyle.EXECUTIVE,
        )

        assert letter.tone == CoverLetterTone.CONFIDENT
        assert letter.style == CoverLetterStyle.EXECUTIVE
        assert "day one" in letter.closing_paragraph.lower()
        assert len(letter.body_paragraphs) >= 3

    @pytest.mark.asyncio
    async def test_build_raises_when_analysis_missing(self, db_session: AsyncSession):
        profile_repo = CandidateProfileRepository(db_session)
        job_repo = JobPostingRepository(db_session)

        await profile_repo.upsert_profile("Jane Smith", SAMPLE_PROFILE_DATA)
        job = await job_repo.create_posting(raw_text="job text", title="Engineering Director", company="Acme")

        service = CoverLetterService(db_session)
        with pytest.raises(AnalysisNotFoundError):
            await service.build_letter(job.id)
