"""Pydantic schemas for job postings."""

from datetime import datetime

from pydantic import BaseModel, Field


class JobPostingCreate(BaseModel):
    raw_text: str = Field(..., min_length=50, description="Full job posting text")
    title: str | None = Field(None, description="Job title (auto-extracted if not provided)")
    company: str | None = Field(None, description="Company name (auto-extracted if not provided)")
    source_url: str | None = Field(None, description="Source URL of the posting")


class JobPostingResponse(BaseModel):
    id: int
    title: str | None
    company: str | None
    source_url: str | None
    raw_text: str
    ingested_at: datetime

    model_config = {"from_attributes": True}


class JobPostingSummary(BaseModel):
    """Lightweight summary without raw_text for list views."""

    id: int
    title: str | None
    company: str | None
    source_url: str | None
    ingested_at: datetime

    model_config = {"from_attributes": True}
