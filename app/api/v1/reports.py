"""Reports API router — generate and download markdown reports."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.database import get_db
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{job_id}", response_class=PlainTextResponse)
async def get_report(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Get the markdown report for a scored job posting."""
    try:
        service = ReportService(db)
        return await service.get_report(job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{job_id}/download")
async def download_report(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download the markdown report as a file."""
    try:
        service = ReportService(db)
        path = await service.save_report(job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return FileResponse(
        path=str(path),
        media_type="text/markdown",
        filename=path.name,
    )
