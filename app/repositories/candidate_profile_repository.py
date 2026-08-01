"""Repository for the single candidate profile."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate_profile import CandidateProfile
from app.repositories.base import BaseRepository


class CandidateProfileRepository(BaseRepository[CandidateProfile]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(CandidateProfile, session)

    async def get_profile(self) -> CandidateProfile | None:
        """Return the single candidate profile (there is only one)."""
        result = await self.session.execute(
            select(CandidateProfile).limit(1)
        )
        return result.scalars().first()

    async def upsert_profile(self, full_name: str, profile_data: dict) -> CandidateProfile:
        """Create or replace the candidate profile."""
        existing = await self.get_profile()
        if existing:
            existing.full_name = full_name
            existing.profile_data = profile_data
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(full_name=full_name, profile_data=profile_data)
