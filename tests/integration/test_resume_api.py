"""Integration tests for the resume API — full pipeline via HTTP."""

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


class TestResumeAPI:
    @pytest.mark.asyncio
    async def test_build_resume_plan_returns_201(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)

        response = await client.post(f"/api/v1/resume/{job_id}", json={})
        assert response.status_code == 201
        data = response.json()
        assert data["job_posting_id"] == job_id
        assert data["markdown"]
        assert data["selection"]["selected_accomplishment_ids"] or data["selection"]["rankings"] == []
        assert "keyword_coverage" in data
        assert "quality_score" in data

    @pytest.mark.asyncio
    async def test_build_resume_plan_without_profile_returns_404(self, client: AsyncClient):
        job_resp = await client.post("/api/v1/jobs", json={"raw_text": SAMPLE_JOB_TEXT})
        job_id = job_resp.json()["id"]
        await client.post(f"/api/v1/analysis/{job_id}")

        response = await client.post(f"/api/v1/resume/{job_id}", json={})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_build_resume_plan_without_analysis_returns_404(self, client: AsyncClient):
        await client.put("/api/v1/profile", json=SAMPLE_PROFILE_DATA)
        job_resp = await client.post("/api/v1/jobs", json={"raw_text": SAMPLE_JOB_TEXT})
        job_id = job_resp.json()["id"]

        response = await client.post(f"/api/v1/resume/{job_id}", json={})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_resume_plan_before_generation_returns_404(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)
        response = await client.get(f"/api/v1/resume/{job_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_resume_plan_after_generation(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)
        await client.post(f"/api/v1/resume/{job_id}", json={})

        response = await client.get(f"/api/v1/resume/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_posting_id"] == job_id

    @pytest.mark.asyncio
    async def test_boosted_accomplishments_reflected_in_strategy(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)

        response = await client.post(
            f"/api/v1/resume/{job_id}",
            json={
                "boosted_accomplishment_ids": ["JJK-002"],
                "boost_multiplier": 2.0,
                "export_preferences": {
                    "reactive_resume_template": "gengar",
                    "reactive_resume_page_format": "a4",
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["strategy"]["boosted_accomplishment_ids"] == ["JJK-002"]
        assert data["strategy"]["boost_multiplier"] == 2.0
        assert data["export_preferences"]["reactive_resume_template"] == "gengar"
        assert data["export_preferences"]["reactive_resume_page_format"] == "a4"

    @pytest.mark.asyncio
    async def test_persona_override_sets_selected_persona_and_keeps_recommendation(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)

        response = await client.post(
            f"/api/v1/resume/{job_id}",
            json={
                "persona_override": "Cloud Transformation Leader",
            },
        )
        assert response.status_code == 201
        data = response.json()
        strategy = data["strategy"]

        assert strategy["persona"] == "Cloud Transformation Leader"
        assert strategy["recommended_persona"] is not None

    @pytest.mark.asyncio
    async def test_download_resume_docx(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)
        await client.post(f"/api/v1/resume/{job_id}", json={})

        response = await client.get(f"/api/v1/resume/{job_id}/download/docx")
        assert response.status_code == 200
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in response.headers["content-type"]
        )
        assert len(response.content) > 0

    @pytest.mark.asyncio
    async def test_download_resume_pdf(self, client: AsyncClient):
        job_id = await _setup_profile_and_analyzed_job(client)
        await client.post(f"/api/v1/resume/{job_id}", json={})

        response = await client.get(f"/api/v1/resume/{job_id}/download/pdf")
        assert response.status_code == 200
        assert "application/pdf" in response.headers["content-type"]
        assert len(response.content) > 0
