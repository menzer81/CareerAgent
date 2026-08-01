"""Unit tests for the scoring service (rule-based path)."""

import pytest

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.scoring import Recommendation
from app.services.scoring_service import rule_based_score
from tests.conftest import SAMPLE_PROFILE_DATA


@pytest.fixture
def profile() -> CandidateProfileData:
    return CandidateProfileData.model_validate(SAMPLE_PROFILE_DATA)


@pytest.fixture
def strong_requirements() -> JobRequirements:
    return JobRequirements(
        required_skills=["Python", "AWS", "Kubernetes"],
        preferred_skills=["Go", "Terraform"],
        manager_of_managers_required=True,
        director_level_or_above=True,
        cloud_requirements=["AWS", "GCP"],
        ai_requirements=["OpenAI API"],
        industry_domain=["SaaS"],
        years_of_experience_min=8,
    )


@pytest.fixture
def weak_requirements() -> JobRequirements:
    return JobRequirements(
        required_skills=["Java", "Oracle", "COBOL"],
        preferred_skills=["SAP", "Mainframe"],
        manager_of_managers_required=False,
        director_level_or_above=False,
        cloud_requirements=["Azure"],
        ai_requirements=["TensorFlow", "PyTorch", "MLflow"],
        industry_domain=["Healthcare", "Pharma"],
        years_of_experience_min=3,
    )


class TestRuleBasedScoring:
    def test_strong_match_produces_high_score(self, profile, strong_requirements):
        result = rule_based_score(profile, strong_requirements, job_posting_id=1)
        assert result.scoring.overall_score >= 70

    def test_weak_match_produces_low_score(self, profile, weak_requirements):
        result = rule_based_score(profile, weak_requirements, job_posting_id=2)
        assert result.scoring.overall_score < 70

    def test_recommendation_tiers(self, profile, strong_requirements, weak_requirements):
        strong = rule_based_score(profile, strong_requirements, job_posting_id=1)
        weak = rule_based_score(profile, weak_requirements, job_posting_id=2)
        # Strong match should be Apply or Strong Apply
        assert strong.scoring.recommendation in (Recommendation.STRONG_APPLY, Recommendation.APPLY)
        # Weak match should be below Apply
        assert weak.scoring.recommendation in (
            Recommendation.STRETCH_OPPORTUNITY, Recommendation.LOW_PRIORITY
        )

    def test_overall_score_is_weighted(self, profile, strong_requirements):
        result = rule_based_score(profile, strong_requirements, job_posting_id=1)
        s = result.scoring
        expected = (
            s.leadership_match.score * 0.20
            + s.technical_match.score * 0.25
            + s.cloud_match.score * 0.15
            + s.ai_match.score * 0.10
            + s.management_scope_match.score * 0.15
            + s.industry_match.score * 0.15
        )
        assert abs(result.scoring.overall_score - round(expected, 1)) < 0.01

    def test_missing_skills_appear_in_gap(self, profile, weak_requirements):
        result = rule_based_score(profile, weak_requirements, job_posting_id=3)
        # COBOL, Java, Oracle should appear in missing keywords
        missing = [k.lower() for k in result.gap_analysis.missing_keywords]
        assert any("java" in m or "cobol" in m or "oracle" in m for m in missing)

    def test_no_cloud_requirements_gives_neutral_score(self, profile):
        reqs = JobRequirements(required_skills=["Python"])
        result = rule_based_score(profile, reqs, job_posting_id=4)
        assert result.scoring.cloud_match.score == 75.0

    def test_no_ai_requirements_gives_neutral_score(self, profile):
        reqs = JobRequirements(required_skills=["Python"])
        result = rule_based_score(profile, reqs, job_posting_id=5)
        assert result.scoring.ai_match.score == 70.0

    def test_mom_required_but_candidate_has_it(self, profile, strong_requirements):
        result = rule_based_score(profile, strong_requirements, job_posting_id=1)
        matched = result.scoring.leadership_match.matched
        assert any("manager of managers" in m.lower() for m in matched)

    def test_result_job_posting_id_matches(self, profile, strong_requirements):
        result = rule_based_score(profile, strong_requirements, job_posting_id=42)
        assert result.job_posting_id == 42

    def test_scores_clamped_to_0_100(self, profile):
        # Even extreme mismatches shouldn't go out of range
        reqs = JobRequirements(
            required_skills=[f"skill_{i}" for i in range(50)],
            manager_of_managers_required=True,
            director_level_or_above=True,
            cloud_requirements=[f"cloud_{i}" for i in range(20)],
        )
        result = rule_based_score(profile, reqs, job_posting_id=99)
        s = result.scoring
        for dim in [s.leadership_match, s.technical_match, s.cloud_match, s.ai_match,
                    s.management_scope_match, s.industry_match]:
            assert 0 <= dim.score <= 100
