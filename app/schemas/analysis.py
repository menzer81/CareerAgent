"""Pydantic schemas for job analysis (LLM-extracted requirements)."""

from datetime import datetime

from pydantic import BaseModel, Field


class JobRequirements(BaseModel):
    """Structured requirements extracted from a job posting by the LLM."""

    # Core requirements
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)

    # Leadership & management
    leadership_requirements: list[str] = Field(default_factory=list)
    manager_of_managers_required: bool = False
    director_level_or_above: bool = False
    min_team_size_managed: int | None = None
    max_team_size_managed: int | None = None
    p_and_l_responsibility: bool = False

    # Technical specialties
    cloud_requirements: list[str] = Field(
        default_factory=list, description="Required cloud platforms and services"
    )
    ai_requirements: list[str] = Field(
        default_factory=list, description="AI/ML experience requirements"
    )

    # Context
    industry_domain: list[str] = Field(
        default_factory=list, description="Industry or domain (e.g. fintech, healthcare)"
    )
    years_of_experience_min: int | None = None
    years_of_experience_max: int | None = None

    # Extracted metadata
    inferred_title: str | None = None
    inferred_company: str | None = None
    role_level: str | None = Field(
        None, description="e.g. Senior Manager, Director, VP, SVP"
    )
    is_remote: bool | None = None
    is_hybrid: bool | None = None

    # Keywords important for resume alignment
    important_keywords: list[str] = Field(default_factory=list)

    # Raw summary from LLM
    role_summary: str = ""


class JobAnalysisResponse(BaseModel):
    id: int
    job_posting_id: int
    requirements_data: JobRequirements
    analyzed_at: datetime

    model_config = {"from_attributes": True}


class BackgroundAnalysisSubmissionResponse(BaseModel):
    job_posting_id: int
    status: str
    message: str
    poll_url: str


class BackgroundAnalysisStatusResponse(BaseModel):
    job_posting_id: int
    status: str
    message: str
    result_ready: bool
    error: str | None = None
