"""Integration tests for cover letter API."""

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_JOB_TEXT, SAMPLE_PROFILE_DATA


async def _setup_profile_and_analyzed_job(client: AsyncClient) -> int:
    await client.put("/api/v1/profile", json=SAMPLE_PROFILE_DATA)
    job_resp = await client.post("/api/v1/jobs", json={"raw_text": SAMPLE_JOB_TEXT})
    job_id = job_resp.json()["id"]
    analysis_resp = await client.post(f"/api/v1/analysis/{job_id}")
    assert analysis_resp.status_code == 201
    return job_id


class TestCoverLettersAPI:
    @pytest.mark.asyncio
    async def test_build_cover_letter_returns_201(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)

        response = await client.post(f"/api/v1/cover-letters/{job_id}")
        assert response.status_code == 201
        data = response.json()
        assert data["job_posting_id"] == job_id
        assert data["subject_line"]
        assert data["markdown"]
        assert data["tone"] == "professional"
        assert data["style"] == "concise"

    @pytest.mark.asyncio
    async def test_build_cover_letter_with_custom_tone_and_style(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)

        response = await client.post(
            f"/api/v1/cover-letters/{job_id}",
            json={"tone": "confident", "style": "executive"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["tone"] == "confident"
        assert data["style"] == "executive"

    @pytest.mark.asyncio
    async def test_get_cover_letter_markdown(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)
        await client.post(f"/api/v1/cover-letters/{job_id}")

        response = await client.get(f"/api/v1/cover-letters/{job_id}")
        assert response.status_code == 200
        assert response.text.startswith("# ")

    @pytest.mark.asyncio
    async def test_download_cover_letter(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)
        await client.post(f"/api/v1/cover-letters/{job_id}")

        response = await client.get(f"/api/v1/cover-letters/{job_id}/download")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_build_cover_letter_without_analysis_returns_404(self, client: AsyncClient):
        await client.put("/api/v1/profile", json=SAMPLE_PROFILE_DATA)
        job_resp = await client.post("/api/v1/jobs", json={"raw_text": SAMPLE_JOB_TEXT})
        job_id = job_resp.json()["id"]

        response = await client.post(f"/api/v1/cover-letters/{job_id}")
        assert response.status_code == 404
