"""Integration tests for the jobs API."""

import pytest
from httpx import AsyncClient


class TestJobsAPI:
    @pytest.mark.asyncio
    async def test_ingest_job_returns_201(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/jobs",
            json={
                "raw_text": (
                    "# Senior Engineering Manager\n\n"
                    "We need a strong engineering manager with Python, AWS, and team leadership experience. "
                    "8+ years required. Manager of managers preferred."
                ),
                "title": "Senior Engineering Manager",
                "company": "Acme Corp",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["title"] == "Senior Engineering Manager"
        assert data["company"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_list_jobs_returns_empty(self, client: AsyncClient):
        response = await client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_jobs_after_ingest(self, client: AsyncClient):
        await client.post(
            "/api/v1/jobs",
            json={"raw_text": "Senior Python Engineer needed with 5+ years experience and AWS skills."},
        )
        response = await client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_get_job_by_id(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/jobs",
            json={"raw_text": "Staff Engineer role requiring Python, Go, and distributed systems experience."},
        )
        job_id = create_resp.json()["id"]
        response = await client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["id"] == job_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_returns_404(self, client: AsyncClient):
        response = await client.get("/api/v1/jobs/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_job(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/jobs",
            json={"raw_text": "Director of Engineering role with Python and cloud platform background required."},
        )
        job_id = create_resp.json()["id"]
        del_resp = await client.delete(f"/api/v1/jobs/{job_id}")
        assert del_resp.status_code == 204
        get_resp = await client.get(f"/api/v1/jobs/{job_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_job_returns_404(self, client: AsyncClient):
        response = await client.delete("/api/v1/jobs/99999")
        assert response.status_code == 404
