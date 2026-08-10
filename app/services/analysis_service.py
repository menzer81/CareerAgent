"""Job analysis service — uses LLM to extract structured requirements,
falling back to rule-based heuristics when no LLM is configured."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.models.analysis import JobAnalysis
from app.repositories.job_analysis_repository import JobAnalysisRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.analysis import JobRequirements
from app.services.llm.base import BaseLLMProvider
from app.services.requirement_extraction_service import heuristic_extract_requirements

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, session: AsyncSession, llm: BaseLLMProvider | None) -> None:
        self.job_repo = JobPostingRepository(session)
        self.analysis_repo = JobAnalysisRepository(session)
        self.llm = llm
        self.llm_extract_timeout_seconds = get_settings().llm_extract_timeout_seconds

    async def analyze_job(self, job_posting_id: int) -> JobAnalysis:
        """Extract structured requirements from a job posting and persist.

        Uses the LLM when configured; falls back to heuristic/rule-based
        extraction otherwise so the pipeline works without an API key.
        """
        posting = await self.job_repo.get(job_posting_id)
        if posting is None:
            raise NotFoundError("JobPosting", job_posting_id)

        if self.llm is not None:
            logger.info("Extracting requirements via LLM for job_posting_id=%d", job_posting_id)
            try:
                requirements = await asyncio.wait_for(
                    self.llm.extract_job_requirements(posting.raw_text),
                    timeout=self.llm_extract_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "LLM extraction timed out after %ds for job_posting_id=%d; falling back to heuristics",
                    self.llm_extract_timeout_seconds,
                    job_posting_id,
                )
                requirements = heuristic_extract_requirements(posting.raw_text)
            except Exception as exc:
                logger.warning(
                    "LLM extraction failed for job_posting_id=%d; falling back to heuristics: %s",
                    job_posting_id,
                    exc,
                )
                requirements = heuristic_extract_requirements(posting.raw_text)
        else:
            logger.info(
                "Extracting requirements via rule-based heuristics for job_posting_id=%d",
                job_posting_id,
            )
            requirements = heuristic_extract_requirements(posting.raw_text)

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
