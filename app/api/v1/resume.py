"""Resume API router — achievement selection, resume strategy, and generation."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_resume_llm_provider
from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.database import get_db
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import ExportPreferences, ResumeBuildRequest, ResumePlan
from app.services.achievement_selection_service import DEFAULT_BOOST_MULTIPLIER, DEFAULT_TOP_N
from app.services.llm.base import BaseLLMProvider
from app.services.resume_export_service import ResumeExportService
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/{job_id}", response_model=ResumePlan, status_code=status.HTTP_201_CREATED)
async def build_resume_plan(
    job_id: int,
    payload: ResumeBuildRequest,
    db: AsyncSession = Depends(get_db),
    llm: BaseLLMProvider | None = Depends(get_resume_llm_provider),
) -> ResumePlan:
    """Run the achievement selection + resume strategy + generation pipeline.

    Requires the candidate profile to be loaded and the job to already be
    analyzed (``POST /api/v1/analysis/{job_id}`` or ``/extract``).
    """
    try:
        service = ResumeService(db, llm)
        return await service.build_plan(
            job_id,
            boosted_accomplishment_ids=payload.boosted_accomplishment_ids or None,
            boost_multiplier=payload.boost_multiplier,
            top_n=payload.top_n,
            export_preferences=payload.export_preferences,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=ResumePlan)
async def get_resume_plan(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResumePlan:
    """Get the most recently generated resume plan for a job posting."""
    service = ResumeService(db)
    record = await service.get_plan(job_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No resume plan found for job {job_id}. Run POST /api/v1/resume/{job_id} first.",
        )
    return ResumePlan.model_validate(record.plan_data)


@router.get("/{job_id}/download/docx")
async def download_resume_docx(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    service = ResumeService(db)
    record = await service.get_plan(job_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No resume plan found for job {job_id}. Run POST /api/v1/resume/{job_id} first.",
        )

    plan = ResumePlan.model_validate(record.plan_data)
    try:
        path = ResumeExportService().save_docx(job_id, plan)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@router.get("/{job_id}/download/pdf")
async def download_resume_pdf(
    job_id: int,
    template: str | None = Query(default=None),
    page_format: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    service = ResumeService(db)
    record = await service.get_plan(job_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No resume plan found for job {job_id}. Run POST /api/v1/resume/{job_id} first.",
        )

    plan = ResumePlan.model_validate(record.plan_data)
    if template or page_format:
        plan = plan.model_copy(
            update={
                "export_preferences": ExportPreferences(
                    reactive_resume_template=template or plan.export_preferences.reactive_resume_template,
                    reactive_resume_page_format=page_format
                    or plan.export_preferences.reactive_resume_page_format,
                )
            }
        )
    profile_record = await service.profile_repo.get_profile()
    if profile_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candidate profile found. Create one via PUT /api/v1/profile.",
        )

    profile = CandidateProfileData.model_validate(profile_record.profile_data)
    try:
        path = await ResumeExportService().save_pdf(job_id, plan, profile)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=path.name,
    )
