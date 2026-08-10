"""Schemas for interview prep and cover letter generation."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.resume import ResumePersona
from app.schemas.scoring import Recommendation


class InterviewQuestion(BaseModel):
    category: str
    question: str
    rationale: str
    talking_points: list[str] = Field(default_factory=list)


class InterviewPrepPlan(BaseModel):
    job_posting_id: int
    recommendation: Recommendation
    overall_score: float = Field(..., ge=0, le=100)
    opening_pitch: str
    priority_focus_areas: list[str] = Field(default_factory=list)
    likely_questions: list[InterviewQuestion] = Field(default_factory=list)
    risk_mitigation_points: list[str] = Field(default_factory=list)
    questions_to_ask_interviewer: list[str] = Field(default_factory=list)


class InterviewPrepResponse(BaseModel):
    id: int
    job_posting_id: int
    prep_data: InterviewPrepPlan
    generated_at: datetime

    model_config = {"from_attributes": True}


class CoverLetterTone(StrEnum):
    PROFESSIONAL = "professional"
    CONFIDENT = "confident"
    CONVERSATIONAL = "conversational"


class CoverLetterStyle(StrEnum):
    CONCISE = "concise"
    EXECUTIVE = "executive"
    STORYTELLING = "storytelling"


class CoverLetterOptions(BaseModel):
    tone: CoverLetterTone = CoverLetterTone.PROFESSIONAL
    style: CoverLetterStyle = CoverLetterStyle.CONCISE


class CoverLetterDraft(BaseModel):
    job_posting_id: int
    persona: ResumePersona
    tone: CoverLetterTone = CoverLetterTone.PROFESSIONAL
    style: CoverLetterStyle = CoverLetterStyle.CONCISE
    subject_line: str
    greeting: str
    opening_paragraph: str
    body_paragraphs: list[str] = Field(default_factory=list)
    closing_paragraph: str
    signature: str
    markdown: str


class CoverLetterResponse(BaseModel):
    id: int
    job_posting_id: int
    letter_data: CoverLetterDraft
    generated_at: datetime

    model_config = {"from_attributes": True}
