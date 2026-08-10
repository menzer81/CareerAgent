"""Integration tests for background analysis processing."""

import asyncio

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_JOB_TEXT, SAMPLE_PROFILE_DATA


class TestAnalysisBackgroundAPI:
    @pytest.mark.asyncio
    async def test_background_analysis_submits_and_completes(self, client: AsyncClient):
        await client.put("/api/v1/profile", json=SAMPLE_PROFILE_DATA)
        job_resp = await client.post("/api/v1/jobs", json={"raw_text": SAMPLE_JOB_TEXT})
        job_id = job_resp.json()["id"]

        submit_resp = await client.post(f"/api/v1/analysis/{job_id}/background")
        assert submit_resp.status_code == 202
        payload = submit_resp.json()
        assert payload["job_posting_id"] == job_id
        assert payload["status"] == "queued"
        assert payload["poll_url"] == f"/api/v1/analysis/{job_id}/status"

        completed = False
        for _ in range(20):
            status_resp = await client.get(f"/api/v1/analysis/{job_id}/status")
            status_payload = status_resp.json()
            if status_payload["status"] == "succeeded":
                completed = True
                break
            await asyncio.sleep(0.05)

        assert completed is True

        final_status = await client.get(f"/api/v1/analysis/{job_id}/status")
        assert final_status.status_code == 200
        assert final_status.json()["result_ready"] is True

        analysis_resp = await client.get(f"/api/v1/analysis/{job_id}")
        assert analysis_resp.status_code == 200
        assert analysis_resp.json()["job_posting_id"] == job_id
