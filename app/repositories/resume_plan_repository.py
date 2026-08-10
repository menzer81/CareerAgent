"""Repository for persisted resume plans."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import ResumePlanResult
from app.repositories.base import BaseRepository


class ResumePlanRepository(BaseRepository[ResumePlanResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ResumePlanResult, session)

    async def get_by_job_id(self, job_posting_id: int) -> ResumePlanResult | None:
        result = await self.session.execute(
            select(ResumePlanResult).where(ResumePlanResult.job_posting_id == job_posting_id)
        )
        return result.scalars().first()

    async def upsert(self, job_posting_id: int, plan_data: dict) -> ResumePlanResult:
        existing = await self.get_by_job_id(job_posting_id)
        if existing:
            existing.plan_data = plan_data
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(job_posting_id=job_posting_id, plan_data=plan_data)
