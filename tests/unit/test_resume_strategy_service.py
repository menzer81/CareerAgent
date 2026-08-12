"""Unit tests for the Resume Strategy Service."""

import pytest

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import ResumePersona
from app.services.achievement_selection_service import AchievementSelectionService
from app.services.resume_strategy_service import ResumeStrategyService, select_persona
from tests.conftest import SAMPLE_PROFILE_DATA


@pytest.fixture
def profile() -> CandidateProfileData:
    return CandidateProfileData.model_validate(SAMPLE_PROFILE_DATA)


@pytest.fixture
def selection_service() -> AchievementSelectionService:
    return AchievementSelectionService(accomplishments=[])


class TestPersonaSelection:
    def test_compliance_keywords_select_compliance_persona(self):
        reqs = JobRequirements(important_keywords=["SOC 2", "Compliance"])
        assert select_persona(reqs) == ResumePersona.COMPLIANCE_GOVERNANCE_LEADER

    def test_ai_requirements_select_ai_persona(self):
        reqs = JobRequirements(ai_requirements=["LLM", "Copilot"])
        assert select_persona(reqs) == ResumePersona.AI_TRANSFORMATION_LEADER

    def test_turnaround_language_selects_turnaround_persona(self):
        reqs = JobRequirements(role_summary="We need a leader to turnaround this underperforming team.")
        assert select_persona(reqs) == ResumePersona.ENGINEERING_TURNAROUND_SPECIALIST

    def test_growth_language_selects_growth_persona(self):
        reqs = JobRequirements(role_summary="Help us scale our engineering org through hypergrowth.")
        assert select_persona(reqs) == ResumePersona.GROWTH_ENGINEERING_LEADER

    def test_default_persona_is_technical_delivery_leader(self):
        reqs = JobRequirements(required_skills=["Python"])
        assert select_persona(reqs) == ResumePersona.TECHNICAL_DELIVERY_LEADER


class TestResumeStrategyOutput:
    async def test_director_role_emphasizes_manager_of_managers(self, profile, selection_service):
        reqs = JobRequirements(director_level_or_above=True)
        selection = selection_service.select_achievements(1, reqs)
        strategy = await ResumeStrategyService().build_strategy(1, reqs, profile, selection)
        assert "manager-of-managers" in strategy.emphasize

    async def test_ai_role_emphasizes_ai_transformation(self, profile, selection_service):
        reqs = JobRequirements(ai_requirements=["LLM"])
        selection = selection_service.select_achievements(1, reqs)
        strategy = await ResumeStrategyService().build_strategy(1, reqs, profile, selection)
        assert "AI Transformation" in strategy.key_themes
        assert "AI Transformation" in strategy.emphasize

    async def test_pl_responsibility_emphasized_when_required(self, profile, selection_service):
        reqs = JobRequirements(p_and_l_responsibility=True)
        selection = selection_service.select_achievements(1, reqs)
        strategy = await ResumeStrategyService().build_strategy(1, reqs, profile, selection)
        assert "P&L ownership" in strategy.emphasize

    async def test_unmatched_technologies_are_deemphasized(self, profile, selection_service):
        reqs = JobRequirements(required_skills=["Python"])  # profile has Go/AWS/etc too
        selection = selection_service.select_achievements(1, reqs)
        strategy = await ResumeStrategyService().build_strategy(1, reqs, profile, selection)
        assert "legacy technologies" in strategy.deemphasize

    async def test_strategy_carries_boost_multiplier(self, profile, selection_service):
        reqs = JobRequirements(required_skills=["Python"])
        selection = selection_service.select_achievements(
            1, reqs, boosted_accomplishment_ids=["X"], boost_multiplier=2.5
        )
        strategy = await ResumeStrategyService().build_strategy(
            1, reqs, profile, selection, boost_multiplier=2.5
        )
        assert strategy.boost_multiplier == 2.5
        assert strategy.boosted_accomplishment_ids == ["X"]
