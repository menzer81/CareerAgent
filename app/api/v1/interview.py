"""Interview prep API router."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.database import get_db
from app.schemas.career_documents import InterviewPrepPlan
from app.services.interview_prep_service import InterviewPrepService

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/{job_id}", response_model=InterviewPrepPlan, status_code=status.HTTP_201_CREATED)
async def build_interview_prep(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> InterviewPrepPlan:
    try:
        service = InterviewPrepService(db)
        return await service.build_prep(job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=InterviewPrepPlan)
async def get_interview_prep(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> InterviewPrepPlan:
    service = InterviewPrepService(db)
    prep = await service.get_prep(job_id)
    if prep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No interview prep found for job {job_id}. Run POST /api/v1/interview/{job_id} first.",
        )
    return prep
