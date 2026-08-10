"""v1 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.cover_letters import router as cover_letters_router
from app.api.v1.interview import router as interview_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.profile import router as profile_router
from app.api.v1.reports import router as reports_router
from app.api.v1.resume import router as resume_router

router = APIRouter(prefix="/api/v1")

router.include_router(jobs_router)
router.include_router(profile_router)
router.include_router(analysis_router)
router.include_router(reports_router)
router.include_router(resume_router)
router.include_router(interview_router)
router.include_router(cover_letters_router)
