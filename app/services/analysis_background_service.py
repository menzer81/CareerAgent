"""Lightweight in-process background runner for long-running job analysis."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app import database as app_database
from app.services.analysis_service import AnalysisService
from app.services.llm.base import BaseLLMProvider
from app.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)


class AnalysisBackgroundStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class AnalysisBackgroundJob:
    job_posting_id: int
    status: AnalysisBackgroundStatus = AnalysisBackgroundStatus.QUEUED
    message: str = "Queued for background processing."
    error: str | None = None
    task: asyncio.Task[None] | None = None


class AnalysisBackgroundService:
    """Queue analysis/scoring work in the current process and expose status polling."""

    def __init__(self) -> None:
        self._jobs: dict[int, AnalysisBackgroundJob] = {}

    def submit_job(
        self,
        job_posting_id: int,
        llm: BaseLLMProvider | None,
        request_session: AsyncSession | None = None,
    ) -> AnalysisBackgroundJob:
        existing = self._jobs.get(job_posting_id)
        if existing is not None:
            if existing.status in {AnalysisBackgroundStatus.QUEUED, AnalysisBackgroundStatus.RUNNING}:
                return existing
            if existing.status in {AnalysisBackgroundStatus.SUCCEEDED, AnalysisBackgroundStatus.FAILED}:
                self._jobs.pop(job_posting_id, None)

        job = AnalysisBackgroundJob(job_posting_id=job_posting_id)
        self._jobs[job_posting_id] = job
        job.task = asyncio.create_task(self._run_job(job_posting_id, llm, job, request_session))
        return job

    def get_job(self, job_posting_id: int) -> AnalysisBackgroundJob | None:
        return self._jobs.get(job_posting_id)

    async def _run_job(
        self,
        job_posting_id: int,
        llm: BaseLLMProvider | None,
        job: AnalysisBackgroundJob,
        request_session: AsyncSession | None,
    ) -> None:
        job.status = AnalysisBackgroundStatus.RUNNING
        job.message = "Analysis in progress..."

        completed_work = False
        try:
            session_factory = getattr(app_database, "AsyncSessionLocal", None)
            if session_factory is None:
                raise RuntimeError("No AsyncSession factory available for background analysis")

            async with session_factory() as session:
                try:
                    analysis_service = AnalysisService(session, llm)
                    await analysis_service.analyze_job(job_posting_id)

                    scoring_service = ScoringService(session, llm)
                    await scoring_service.score_job(job_posting_id)
                    await session.commit()
                    completed_work = True
                except Exception:
                    await session.rollback()
                    raise
        except Exception as exc:  # pragma: no cover - defensive logging path
            if completed_work:
                logger.warning(
                    "Background analysis completed but session cleanup failed for job_posting_id=%d: %s",
                    job_posting_id,
                    exc,
                )
                job.status = AnalysisBackgroundStatus.SUCCEEDED
                job.message = "Analysis completed."
                return

            logger.exception("Background analysis failed for job_posting_id=%d", job_posting_id)
            job.status = AnalysisBackgroundStatus.FAILED
            job.message = "Analysis failed."
            job.error = str(exc)
            return

        job.status = AnalysisBackgroundStatus.SUCCEEDED
        job.message = "Analysis completed."


background_analysis_service = AnalysisBackgroundService()
