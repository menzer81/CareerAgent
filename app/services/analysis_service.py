"""Job analysis service — uses LLM to extract structured requirements."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LLMNotConfiguredError, NotFoundError
from app.models.analysis import JobAnalysis
from app.repositories.job_analysis_repository import JobAnalysisRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.analysis import JobRequirements
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, session: AsyncSession, llm: BaseLLMProvider | None) -> None:
        self.job_repo = JobPostingRepository(session)
        self.analysis_repo = JobAnalysisRepository(session)
        self.llm = llm

    async def analyze_job(self, job_posting_id: int) -> JobAnalysis:
        """Extract structured requirements from a job posting via LLM and persist."""
        if self.llm is None:
            raise LLMNotConfiguredError()

        posting = await self.job_repo.get(job_posting_id)
        if posting is None:
            raise NotFoundError("JobPosting", job_posting_id)

        logger.info("Extracting requirements for job_posting_id=%d", job_posting_id)
        requirements: JobRequirements = await self.llm.extract_job_requirements(posting.raw_text)

        # Back-fill title/company on the posting if the LLM found them
        if not posting.title and requirements.inferred_title:
            posting.title = requirements.inferred_title
        if not posting.company and requirements.inferred_company:
            posting.company = requirements.inferred_company

        analysis = await self.analysis_repo.upsert(
            job_posting_id=job_posting_id,
            requirements_data=requirements.model_dump(),
        )
        logger.info("Analysis stored for job_posting_id=%d analysis_id=%d", job_posting_id, analysis.id)
        return analysis

    async def get_analysis(self, job_posting_id: int) -> JobAnalysis | None:
        return await self.analysis_repo.get_by_job_id(job_posting_id)
