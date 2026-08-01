"""Jobs API router — ingest, list, get, delete job postings."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_llm_provider
from app.core.exceptions import NotFoundError, not_found_exception
from app.database import get_db
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.job_posting import JobPostingCreate, JobPostingResponse, JobPostingSummary
from app.services.ingestion_service import IngestionService
from app.services.llm.base import BaseLLMProvider

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobPostingResponse, status_code=status.HTTP_201_CREATED)
async def ingest_job_posting(
    payload: JobPostingCreate,
    db: AsyncSession = Depends(get_db),
) -> JobPostingResponse:
    """Ingest a job posting from a JSON body."""
    service = IngestionService(db)
    posting = await service.ingest_text(
        raw_text=payload.raw_text,
        title=payload.title,
        company=payload.company,
        source_url=payload.source_url,
    )
    return JobPostingResponse.model_validate(posting)


@router.post("/upload", response_model=JobPostingResponse, status_code=status.HTTP_201_CREATED)
async def upload_job_posting(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    company: str | None = Form(None),
    source_url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> JobPostingResponse:
    """Ingest a job posting from an uploaded text or markdown file."""
    content = await file.read()
    raw_text = content.decode("utf-8", errors="replace")
    service = IngestionService(db)
    posting = await service.ingest_text(
        raw_text=raw_text,
        title=title,
        company=company,
        source_url=source_url,
    )
    return JobPostingResponse.model_validate(posting)


@router.get("", response_model=list[JobPostingSummary])
async def list_job_postings(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[JobPostingSummary]:
    """List all stored job postings (summary view, no raw text)."""
    repo = JobPostingRepository(db)
    postings = await repo.get_all(limit=limit, offset=offset)
    return [JobPostingSummary.model_validate(p) for p in postings]


@router.get("/{job_id}", response_model=JobPostingResponse)
async def get_job_posting(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> JobPostingResponse:
    repo = JobPostingRepository(db)
    posting = await repo.get(job_id)
    if posting is None:
        raise not_found_exception("JobPosting", job_id)
    return JobPostingResponse.model_validate(posting)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_posting(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = JobPostingRepository(db)
    deleted = await repo.delete(job_id)
    if not deleted:
        raise not_found_exception("JobPosting", job_id)
