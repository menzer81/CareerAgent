"""Helpers for keeping the persisted candidate profile aligned with the canonical JSON file."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.schemas.candidate_profile import CandidateProfileData, CandidateProfileResponse


def canonical_profile_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "candidate_profile.json"


def load_canonical_profile() -> CandidateProfileData:
    profile_path = canonical_profile_path()
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    return CandidateProfileData.model_validate(raw)


async def sync_canonical_profile(session: AsyncSession) -> CandidateProfileResponse | None:
    profile_path = canonical_profile_path()
    if not profile_path.exists():
        return None

    profile = load_canonical_profile()
    repo = CandidateProfileRepository(session)
    record = await repo.upsert_profile(profile.full_name, profile.model_dump())
    await session.flush()
    await session.refresh(record)
    return CandidateProfileResponse.model_validate(record)