"""Pydantic schemas for accomplishment ranking, resume strategy, and resume generation.

These schemas implement the architecture recommendations in
CareerAgent_Architecture_and_Testing_Recommendations.md:

- Recommendation 1: Resume Data Model layer (``ResumeDataModel``)
- Recommendation 2: Boosted accomplishments instead of must-include
- Recommendation 3: Resume exclusion logic (``deemphasize`` / ``omit``)
- Recommendation 4: Keyword coverage reporting (``KeywordCoverageReport``)
- Recommendation 5: Accomplishment explainability (``AccomplishmentRanking``)
- Recommendation 6: Multiple resume personas (``ResumePersona``)
- Recommendation 7: ResumeDocument model (``ResumeDocument`` + renderers)
- Recommendation 8: Resume quality scoring (``ResumeQualityScore``)
"""

from enum import Enum

from pydantic import BaseModel, Field


class AccomplishmentEntry(BaseModel):
    """A single structured accomplishment loaded from data/accomplishments.json."""

    id: str
    title: str
    company: str
    category: str
    tags: list[str] = Field(default_factory=list)
    impact: str = ""
    scope: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


class ResumePersona(str, Enum):
    """Alternate framings of the same experience base for different target roles."""

    AI_TRANSFORMATION_LEADER = "AI Transformation Leader"
    ENGINEERING_TURNAROUND_SPECIALIST = "Engineering Turnaround Specialist"
    COMPLIANCE_GOVERNANCE_LEADER = "Compliance & Governance Leader"
    TECHNICAL_DELIVERY_LEADER = "Technical Delivery Leader"
    GROWTH_ENGINEERING_LEADER = "Growth Engineering Leader"


class AccomplishmentRanking(BaseModel):
    """Ranking + explainability for a single accomplishment (Recommendation 5)."""

    id: str
    ranking_score: float = Field(..., ge=0, le=100)
    ranking_reason: list[str] = Field(default_factory=list)
    boosted: bool = False
    boost_multiplier: float = 1.0


class AchievementSelectionResult(BaseModel):
    """Output of the Achievement Selection Engine."""

    job_posting_id: int
    rankings: list[AccomplishmentRanking] = Field(
        default_factory=list, description="All ranked accomplishments, sorted best-first"
    )
    selected_accomplishment_ids: list[str] = Field(
        default_factory=list, description="Top-N accomplishment IDs chosen for this job"
    )
    boosted_accomplishment_ids: list[str] = Field(
        default_factory=list,
        description="Accomplishment IDs the user asked to boost (Recommendation 2, "
        "replaces the old 'must_include_accomplishment_ids' concept)",
    )
    boost_multiplier: float = Field(
        1.5, description="Weighting factor applied to boosted accomplishments"
    )


class ResumeStrategy(BaseModel):
    """Strategic direction for tailoring a resume to a specific job (Sprint 1)."""

    job_posting_id: int
    persona: ResumePersona
    key_themes: list[str] = Field(default_factory=list)
    emphasize: list[str] = Field(default_factory=list)
    deemphasize: list[str] = Field(
        default_factory=list, description="Recommendation 3: content to soften, not remove"
    )
    omit: list[str] = Field(
        default_factory=list, description="Recommendation 3: low-relevance content to leave out"
    )
    boosted_accomplishment_ids: list[str] = Field(default_factory=list)
    boost_multiplier: float = 1.5


class KeywordCoverageReport(BaseModel):
    """Recommendation 4: keyword coverage diagnostic computed before generation."""

    required_keywords: int
    covered_keywords: int
    coverage_percent: float = Field(..., ge=0, le=100)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)


class ResumeDataModel(BaseModel):
    """Recommendation 1: business-logic resume data, independent of rendering."""

    job_posting_id: int
    executive_summary: str = ""
    selected_work_history: list[str] = Field(
        default_factory=list, description="Company names to include, in display order"
    )
    selected_accomplishments: list[str] = Field(
        default_factory=list, description="Accomplishment IDs to surface"
    )
    skills_to_highlight: list[str] = Field(default_factory=list)
    keywords_to_include: list[str] = Field(default_factory=list)
    roles_to_shorten: list[str] = Field(
        default_factory=list, description="Company names whose entries should be condensed"
    )
    resume_length: str = "2-page"


class ResumeSection(BaseModel):
    """A single named section of a rendered resume."""

    heading: str
    bullets: list[str] = Field(default_factory=list)
    level: int = Field(2, description="Markdown heading level (2 = ##, 3 = ###)")


class ResumeDocument(BaseModel):
    """Recommendation 7: renderer-agnostic resume document model.

    ``ResumeGenerator`` produces this; ``MarkdownResumeRenderer`` (and future
    DocxRenderer/PdfRenderer) turn it into an output format. All content must be
    traceable to the candidate profile or accomplishment/story bank — nothing here
    should be invented.
    """

    full_name: str
    current_title: str
    location: str | None = None
    executive_summary: str = ""
    sections: list[ResumeSection] = Field(default_factory=list)


class ResumeQualityScore(BaseModel):
    """Recommendation 8: self-evaluation of the generated resume before presenting it."""

    keyword_coverage: float = Field(..., ge=0, le=100)
    leadership_signal_strength: float = Field(..., ge=0, le=100)
    ai_relevance: float = Field(..., ge=0, le=100)
    manager_of_managers_alignment: float = Field(..., ge=0, le=100)
    overall_resume_quality: float = Field(..., ge=0, le=100)


class ResumePlan(BaseModel):
    """The full, combined output of the resume pipeline for a job posting."""

    job_posting_id: int
    selection: AchievementSelectionResult
    strategy: ResumeStrategy
    keyword_coverage: KeywordCoverageReport
    data_model: ResumeDataModel
    quality_score: ResumeQualityScore
    markdown: str = ""
