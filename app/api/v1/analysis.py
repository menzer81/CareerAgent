"""Analysis API router — trigger and retrieve job analyses."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_llm_provider
from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.database import get_db
from app.repositories.job_analysis_repository import JobAnalysisRepository, ScoringResultRepository
from app.schemas.analysis import JobAnalysisResponse, JobRequirements
from app.schemas.scoring import FullAnalysisResult, ScoringResultResponse
from app.services.analysis_service import AnalysisService
from app.services.llm.base import BaseLLMProvider
from app.services.scoring_service import ScoringService

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/{job_id}", response_model=ScoringResultResponse, status_code=status.HTTP_201_CREATED)
async def run_analysis(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    llm: BaseLLMProvider | None = Depends(get_llm_provider),
) -> ScoringResultResponse:
    """Run full analysis (extraction + scoring) on a job posting.

    Requires a candidate profile to be loaded. LLM is used when configured;
    rule-based heuristics/scoring are used as fallback when it is not.
    """
    try:
        analysis_svc = AnalysisService(db, llm)
        await analysis_svc.analyze_job(job_id)

        scoring_svc = ScoringService(db, llm)
        scoring = await scoring_svc.score_job(job_id)
        return ScoringResultResponse.model_validate(scoring)

    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{job_id}/extract", response_model=JobAnalysisResponse, status_code=status.HTTP_201_CREATED)
async def extract_requirements(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    llm: BaseLLMProvider | None = Depends(get_llm_provider),
) -> JobAnalysisResponse:
    """Extract structured requirements from a job posting (no scoring)."""
    try:
        service = AnalysisService(db, llm)
        analysis = await service.analyze_job(job_id)
        requirements = JobRequirements.model_validate(analysis.requirements_data)
        return JobAnalysisResponse(
            id=analysis.id,
            job_posting_id=analysis.job_posting_id,
            requirements_data=requirements,
            analyzed_at=analysis.analyzed_at,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{job_id}/score", response_model=ScoringResultResponse, status_code=status.HTTP_201_CREATED)
async def score_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    llm: BaseLLMProvider | None = Depends(get_llm_provider),
) -> ScoringResultResponse:
    """Score a job posting that has already been analyzed. Requires prior /extract call."""
    try:
        service = ScoringService(db, llm)
        scoring = await service.score_job(job_id)
        return ScoringResultResponse.model_validate(scoring)
    except (NotFoundError, AnalysisNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=ScoringResultResponse)
async def get_analysis(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> ScoringResultResponse:
    """Get the latest scoring result for a job posting."""
    repo = ScoringResultRepository(db)
    record = await repo.get_by_job_id(job_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis found for job {job_id}. Run POST /api/v1/analysis/{job_id} first.",
        )
    return ScoringResultResponse.model_validate(record)


@router.get("", response_model=list[ScoringResultResponse])
async def list_analyses(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[ScoringResultResponse]:
    """List all scoring results."""
    repo = ScoringResultRepository(db)
    records = await repo.get_all(limit=limit, offset=offset)
    return [ScoringResultResponse.model_validate(r) for r in records]
