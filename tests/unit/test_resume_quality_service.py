"""Unit tests for the Resume Quality Scoring Service (Recommendation 8)."""

import pytest

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import KeywordCoverageReport
from app.services.resume_quality_service import ResumeQualityScoringService
from tests.conftest import SAMPLE_PROFILE_DATA


@pytest.fixture
def profile() -> CandidateProfileData:
    return CandidateProfileData.model_validate(SAMPLE_PROFILE_DATA)


@pytest.fixture
def service() -> ResumeQualityScoringService:
    return ResumeQualityScoringService()


def _coverage(percent: float) -> KeywordCoverageReport:
    return KeywordCoverageReport(
        required_keywords=10,
        covered_keywords=int(percent / 10),
        coverage_percent=percent,
        matched_keywords=[],
        missing_keywords=[],
    )


class TestResumeQualityScoringService:
    def test_scores_are_bounded_0_100(self, service, profile):
        requirements = JobRequirements(
            manager_of_managers_required=True, ai_requirements=["LLM"]
        )
        result = service.score(profile, requirements, _coverage(80.0))
        for value in (
            result.keyword_coverage,
            result.leadership_signal_strength,
            result.ai_relevance,
            result.manager_of_managers_alignment,
            result.overall_resume_quality,
        ):
            assert 0.0 <= value <= 100.0

    def test_higher_keyword_coverage_increases_overall_quality(self, service, profile):
        requirements = JobRequirements()
        low = service.score(profile, requirements, _coverage(20.0))
        high = service.score(profile, requirements, _coverage(90.0))
        assert high.overall_resume_quality > low.overall_resume_quality

    def test_manager_of_managers_requirement_matched_scores_full_alignment(
        self, service, profile
    ):
        profile.leadership_experience.manager_of_managers = True
        requirements = JobRequirements(manager_of_managers_required=True)
        result = service.score(profile, requirements, _coverage(50.0))
        assert result.manager_of_managers_alignment == 100.0

    def test_manager_of_managers_requirement_unmatched_scores_low_alignment(
        self, service, profile
    ):
        profile.leadership_experience.manager_of_managers = False
        requirements = JobRequirements(manager_of_managers_required=True)
        result = service.score(profile, requirements, _coverage(50.0))
        assert result.manager_of_managers_alignment == 30.0

    def test_no_manager_of_managers_requirement_scores_full_alignment_by_default(
        self, service, profile
    ):
        requirements = JobRequirements(manager_of_managers_required=False)
        result = service.score(profile, requirements, _coverage(50.0))
        assert result.manager_of_managers_alignment == 100.0

    def test_no_ai_requirements_gives_neutral_ai_relevance(self, service, profile):
        requirements = JobRequirements()
        result = service.score(profile, requirements, _coverage(50.0))
        assert result.ai_relevance == 70.0
