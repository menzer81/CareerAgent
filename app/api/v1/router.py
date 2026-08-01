"""v1 API router — aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.v1.jobs import router as jobs_router
from app.api.v1.profile import router as profile_router
from app.api.v1.analysis import router as analysis_router
from app.api.v1.reports import router as reports_router

router = APIRouter(prefix="/api/v1")

router.include_router(jobs_router)
router.include_router(profile_router)
router.include_router(analysis_router)
router.include_router(reports_router)
