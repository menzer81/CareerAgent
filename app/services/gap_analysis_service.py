"""Gap analysis service.

The gap analysis is computed as part of the scoring pipeline. This service provides
a dedicated entry point for fetching or re-computing just the gap analysis portion
of an existing scoring result.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError
from app.repositories.job_analysis_repository import ScoringResultRepository
from app.schemas.scoring import FullAnalysisResult, GapAnalysis

logger = logging.getLogger(__name__)


class GapAnalysisService:
    def __init__(self, session: AsyncSession) -> None:
        self.scoring_repo = ScoringResultRepository(session)

    async def get_gap_analysis(self, job_posting_id: int) -> GapAnalysis:
        """Return the gap analysis for a previously scored job posting."""
        record = await self.scoring_repo.get_by_job_id(job_posting_id)
        if record is None:
            raise AnalysisNotFoundError(job_posting_id)

        result = FullAnalysisResult.model_validate(record.scoring_data)
        return result.gap_analysis
