"""Unit tests for the gap analysis service."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.job_analysis_repository import ScoringResultRepository
from app.schemas.scoring import (
    DimensionScore,
    FullAnalysisResult,
    GapAnalysis,
    Recommendation,
    ScoringBreakdown,
)
from app.services.gap_analysis_service import GapAnalysisService


def _make_scoring_data(job_posting_id: int = 1) -> dict:
    result = FullAnalysisResult(
        job_posting_id=job_posting_id,
        scoring=ScoringBreakdown(
            leadership_match=DimensionScore(score=80, explanation="ok", matched=["MoM"], missing=[]),
            technical_match=DimensionScore(
                score=60, explanation="ok", matched=["Python"], missing=["Go", "Rust"]
            ),
            cloud_match=DimensionScore(score=70, explanation="ok", matched=["AWS"], missing=["Azure"]),
            ai_match=DimensionScore(score=50, explanation="ok", matched=[], missing=["PyTorch"]),
            management_scope_match=DimensionScore(score=85, explanation="ok", matched=[], missing=[]),
            industry_match=DimensionScore(score=40, explanation="ok", matched=[], missing=["fintech"]),
            overall_score=67.5,
            recommendation=Recommendation.STRETCH_OPPORTUNITY,
            recommendation_reasoning="Moderate match.",
        ),
        gap_analysis=GapAnalysis(
            missing_experiences=["Fintech domain experience"],
            missing_keywords=["Go", "Rust", "PyTorch"],
            missing_certifications=["CFA"],
            missing_leadership_signals=[],
            strengths=["Manager of managers", "Strong AWS background"],
            risks=["Industry mismatch"],
            resume_focus_areas=["Emphasize Python expertise"],
        ),
    )
    return result.model_dump()


class TestGapAnalysisService:
    @pytest.mark.asyncio
    async def test_returns_gap_analysis(self, db_session: AsyncSession):
        repo = ScoringResultRepository(db_session)
        await repo.create(job_posting_id=1, scoring_data=_make_scoring_data(1))
        await db_session.flush()

        service = GapAnalysisService(db_session)
        gap = await service.get_gap_analysis(1)

        assert "Fintech domain experience" in gap.missing_experiences
        assert "Go" in gap.missing_keywords
        assert "CFA" in gap.missing_certifications
        assert "Manager of managers" in gap.strengths

    @pytest.mark.asyncio
    async def test_raises_when_no_analysis(self, db_session: AsyncSession):
        from app.core.exceptions import AnalysisNotFoundError
        service = GapAnalysisService(db_session)
        with pytest.raises(AnalysisNotFoundError):
            await service.get_gap_analysis(999)
