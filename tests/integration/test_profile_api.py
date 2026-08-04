"""Integration tests for the profile API."""

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_PROFILE_DATA


class TestProfileAPI:
    @pytest.mark.asyncio
    async def test_get_profile_when_empty_returns_404(self, client: AsyncClient):
        response = await client.get("/api/v1/profile")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_profile(self, client: AsyncClient):
        response = await client.put(
            "/api/v1/profile",
            json=SAMPLE_PROFILE_DATA,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Jane Smith"

    @pytest.mark.asyncio
    async def test_get_profile_after_creation(self, client: AsyncClient):
        await client.put("/api/v1/profile", json=SAMPLE_PROFILE_DATA)
        response = await client.get("/api/v1/profile")
        assert response.status_code == 200
        assert response.json()["full_name"] == "Jane Smith"

    @pytest.mark.asyncio
    async def test_update_profile(self, client: AsyncClient):
        await client.put("/api/v1/profile", json=SAMPLE_PROFILE_DATA)
        updated = {**SAMPLE_PROFILE_DATA, "full_name": "Jane Doe", "current_title": "VP Engineering"}
        response = await client.put("/api/v1/profile", json=updated)
        assert response.status_code == 200
        assert response.json()["full_name"] == "Jane Doe"

    @pytest.mark.asyncio
    async def test_profile_contains_nested_data(self, client: AsyncClient):
        await client.put("/api/v1/profile", json=SAMPLE_PROFILE_DATA)
        response = await client.get("/api/v1/profile")
        data = response.json()
        profile = data["profile_data"]
        assert "work_history" in profile
        assert len(profile["work_history"]) == 1
        assert profile["work_history"][0]["company"] == "TechCorp"
        assert profile["leadership_experience"]["manager_of_managers"] is True
        assert "AWS Solutions Architect - Professional" in [
            c["name"] for c in profile["certifications"]
        ]
