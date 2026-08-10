"""Repositories for interview prep and cover letter artifacts."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career_documents import CoverLetterResult, InterviewPrepResult
from app.repositories.base import BaseRepository


class InterviewPrepRepository(BaseRepository[InterviewPrepResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(InterviewPrepResult, session)

    async def get_by_job_id(self, job_posting_id: int) -> InterviewPrepResult | None:
        result = await self.session.execute(
            select(InterviewPrepResult).where(InterviewPrepResult.job_posting_id == job_posting_id)
        )
        return result.scalars().first()

    async def upsert(self, job_posting_id: int, prep_data: dict) -> InterviewPrepResult:
        existing = await self.get_by_job_id(job_posting_id)
        if existing:
            existing.prep_data = prep_data
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(job_posting_id=job_posting_id, prep_data=prep_data)


class CoverLetterRepository(BaseRepository[CoverLetterResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CoverLetterResult, session)

    async def get_by_job_id(self, job_posting_id: int) -> CoverLetterResult | None:
        result = await self.session.execute(
            select(CoverLetterResult).where(CoverLetterResult.job_posting_id == job_posting_id)
        )
        return result.scalars().first()

    async def upsert(self, job_posting_id: int, letter_data: dict) -> CoverLetterResult:
        existing = await self.get_by_job_id(job_posting_id)
        if existing:
            existing.letter_data = letter_data
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(job_posting_id=job_posting_id, letter_data=letter_data)
