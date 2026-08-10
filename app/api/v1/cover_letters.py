"""Cover letter API router."""

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.database import get_db
from app.schemas.career_documents import CoverLetterDraft, CoverLetterOptions
from app.services.cover_letter_service import CoverLetterService

router = APIRouter(prefix="/cover-letters", tags=["cover-letters"])


@router.post("/{job_id}", response_model=CoverLetterDraft, status_code=status.HTTP_201_CREATED)
async def build_cover_letter(
    job_id: int,
    options: CoverLetterOptions = Body(default_factory=CoverLetterOptions),
    db: AsyncSession = Depends(get_db),
) -> CoverLetterDraft:
    try:
        service = CoverLetterService(db)
        return await service.build_letter(job_id, tone=options.tone, style=options.style)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{job_id}", response_class=PlainTextResponse)
async def get_cover_letter(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> str:
    service = CoverLetterService(db)
    letter = await service.get_letter(job_id)
    if letter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cover letter found for job {job_id}. Run POST /api/v1/cover-letters/{job_id} first.",
        )
    return letter.markdown


@router.get("/{job_id}/download")
async def download_cover_letter(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        service = CoverLetterService(db)
        path = await service.save_letter(job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return FileResponse(
        path=str(path),
        media_type="text/markdown",
        filename=path.name,
    )
