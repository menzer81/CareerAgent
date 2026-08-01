"""Repository for job postings."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_posting import JobPosting
from app.repositories.base import BaseRepository


class JobPostingRepository(BaseRepository[JobPosting]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(JobPosting, session)

    async def create_posting(
        self,
        raw_text: str,
        title: str | None = None,
        company: str | None = None,
        source_url: str | None = None,
    ) -> JobPosting:
        return await self.create(
            raw_text=raw_text,
            title=title,
            company=company,
            source_url=source_url,
        )
