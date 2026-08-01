"""Pydantic schemas for candidate profile."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field


class WorkHistoryEntry(BaseModel):
    company: str
    title: str
    start_date: str = Field(..., description="YYYY-MM or YYYY format")
    end_date: str | None = Field(None, description="YYYY-MM or YYYY, or null if current")
    is_current: bool = False
    description: str = ""
    team_size: int | None = None
    direct_reports: int | None = None
    budget_usd: int | None = Field(None, description="Approximate budget managed in USD")
    key_accomplishments: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)


class LeadershipExperience(BaseModel):
    largest_team_managed: int | None = None
    largest_org_managed: int | None = None
    manager_of_managers: bool = False
    director_level_or_above: bool = False
    executive_level: bool = False
    vp_or_above: bool = False
    managed_multiple_teams: bool = False
    cross_functional_leadership: bool = False
    board_presentations: bool = False
    p_and_l_responsibility: bool = False
    hiring_scale: str | None = Field(None, description="e.g. 'Built team from 0 to 40'")
    leadership_highlights: list[str] = Field(default_factory=list)


class AIExperience(BaseModel):
    worked_with_llms: bool = False
    built_ai_products: bool = False
    ml_engineering_background: bool = False
    ai_product_management: bool = False
    rag_systems: bool = False
    fine_tuning_experience: bool = False
    ai_agents: bool = False
    tools_and_frameworks: list[str] = Field(
        default_factory=list,
        description="e.g. OpenAI API, LangChain, HuggingFace, PyTorch",
    )
    ai_highlights: list[str] = Field(default_factory=list)


class ManagementExperience(BaseModel):
    total_years_managing: float | None = None
    total_years_ic: float | None = None
    remote_team_management: bool = False
    distributed_team_management: bool = False
    offshore_team_management: bool = False
    agile_practitioner: bool = True
    scaled_agile: bool = False
    org_design_experience: bool = False
    performance_management: bool = True
    executive_stakeholder_management: bool = False
    management_highlights: list[str] = Field(default_factory=list)


class CertificationEntry(BaseModel):
    name: str
    issuer: str
    year: int | None = None
    expiry_year: int | None = None
    is_active: bool = True


class EducationEntry(BaseModel):
    institution: str
    degree: str
    field_of_study: str | None = None
    graduation_year: int | None = None
    honors: str | None = None


class CandidateProfileData(BaseModel):
    """The full structured candidate profile."""

    full_name: str
    current_title: str
    location: str | None = None
    years_total_experience: float | None = None
    years_management_experience: float | None = None
    summary: str = ""

    work_history: list[WorkHistoryEntry] = Field(default_factory=list)
    leadership_experience: LeadershipExperience = Field(
        default_factory=LeadershipExperience
    )
    ai_experience: AIExperience = Field(default_factory=AIExperience)
    management_experience: ManagementExperience = Field(
        default_factory=ManagementExperience
    )

    technologies: list[str] = Field(
        default_factory=list,
        description="All technologies, languages, frameworks, and tools",
    )
    cloud_platforms: list[str] = Field(
        default_factory=list,
        description="e.g. AWS, GCP, Azure, and specific services",
    )
    certifications: list[CertificationEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    accomplishments: list[str] = Field(
        default_factory=list,
        description="Notable career accomplishments and quantified wins",
    )
    industries: list[str] = Field(
        default_factory=list,
        description="Industry domains the candidate has worked in",
    )
    career_goals: list[str] = Field(
        default_factory=list,
        description="What the candidate is looking for in their next role",
    )


class CandidateProfileResponse(BaseModel):
    id: int
    full_name: str
    profile_data: CandidateProfileData

    model_config = {"from_attributes": True}


class CandidateProfileUpdate(BaseModel):
    profile_data: CandidateProfileData
