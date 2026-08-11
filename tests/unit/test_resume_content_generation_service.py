"""Unit tests for the Resume Content Generation Service."""

import pytest

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import (
    AccomplishmentEntry,
    GeneratedAccomplishmentBullet,
    GeneratedResumeContent,
    GeneratedWorkHistoryBullets,
    ResumePersona,
    ResumeStrategy,
)
from app.services.resume_content_generation_service import ResumeContentGenerationService
from tests.conftest import SAMPLE_PROFILE_DATA


@pytest.fixture
def profile() -> CandidateProfileData:
    return CandidateProfileData.model_validate(SAMPLE_PROFILE_DATA)


@pytest.fixture
def strategy() -> ResumeStrategy:
    return ResumeStrategy(job_posting_id=1, persona=ResumePersona.TECHNICAL_DELIVERY_LEADER)


@pytest.fixture
def accomplishments() -> list[AccomplishmentEntry]:
    return [
        AccomplishmentEntry(
            id="acc-1",
            title="Led platform migration",
            company="TechCorp",
            category="Leadership",
            impact="Saved $2M/year",
            metrics={"savings_usd": 2_000_000},
        )
    ]


class TestResumeContentGenerationService:
    @pytest.mark.asyncio
    async def test_no_llm_falls_back_to_static_profile_content(self, profile, strategy, accomplishments):
        service = ResumeContentGenerationService(llm=None)
        result = await service.generate(1, profile, JobRequirements(), strategy, accomplishments)

        assert result.generated_by == "static"
        assert result.executive_summary == profile.summary
        assert result.accomplishment_bullets[0].id == "acc-1"
        assert "Saved $2M/year" in result.accomplishment_bullets[0].generated_text

    @pytest.mark.asyncio
    async def test_uses_llm_output_when_configured(self, profile, strategy, accomplishments):
        class FakeLLM:
            async def generate_resume_content(self, job_posting_id, profile, requirements, strategy, selected):
                return GeneratedResumeContent(
                    job_posting_id=job_posting_id,
                    executive_summary="Tailored summary.",
                    experience_bullets=[
                        GeneratedWorkHistoryBullets(company="TechCorp", bullets=["Rewrote bullet."])
                    ],
                    accomplishment_bullets=[
                        GeneratedAccomplishmentBullet(id="acc-1", generated_text="Rewrote accomplishment.")
                    ],
                    generated_by="llm",
                )

        service = ResumeContentGenerationService(llm=FakeLLM())
        result = await service.generate(1, profile, JobRequirements(), strategy, accomplishments)

        assert result.generated_by == "llm"
        assert result.executive_summary == "Tailored summary."
        assert result.experience_bullets[0].bullets == ["Rewrote bullet."]

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_static_content(self, profile, strategy, accomplishments):
        class FailingLLM:
            async def generate_resume_content(self, *args, **kwargs):
                raise RuntimeError("boom")

        service = ResumeContentGenerationService(llm=FailingLLM())
        result = await service.generate(1, profile, JobRequirements(), strategy, accomplishments)

        assert result.generated_by == "static"
        assert result.executive_summary == profile.summary

    @pytest.mark.asyncio
    async def test_fabricated_metrics_scrubbed_to_static(self, profile, strategy):
        """Bullets with hallucinated numbers are replaced by safe static text."""
        acc = AccomplishmentEntry(
            id="acc-1",
            title="AWS Enablement",
            company="Entrata",
            category="Leadership",
            impact="Trained 500 engineers with 98% completion.",
            metrics={"engineers_trained": 500, "completion_rate_percent": 98},
        )

        class HallucinatingLLM:
            async def generate_resume_content(self, job_posting_id, profile, requirements, strategy, selected):
                return GeneratedResumeContent(
                    job_posting_id=job_posting_id,
                    executive_summary="Tailored summary.",
                    accomplishment_bullets=[
                        # 150000 is fabricated
                        GeneratedAccomplishmentBullet(
                            id="acc-1",
                            generated_text="Scaled platform to 150000 units and trained 500 engineers.",
                        )
                    ],
                    generated_by="llm",
                )

        service = ResumeContentGenerationService(llm=HallucinatingLLM())
        result = await service.generate(1, profile, JobRequirements(), strategy, [acc])

        bullet = result.accomplishment_bullets[0]
        assert "150000" not in bullet.generated_text
        assert "AWS Enablement" in bullet.generated_text or "500" in bullet.generated_text
