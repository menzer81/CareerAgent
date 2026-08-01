"""Pydantic schemas for scoring results and recommendations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Recommendation(str, Enum):
    STRONG_APPLY = "Strong Apply"
    APPLY = "Apply"
    STRETCH_OPPORTUNITY = "Stretch Opportunity"
    LOW_PRIORITY = "Low Priority"


class DimensionScore(BaseModel):
    score: float = Field(..., ge=0, le=100, description="Score from 0 to 100")
    explanation: str = Field(..., description="Why this score was assigned")
    matched: list[str] = Field(default_factory=list, description="What matched")
    missing: list[str] = Field(default_factory=list, description="What was missing")


class ScoringBreakdown(BaseModel):
    leadership_match: DimensionScore
    technical_match: DimensionScore
    cloud_match: DimensionScore
    ai_match: DimensionScore
    management_scope_match: DimensionScore
    industry_match: DimensionScore
    overall_score: float = Field(..., ge=0, le=100)
    recommendation: Recommendation
    recommendation_reasoning: str


class GapAnalysis(BaseModel):
    missing_experiences: list[str] = Field(
        default_factory=list,
        description="Job experience requirements the candidate lacks",
    )
    missing_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords in the job description not present in the candidate profile",
    )
    missing_certifications: list[str] = Field(
        default_factory=list,
        description="Certifications the job requires or prefers that the candidate doesn't have",
    )
    missing_leadership_signals: list[str] = Field(
        default_factory=list,
        description="Leadership signals called out in the JD that the candidate profile doesn't demonstrate",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Areas where the candidate clearly exceeds requirements",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Potential red flags or concerns about this application",
    )
    resume_focus_areas: list[str] = Field(
        default_factory=list,
        description="Suggested areas to emphasize when tailoring the resume for this role",
    )


class FullAnalysisResult(BaseModel):
    job_posting_id: int
    scoring: ScoringBreakdown
    gap_analysis: GapAnalysis


class ScoringResultResponse(BaseModel):
    id: int
    job_posting_id: int
    scoring_data: FullAnalysisResult
    scored_at: datetime

    model_config = {"from_attributes": True}
