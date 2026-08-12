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
                    executive_summary=(
                        "Engineering delivery leader with 15 years of software delivery experience. "
                        "Leads distributed teams and drives measurable execution outcomes. "
                        "Builds AI-assisted engineering workflows to improve developer productivity. "
                        "Aligns platform, compliance, and cloud initiatives with business goals."
                    ),
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
        assert "Engineering delivery leader" in result.executive_summary
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
                    executive_summary=(
                        "Engineering leader focused on delivery outcomes and operational reliability. "
                        "Partners across teams to improve execution quality and cycle time. "
                        "Applies automation and AI-assisted workflows where appropriate. "
                        "Builds accountable teams with measurable impact."
                    ),
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

        assert result.generated_by == "llm"
        assert result.accomplishment_bullets[0].id == "acc-1"
        assert (
            result.accomplishment_bullets[0].generated_text
            == "AWS Enablement: Trained 500 engineers with 98% completion."
        )

    @pytest.mark.asyncio
    async def test_fuzzy_company_match_allows_cross_source_numbers(self, profile, strategy):
        """Numbers present in work history are NOT flagged even when accomplishment company
        name differs by suffix (e.g. 'J.J. Keller' vs 'J.J. Keller & Associates')."""
        # This accomplishment's company name is shorter than the work history entry's name.
        acc = AccomplishmentEntry(
            id="JJK-004",
            title="SOC 2 Compliance Automation",
            company="J.J. Keller",
            category="Compliance",
            impact="Automated SOC 2 and ISO 27001 evidence collection.",
            metrics={},
        )
        # Profile work history has "J.J. Keller & Associates" with these numbers in key_accomplishments.
        import copy, json
        raw = copy.deepcopy(SAMPLE_PROFILE_DATA)
        raw["work_history"] = [
            {
                "company": "J.J. Keller & Associates",
                "title": "Software Development Manager",
                "start_date": "2024-01",
                "key_accomplishments": [
                    "Automated approximately 80 percent of SOC 2 evidence collection.",
                    "Automated approximately 50 percent of ISO 27001 evidence collection.",
                ],
            }
        ]
        from app.schemas.candidate_profile import CandidateProfileData as CPD
        profile_patched = CPD.model_validate(raw)

        class LLMReturnsCrossSourceNumbers:
            async def generate_resume_content(self, job_posting_id, prof, requirements, strategy, selected):
                return GeneratedResumeContent(
                    job_posting_id=job_posting_id,
                    executive_summary=(
                        "Technical delivery leader with deep experience in engineering execution. "
                        "Leads distributed teams and drives quality and throughput improvements. "
                        "Uses automation and AI-assisted practices to strengthen delivery outcomes. "
                        "Brings compliance and operational rigor to complex delivery environments."
                    ),
                    accomplishment_bullets=[
                        GeneratedAccomplishmentBullet(
                            id="JJK-004",
                            generated_text=(
                                "Led development of AI-driven automation, automating approximately "
                                "80 percent of SOC 2 evidence and approximately 50 percent of "
                                "ISO 27001 evidence collection."
                            ),
                        )
                    ],
                    generated_by="llm",
                )

        service = ResumeContentGenerationService(llm=LLMReturnsCrossSourceNumbers())
        result = await service.generate(1, profile_patched, JobRequirements(), strategy, [acc])

        bullet = result.accomplishment_bullets[0]
        # Should NOT have been scrubbed — 80, 50, 2, 27001 all come from work history
        assert "80" in bullet.generated_text, "80 should survive fuzzy company match"
        assert "27001" in bullet.generated_text, "27001 should survive fuzzy company match"

    @pytest.mark.asyncio
    async def test_ai_heavy_summary_retries_with_guidance(self, profile, strategy, accomplishments):
        class RetryLLM:
            def __init__(self) -> None:
                self.guided_calls = 0

            async def generate_resume_content(self, job_posting_id, profile, requirements, strategy, selected):
                return GeneratedResumeContent(
                    job_posting_id=job_posting_id,
                    executive_summary=(
                        "Engineering delivery leader with strong leadership outcomes. "
                        "Drives cross-functional execution and operational excellence. "
                        "Builds reliable delivery systems across distributed teams. "
                        "Partners with stakeholders to deliver measurable business results."
                    ),
                    generated_by="llm",
                )

            async def generate_resume_content_with_guidance(
                self,
                job_posting_id,
                profile,
                requirements,
                strategy,
                selected,
                summary_guidance,
            ):
                self.guided_calls += 1
                return GeneratedResumeContent(
                    job_posting_id=job_posting_id,
                    executive_summary=(
                        "Engineering delivery leader with deep experience building AI-enabled execution systems. "
                        "Leads distributed teams and scales AI and Copilot adoption to improve developer productivity. "
                        "Drives AI automation, agent-based workflows, and governance-aligned delivery outcomes. "
                        "Partners with stakeholders to deliver measurable, AI-informed business impact."
                    ),
                    generated_by="llm",
                )

        requirements = JobRequirements(
            ai_requirements=["LLM integration", "AI agents"],
            important_keywords=["AI transformation", "copilot", "leadership"],
            role_summary="Lead AI platform initiatives while managing distributed teams.",
            leadership_requirements=["team leadership"],
        )
        llm = RetryLLM()
        service = ResumeContentGenerationService(llm=llm)

        result = await service.generate(1, profile, requirements, strategy, accomplishments)

        assert llm.guided_calls == 1
        assert result.generated_by == "llm"
        lowered = result.executive_summary.lower()
        assert lowered.count("ai") >= 2

    @pytest.mark.asyncio
    async def test_ai_heavy_summary_retry_failure_falls_back_to_static(self, profile, strategy, accomplishments):
        class AlwaysBadSummaryLLM:
            async def generate_resume_content(self, job_posting_id, profile, requirements, strategy, selected):
                return GeneratedResumeContent(
                    job_posting_id=job_posting_id,
                    executive_summary="Short summary.",
                    generated_by="llm",
                )

            async def generate_resume_content_with_guidance(
                self,
                job_posting_id,
                profile,
                requirements,
                strategy,
                selected,
                summary_guidance,
            ):
                return GeneratedResumeContent(
                    job_posting_id=job_posting_id,
                    executive_summary="Still short.",
                    generated_by="llm",
                )

        requirements = JobRequirements(
            ai_requirements=["AI agents"],
            important_keywords=["ai", "copilot", "leadership"],
            role_summary="Need an AI-heavy engineering leader.",
            leadership_requirements=["leadership"],
        )
        service = ResumeContentGenerationService(llm=AlwaysBadSummaryLLM())

        result = await service.generate(1, profile, requirements, strategy, accomplishments)

        assert result.generated_by == "static"
        assert result.executive_summary == profile.summary

