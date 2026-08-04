"""Profile API router — manage the candidate profile."""

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found_exception
from app.database import get_db
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.schemas.candidate_profile import CandidateProfileData, CandidateProfileResponse

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=CandidateProfileResponse)
async def get_profile(db: AsyncSession = Depends(get_db)) -> CandidateProfileResponse:
    """Retrieve the candidate profile."""
    repo = CandidateProfileRepository(db)
    profile = await repo.get_profile()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No candidate profile found. Create one via PUT /api/v1/profile.",
        )
    return CandidateProfileResponse.model_validate(profile)


@router.put("", response_model=CandidateProfileResponse, status_code=status.HTTP_200_OK)
async def upsert_profile(
    payload: CandidateProfileData,
    db: AsyncSession = Depends(get_db),
) -> CandidateProfileResponse:
    """Create or replace the candidate profile."""
    repo = CandidateProfileRepository(db)
    profile = await repo.upsert_profile(
        full_name=payload.full_name,
        profile_data=payload.model_dump(),
    )
    return CandidateProfileResponse.model_validate(profile)


@router.post("/upload", response_model=CandidateProfileResponse, status_code=status.HTTP_200_OK)
async def upload_profile(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> CandidateProfileResponse:
    """Upload a candidate profile from a JSON file."""
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid JSON file: {exc}",
        ) from exc

    payload = CandidateProfileData.model_validate(data)
    repo = CandidateProfileRepository(db)
    profile = await repo.upsert_profile(
        full_name=payload.full_name,
        profile_data=payload.model_dump(),
    )
    return CandidateProfileResponse.model_validate(profile)
