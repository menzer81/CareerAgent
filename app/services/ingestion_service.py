"""Job posting ingestion service."""

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_posting import JobPosting
from app.repositories.job_posting_repository import JobPostingRepository

logger = logging.getLogger(__name__)

# Basic patterns to try to auto-extract title/company from raw text
_TITLE_PATTERNS = [
    re.compile(r"(?:job title|position|role)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"^#+\s*(.+)$", re.MULTILINE),  # Markdown heading
]
_COMPANY_PATTERNS = [
    re.compile(r"(?:company|employer|organization|at\s+)[:\s]+([A-Z][^\n,]{2,60})", re.IGNORECASE),
    re.compile(r"^About\s+([A-Z][^\n,]{2,40})$", re.MULTILINE),
]


def _try_extract_field(text: str, patterns: list[re.Pattern]) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) > 2:
                return candidate
    return None


def normalize_text(raw: str) -> str:
    """Clean up excess whitespace while preserving structure."""
    lines = [line.rstrip() for line in raw.splitlines()]
    # Collapse runs of blank lines into at most 2
    result: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 1:
                result.append(line)
        else:
            blank_run = 0
            result.append(line)
    return "\n".join(result).strip()


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = JobPostingRepository(session)

    async def ingest_text(
        self,
        raw_text: str,
        title: str | None = None,
        company: str | None = None,
        source_url: str | None = None,
    ) -> JobPosting:
        """Normalize and store a job posting. Auto-extracts title/company if not provided."""
        normalized = normalize_text(raw_text)

        resolved_title = title or _try_extract_field(normalized, _TITLE_PATTERNS)
        resolved_company = company or _try_extract_field(normalized, _COMPANY_PATTERNS)

        posting = await self.repo.create_posting(
            raw_text=normalized,
            title=resolved_title,
            company=resolved_company,
            source_url=source_url,
        )
        logger.info(
            "Ingested job posting id=%d title=%r company=%r",
            posting.id,
            posting.title,
            posting.company,
        )
        return posting
