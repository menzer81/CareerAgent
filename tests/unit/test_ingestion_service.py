"""Unit tests for the ingestion service."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion_service import IngestionService, normalize_text


class TestNormalizeText:
    def test_strips_trailing_whitespace(self):
        result = normalize_text("  hello world  ")
        assert result == "hello world"

    def test_collapses_excessive_blank_lines(self):
        text = "line1\n\n\n\n\nline2"
        result = normalize_text(text)
        assert "\n\n\n" not in result

    def test_preserves_content(self):
        text = "# Job Title\n\nRequirements:\n- Python\n- AWS"
        result = normalize_text(text)
        assert "Job Title" in result
        assert "Python" in result
        assert "AWS" in result


class TestIngestionService:
    @pytest.mark.asyncio
    async def test_ingest_plain_text(self, db_session: AsyncSession):
        service = IngestionService(db_session)
        text = "Senior Software Engineer\nRequirements: Python, AWS, 5+ years experience."
        posting = await service.ingest_text(raw_text=text)
        assert posting.id is not None
        assert "Python" in posting.raw_text

    @pytest.mark.asyncio
    async def test_explicit_title_and_company_preserved(self, db_session: AsyncSession):
        service = IngestionService(db_session)
        posting = await service.ingest_text(
            raw_text="Some job description with lots of content here.",
            title="My Job Title",
            company="My Company",
        )
        assert posting.title == "My Job Title"
        assert posting.company == "My Company"

    @pytest.mark.asyncio
    async def test_markdown_heading_extracted_as_title(self, db_session: AsyncSession):
        service = IngestionService(db_session)
        text = "# Engineering Director\n\nWe are looking for a director..."
        posting = await service.ingest_text(raw_text=text)
        assert posting.title == "Engineering Director"

    @pytest.mark.asyncio
    async def test_source_url_stored(self, db_session: AsyncSession):
        service = IngestionService(db_session)
        url = "https://jobs.example.com/12345"
        posting = await service.ingest_text(
            raw_text="Some job description with lots of content here for testing purposes.",
            source_url=url,
        )
        assert posting.source_url == url

    @pytest.mark.asyncio
    async def test_multiple_postings_have_unique_ids(self, db_session: AsyncSession):
        service = IngestionService(db_session)
        p1 = await service.ingest_text("Job one: requires Python and AWS experience for backend role.")
        p2 = await service.ingest_text("Job two: requires Go and Kubernetes experience for platform role.")
        assert p1.id != p2.id
