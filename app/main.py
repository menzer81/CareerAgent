"""CareerAgent FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.core.logging import configure_logging
from app.database import AsyncSessionLocal, init_db
from app.services.profile_sync_service import sync_canonical_profile

configure_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize DB on startup."""
    await init_db()
    async with AsyncSessionLocal() as session:
        await sync_canonical_profile(session)
        await session.commit()
    yield


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "Analyze software engineering job postings and score how well they match "
        "a candidate's experience and career goals."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok", "version": settings.app_version}
