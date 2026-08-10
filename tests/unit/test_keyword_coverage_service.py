"""Unit tests for the Keyword Coverage Service (Recommendation 4)."""

import pytest

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.services.keyword_coverage_service import KeywordCoverageService
from tests.conftest import SAMPLE_PROFILE_DATA


@pytest.fixture
def profile() -> CandidateProfileData:
    return CandidateProfileData.model_validate(SAMPLE_PROFILE_DATA)


@pytest.fixture
def service() -> KeywordCoverageService:
    return KeywordCoverageService()


class TestKeywordCoverageService:
    def test_no_keywords_returns_full_coverage(self, service, profile):
        report = service.compute_coverage(JobRequirements(), profile)
        assert report.coverage_percent == 100.0
        assert report.required_keywords == 0

    def test_falls_back_to_required_and_preferred_skills(self, service, profile):
        tech = profile.technologies[0]
        requirements = JobRequirements(required_skills=[tech])
        report = service.compute_coverage(requirements, profile)
        assert report.required_keywords == 1
        assert tech in report.matched_keywords

    def test_matched_and_missing_keywords_partition_correctly(self, service, profile):
        tech = profile.technologies[0]
        requirements = JobRequirements(
            important_keywords=[tech, "TotallyUnrelatedNonsenseKeywordXYZ"]
        )
        report = service.compute_coverage(requirements, profile)
        assert tech in report.matched_keywords
        assert "TotallyUnrelatedNonsenseKeywordXYZ" in report.missing_keywords
        assert report.covered_keywords == 1
        assert report.required_keywords == 2
        assert report.coverage_percent == 50.0

    def test_duplicate_keywords_are_deduplicated(self, service, profile):
        tech = profile.technologies[0]
        requirements = JobRequirements(important_keywords=[tech, tech.upper(), tech])
        report = service.compute_coverage(requirements, profile)
        assert report.required_keywords == 1

    def test_full_mismatch_gives_zero_coverage(self, service, profile):
        requirements = JobRequirements(
            important_keywords=["CompletelyMadeUpTechABC", "AnotherFakeSkillDEF"]
        )
        report = service.compute_coverage(requirements, profile)
        assert report.coverage_percent == 0.0
        assert report.matched_keywords == []
