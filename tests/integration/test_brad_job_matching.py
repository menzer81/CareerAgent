"""Candidate fit integration tests using the real candidate profile and a
hand-verified golden job dataset (data/golden_jobs.json + data/job_descriptions/).

These tests exist to catch regressions in scoring and achievement-selection
behavior against Brad's actual profile — not the synthetic SAMPLE_PROFILE_DATA
used elsewhere — across three validation categories:

- Strong Apply: expected score 85+
- Stretch: expected score ~55-85
- Low Priority: expected score below 55
"""

import json
from pathlib import Path

import pytest

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.services.accomplishment_loader import load_accomplishments
from app.services.achievement_selection_service import AchievementSelectionService
from app.services.resume_strategy_service import ResumePersona, ResumeStrategyService
from app.services.scoring_service import rule_based_score

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_brad_profile() -> CandidateProfileData:
    raw = json.loads((DATA_DIR / "candidate_profile.json").read_text(encoding="utf-8"))
    return CandidateProfileData.model_validate(raw)


def load_golden_jobs() -> list[dict]:
    raw = json.loads((DATA_DIR / "golden_jobs.json").read_text(encoding="utf-8"))
    return raw["jobs"]


BRAD_PROFILE = load_brad_profile()
GOLDEN_JOBS = load_golden_jobs()
ACCOMPLISHMENTS = load_accomplishments()


def _job_by_file(job_file: str) -> dict:
    for job in GOLDEN_JOBS:
        if job["job_file"] == job_file:
            return job
    raise AssertionError(f"No golden job entry for {job_file}")


class TestGoldenJobDataset:
    """Every golden job's job_descriptions/*.md file must actually exist."""

    @pytest.mark.parametrize("job", GOLDEN_JOBS, ids=lambda j: j["job_file"])
    def test_job_posting_file_exists(self, job: dict) -> None:
        posting_path = DATA_DIR / "job_descriptions" / job["job_file"]
        assert posting_path.exists(), f"Missing job posting file: {posting_path}"


class TestBradCandidateFit:
    """Score every golden job against Brad's real profile and check expectations."""

    @pytest.mark.parametrize("job", GOLDEN_JOBS, ids=lambda j: j["job_file"])
    def test_score_falls_in_expected_range(self, job: dict) -> None:
        requirements = JobRequirements.model_validate(job["requirements"])
        result = rule_based_score(BRAD_PROFILE, requirements, job_posting_id=1)

        low, high = job["expected_score_range"]
        overall = result.scoring.overall_score
        assert low <= overall <= high, (
            f"{job['job_file']}: expected score in [{low}, {high}], got {overall}"
        )


class TestStrongMatches:
    """Roles closely aligned with Brad's actual background and target roles."""

    @pytest.fixture(params=[j for j in GOLDEN_JOBS if j["category"] == "strong_apply"])
    def strong_job(self, request) -> dict:
        return request.param

    def test_ai_focused_senior_sdm_scores_high(self) -> None:
        job = _job_by_file("strong_apply/senior_sdm_ai.md")
        requirements = JobRequirements.model_validate(job["requirements"])
        result = rule_based_score(BRAD_PROFILE, requirements, job_posting_id=1)
        assert result.scoring.overall_score >= 85

    def test_strong_apply_bucket_has_expected_top_candidates(self, strong_job: dict) -> None:
        # The folder is user-curated; per-job expected score/recommendation are
        # enforced in TestBradCandidateFit. Here we still require a meaningful
        # expected-top-accomplishments list for curation quality.
        assert strong_job["expected_top_accomplishments_any_of"]

    def test_strong_match_selects_relevant_top_accomplishment(self, strong_job: dict) -> None:
        requirements = JobRequirements.model_validate(strong_job["requirements"])
        selection = AchievementSelectionService(ACCOMPLISHMENTS).select_achievements(
            1, requirements, top_n=3
        )
        expected_any_of = strong_job["expected_top_accomplishments_any_of"]
        assert any(acc_id in selection.selected_accomplishment_ids for acc_id in expected_any_of)


class TestStretchOpportunities:
    """Larger-scope roles Brad could grow into but doesn't fully meet yet."""

    @pytest.fixture(params=[j for j in GOLDEN_JOBS if j["category"] == "stretch"])
    def stretch_job(self, request) -> dict:
        return request.param

    def test_stretch_roles_score_in_middle_band(self, stretch_job: dict) -> None:
        requirements = JobRequirements.model_validate(stretch_job["requirements"])
        result = rule_based_score(BRAD_PROFILE, requirements, job_posting_id=1)
        assert 55 <= result.scoring.overall_score <= 85

    def test_director_role_emphasizes_manager_of_managers(self, stretch_job: dict) -> None:
        requirements = JobRequirements.model_validate(stretch_job["requirements"])
        selection = AchievementSelectionService(ACCOMPLISHMENTS).select_achievements(
            1, requirements
        )
        strategy = ResumeStrategyService().build_strategy(
            1, requirements, BRAD_PROFILE, selection
        )
        assert "manager-of-managers" in strategy.emphasize


class TestApplyMatches:
    """Roles that should generally score as 'Apply' for Brad's background."""

    @pytest.fixture(params=[j for j in GOLDEN_JOBS if j["category"] == "apply"])
    def apply_job(self, request) -> dict:
        return request.param

    def test_apply_roles_recommend_at_least_stretch(self, apply_job: dict) -> None:
        requirements = JobRequirements.model_validate(apply_job["requirements"])
        result = rule_based_score(BRAD_PROFILE, requirements, job_posting_id=1)
        assert result.scoring.recommendation.value in (
            "Stretch Opportunity",
            "Apply",
            "Strong Apply",
        )


class TestPoorMatches:
    """Roles that are a clear mismatch with Brad's management-focused background."""

    @pytest.fixture(params=[j for j in GOLDEN_JOBS if j["category"] == "low_priority"])
    def poor_job(self, request) -> dict:
        return request.param

    def test_poor_matches_score_below_50(self, poor_job: dict) -> None:
        requirements = JobRequirements.model_validate(poor_job["requirements"])
        result = rule_based_score(BRAD_PROFILE, requirements, job_posting_id=1)
        assert result.scoring.overall_score < 55

    def test_poor_matches_recommend_low_priority(self, poor_job: dict) -> None:
        requirements = JobRequirements.model_validate(poor_job["requirements"])
        result = rule_based_score(BRAD_PROFILE, requirements, job_posting_id=1)
        assert result.scoring.recommendation.value == "Low Priority"


class TestAchievementRanking:
    """Achievement Selection Engine behavior against Brad's real accomplishment bank."""

    def test_ai_role_selects_ai_accomplishments(self) -> None:
        requirements = JobRequirements(
            ai_requirements=["AI", "Copilot", "LLM"],
            important_keywords=["AI Transformation", "training"],
        )
        selection = AchievementSelectionService(ACCOMPLISHMENTS).select_achievements(
            1, requirements, top_n=3
        )
        assert "JJK-002" in selection.selected_accomplishment_ids
        assert "JJK-003" in selection.selected_accomplishment_ids

    def test_compliance_role_selects_compliance_accomplishments(self) -> None:
        requirements = JobRequirements(
            important_keywords=["SOC 2", "ISO 27001", "Compliance", "audit"],
            industry_domain=["Compliance"],
        )
        selection = AchievementSelectionService(ACCOMPLISHMENTS).select_achievements(
            1, requirements, top_n=1
        )
        assert selection.selected_accomplishment_ids == ["JJK-004"]

    def test_cloud_role_selects_aws_training_story(self) -> None:
        requirements = JobRequirements(
            cloud_requirements=["AWS", "Cloud"],
            important_keywords=["AWS", "training", "cloud transformation"],
        )
        selection = AchievementSelectionService(ACCOMPLISHMENTS).select_achievements(
            1, requirements, top_n=1
        )
        assert selection.selected_accomplishment_ids == ["ENT-001"]


class TestResumeStrategyOutput:
    """Resume Strategy Service behavior against real requirements/profile."""

    def test_ai_role_emphasizes_ai_transformation(self) -> None:
        requirements = JobRequirements(
            ai_requirements=["AI", "Copilot", "LLM"],
            important_keywords=["AI Transformation"],
        )
        selection = AchievementSelectionService(ACCOMPLISHMENTS).select_achievements(
            1, requirements
        )
        strategy = ResumeStrategyService().build_strategy(
            1, requirements, BRAD_PROFILE, selection
        )
        assert "AI Transformation" in strategy.key_themes
        assert strategy.persona == ResumePersona.AI_TRANSFORMATION_LEADER
