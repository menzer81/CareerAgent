"""Integration tests for interview prep API."""

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


class TestInterviewAPI:
    @pytest.mark.asyncio
    async def test_build_interview_prep_returns_201(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)

        response = await client.post(f"/api/v1/interview/{job_id}")
        assert response.status_code == 201
        data = response.json()
        assert data["job_posting_id"] == job_id
        assert data["opening_pitch"]
        assert len(data["likely_questions"]) > 0

    @pytest.mark.asyncio
    async def test_get_interview_prep_after_generation(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)
        await client.post(f"/api/v1/interview/{job_id}")

        response = await client.get(f"/api/v1/interview/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_posting_id"] == job_id

    @pytest.mark.asyncio
    async def test_build_interview_prep_without_profile_returns_404(self, client: AsyncClient):
        job_resp = await client.post("/api/v1/jobs", json={"raw_text": SAMPLE_JOB_TEXT})
        job_id = job_resp.json()["id"]
        await client.post(f"/api/v1/analysis/{job_id}")

        response = await client.post(f"/api/v1/interview/{job_id}")
        assert response.status_code == 404
