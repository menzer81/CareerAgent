"""Unit tests for the Achievement Selection Engine."""

import pytest

from app.schemas.analysis import JobRequirements
from app.schemas.resume import AccomplishmentEntry
from app.services.achievement_selection_service import (
    AchievementSelectionService,
    rank_accomplishments,
)


@pytest.fixture
def accomplishments() -> list[AccomplishmentEntry]:
    return [
        AccomplishmentEntry(
            id="AI-001",
            title="Led AI Adoption",
            company="Acme",
            category="AI Transformation",
            tags=["copilot", "training", "ai-adoption"],
            impact="Drove Copilot adoption across engineering.",
        ),
        AccomplishmentEntry(
            id="CLOUD-001",
            title="AWS Enablement",
            company="Acme",
            category="Organizational Leadership",
            tags=["aws", "cloud", "training"],
            impact="Trained 500 engineers on AWS.",
        ),
        AccomplishmentEntry(
            id="LEGACY-001",
            title="Maintained a legacy mainframe system",
            company="Acme",
            category="Maintenance",
            tags=["cobol", "mainframe"],
            impact="Kept an old system running.",
        ),
    ]


class TestRankAccomplishments:
    def test_ai_requirements_favor_ai_accomplishment(self, accomplishments):
        reqs = JobRequirements(ai_requirements=["Copilot", "AI"])
        rankings = rank_accomplishments(accomplishments, reqs)
        assert rankings[0].id == "AI-001"

    def test_unrelated_accomplishment_scores_lowest(self, accomplishments):
        reqs = JobRequirements(ai_requirements=["Copilot", "AI"], cloud_requirements=["AWS"])
        rankings = rank_accomplishments(accomplishments, reqs)
        ranked_ids = [r.id for r in rankings]
        assert ranked_ids[-1] == "LEGACY-001"

    def test_ranking_includes_explainability_reasons(self, accomplishments):
        reqs = JobRequirements(cloud_requirements=["AWS"])
        rankings = rank_accomplishments(accomplishments, reqs)
        cloud_ranking = next(r for r in rankings if r.id == "CLOUD-001")
        assert cloud_ranking.ranking_reason
        assert any("AWS" in reason for reason in cloud_ranking.ranking_reason)

    def test_no_match_gives_generic_reason(self, accomplishments):
        reqs = JobRequirements(required_skills=["Quantum Computing"])
        rankings = rank_accomplishments(accomplishments, reqs)
        legacy_ranking = next(r for r in rankings if r.id == "LEGACY-001")
        assert legacy_ranking.ranking_reason == ["No direct requirement match"]

    def test_boosted_accomplishment_increases_score_and_is_flagged(self, accomplishments):
        reqs = JobRequirements(required_skills=["Quantum Computing"])
        unboosted = rank_accomplishments(accomplishments, reqs)
        boosted = rank_accomplishments(
            accomplishments, reqs, boosted_accomplishment_ids=["LEGACY-001"], boost_multiplier=2.0
        )

        legacy_unboosted = next(r for r in unboosted if r.id == "LEGACY-001")
        legacy_boosted = next(r for r in boosted if r.id == "LEGACY-001")

        assert legacy_boosted.boosted is True
        assert legacy_boosted.boost_multiplier == 2.0
        assert legacy_boosted.ranking_score > legacy_unboosted.ranking_score
        assert any("Boosted" in reason for reason in legacy_boosted.ranking_reason)

    def test_boosting_does_not_force_top_rank_when_irrelevant(self, accomplishments):
        """Recommendation 2: boosting should not force an irrelevant item to outrank
        a clearly relevant one — it only increases weighting, not forced inclusion."""
        reqs = JobRequirements(ai_requirements=["Copilot", "AI", "Training"])
        rankings = rank_accomplishments(
            accomplishments, reqs, boosted_accomplishment_ids=["LEGACY-001"], boost_multiplier=1.1
        )
        assert rankings[0].id == "AI-001"

    def test_scores_clamped_to_0_100(self, accomplishments):
        reqs = JobRequirements(
            required_skills=[f"skill_{i}" for i in range(20)],
            ai_requirements=["Copilot", "AI", "Training"],
        )
        rankings = rank_accomplishments(
            accomplishments, reqs, boosted_accomplishment_ids=["AI-001"], boost_multiplier=5.0
        )
        for ranking in rankings:
            assert 0 <= ranking.ranking_score <= 100


class TestAchievementSelectionService:
    def test_select_achievements_returns_top_n(self, accomplishments):
        service = AchievementSelectionService(accomplishments)
        reqs = JobRequirements(ai_requirements=["Copilot"])
        result = service.select_achievements(job_posting_id=1, requirements=reqs, top_n=2)
        assert len(result.selected_accomplishment_ids) == 2
        assert result.job_posting_id == 1

    def test_get_accomplishment_by_id(self, accomplishments):
        service = AchievementSelectionService(accomplishments)
        found = service.get_accomplishment("AI-001")
        assert found is not None
        assert found.title == "Led AI Adoption"

    def test_get_accomplishment_missing_returns_none(self, accomplishments):
        service = AchievementSelectionService(accomplishments)
        assert service.get_accomplishment("DOES-NOT-EXIST") is None
