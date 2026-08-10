"""Resume Service — orchestrates the full Sprint 1-3 resume pipeline.

    Job + Requirements
        -> Achievement Selection (AchievementSelectionService)
        -> Resume Strategy       (ResumeStrategyService)
        -> Keyword Coverage      (KeywordCoverageService)
        -> Resume Data Model     (ResumeDataModelService)
        -> Resume Document       (ResumeDocumentService + MarkdownResumeRenderer)
        -> Resume Quality Score  (ResumeQualityScoringService)
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.models.resume import ResumePlanResult
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.job_analysis_repository import JobAnalysisRepository
from app.repositories.resume_plan_repository import ResumePlanRepository
from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import ResumePlan
from app.services.accomplishment_loader import load_accomplishments
from app.services.achievement_selection_service import (
    DEFAULT_BOOST_MULTIPLIER,
    DEFAULT_TOP_N,
    AchievementSelectionService,
)
from app.services.keyword_coverage_service import KeywordCoverageService
from app.services.resume_data_model_service import ResumeDataModelService
from app.services.resume_document_service import MarkdownResumeRenderer, ResumeDocumentService
from app.services.resume_quality_service import ResumeQualityScoringService
from app.services.resume_strategy_service import ResumeStrategyService

logger = logging.getLogger(__name__)


class ResumeService:
    def __init__(self, session: AsyncSession) -> None:
        self.profile_repo = CandidateProfileRepository(session)
        self.analysis_repo = JobAnalysisRepository(session)
        self.plan_repo = ResumePlanRepository(session)

        accomplishments = load_accomplishments()
        self.achievement_service = AchievementSelectionService(accomplishments)
        self.strategy_service = ResumeStrategyService()
        self.coverage_service = KeywordCoverageService()
        self.data_model_service = ResumeDataModelService()
        self.document_service = ResumeDocumentService()
        self.renderer = MarkdownResumeRenderer()
        self.quality_service = ResumeQualityScoringService()

    async def build_plan(
        self,
        job_posting_id: int,
        boosted_accomplishment_ids: list[str] | None = None,
        boost_multiplier: float = DEFAULT_BOOST_MULTIPLIER,
        top_n: int = DEFAULT_TOP_N,
    ) -> ResumePlan:
        profile_record = await self.profile_repo.get_profile()
        if profile_record is None:
            raise NotFoundError("CandidateProfile", "singleton")

        analysis_record = await self.analysis_repo.get_by_job_id(job_posting_id)
        if analysis_record is None:
            raise AnalysisNotFoundError(job_posting_id)

        profile = CandidateProfileData.model_validate(profile_record.profile_data)
        requirements = JobRequirements.model_validate(analysis_record.requirements_data)

        plan = self.build_plan_from_data(
            job_posting_id,
            profile,
            requirements,
            boosted_accomplishment_ids=boosted_accomplishment_ids,
            boost_multiplier=boost_multiplier,
            top_n=top_n,
        )

        await self.plan_repo.upsert(job_posting_id, plan.model_dump())
        return plan

    def build_plan_from_data(
        self,
        job_posting_id: int,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        boosted_accomplishment_ids: list[str] | None = None,
        boost_multiplier: float = DEFAULT_BOOST_MULTIPLIER,
        top_n: int = DEFAULT_TOP_N,
    ) -> ResumePlan:
        """Run the full pipeline purely in-memory (no DB access) — used by tests too."""
        selection = self.achievement_service.select_achievements(
            job_posting_id,
            requirements,
            boosted_accomplishment_ids=boosted_accomplishment_ids,
            boost_multiplier=boost_multiplier,
            top_n=top_n,
        )
        strategy = self.strategy_service.build_strategy(
            job_posting_id, requirements, profile, selection, boost_multiplier=boost_multiplier
        )
        coverage = self.coverage_service.compute_coverage(requirements, profile)
        data_model = self.data_model_service.build(
            job_posting_id,
            requirements,
            profile,
            strategy,
            selection,
            coverage,
            accomplishments=self.achievement_service.accomplishments,
        )
        document = self.document_service.build(
            profile, data_model, strategy, accomplishments=self.achievement_service.accomplishments
        )
        markdown = self.renderer.render(document)
        quality_score = self.quality_service.score(profile, requirements, coverage)

        return ResumePlan(
            job_posting_id=job_posting_id,
            selection=selection,
            strategy=strategy,
            keyword_coverage=coverage,
            data_model=data_model,
            quality_score=quality_score,
            markdown=markdown,
        )

    async def get_plan(self, job_posting_id: int) -> ResumePlanResult | None:
        return await self.plan_repo.get_by_job_id(job_posting_id)
