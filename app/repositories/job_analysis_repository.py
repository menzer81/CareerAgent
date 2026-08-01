"""Repository for job analyses and scoring results."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import JobAnalysis, ScoringResult
from app.repositories.base import BaseRepository


class JobAnalysisRepository(BaseRepository[JobAnalysis]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(JobAnalysis, session)

    async def get_by_job_id(self, job_posting_id: int) -> JobAnalysis | None:
        result = await self.session.execute(
            select(JobAnalysis).where(JobAnalysis.job_posting_id == job_posting_id)
        )
        return result.scalars().first()

    async def upsert(self, job_posting_id: int, requirements_data: dict) -> JobAnalysis:
        existing = await self.get_by_job_id(job_posting_id)
        if existing:
            existing.requirements_data = requirements_data
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(
            job_posting_id=job_posting_id,
            requirements_data=requirements_data,
        )


class ScoringResultRepository(BaseRepository[ScoringResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ScoringResult, session)

    async def get_by_job_id(self, job_posting_id: int) -> ScoringResult | None:
        result = await self.session.execute(
            select(ScoringResult).where(ScoringResult.job_posting_id == job_posting_id)
        )
        return result.scalars().first()

    async def upsert(self, job_posting_id: int, scoring_data: dict) -> ScoringResult:
        existing = await self.get_by_job_id(job_posting_id)
        if existing:
            existing.scoring_data = scoring_data
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(
            job_posting_id=job_posting_id,
            scoring_data=scoring_data,
        )
