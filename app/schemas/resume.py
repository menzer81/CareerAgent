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
    importance: int = Field(
        5,
        ge=0,
        le=10,
        description="Inherent value of this accomplishment independent of job relevance "
        "(10 = signature accomplishment, 8 = strong, 5 = good, 3 = supporting).",
    )


class ResumePersona(str, Enum):
    """Alternate framings of the same experience base for different target roles."""

    AI_TRANSFORMATION_LEADER = "AI Transformation Leader"
    ENGINEERING_TURNAROUND_SPECIALIST = "Engineering Turnaround Specialist"
    COMPLIANCE_GOVERNANCE_LEADER = "Compliance & Governance Leader"
    TECHNICAL_DELIVERY_LEADER = "Technical Delivery Leader"
    GROWTH_ENGINEERING_LEADER = "Growth Engineering Leader"
    CLOUD_TRANSFORMATION_LEADER = "Cloud Transformation Leader"
    DIRECTOR_TRACK_CANDIDATE = "Director Track Candidate"


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
    recommended_persona: ResumePersona | None = None
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


class GeneratedAccomplishmentBullet(BaseModel):
    """LLM-rewritten copy for a single accomplishment (Recommendation: OpenAI Resume Generator)."""

    id: str
    generated_text: str


class GeneratedWorkHistoryBullets(BaseModel):
    """LLM-rewritten experience bullets for a single work history entry."""

    company: str
    bullets: list[str] = Field(default_factory=list)


class GeneratedResumeContent(BaseModel):
    """Tailored resume prose produced by an LLM content generator.

    All content here must be traceable to the candidate profile / accomplishment
    bank the LLM was given — it is expected to *rewrite* wording and framing,
    not invent new facts, metrics, or experience.
    """

    job_posting_id: int
    executive_summary: str = ""
    experience_bullets: list[GeneratedWorkHistoryBullets] = Field(default_factory=list)
    accomplishment_bullets: list[GeneratedAccomplishmentBullet] = Field(default_factory=list)
    generated_by: str = "static"
    """Provenance marker: "llm" when produced by an LLM provider, "static" when
    falling back to the unmodified profile/accomplishment text."""


class ResumeValidationIssue(BaseModel):
    """A single validation finding produced by the Resume Validation Layer."""

    check: str
    severity: str = Field("error", description="'error' or 'warning'")
    message: str


class ResumeValidationResult(BaseModel):
    """Recommendation: Validation Layer — quality/safety gate before rendering."""

    passed: bool
    issues: list[ResumeValidationIssue] = Field(default_factory=list)


class ExportPreferences(BaseModel):
    """Rendering preferences for downstream resume exporters."""

    reactive_resume_template: str = "onyx"
    reactive_resume_page_format: str = "letter"


class ExportCapabilities(BaseModel):
    """Resolved export/runtime capabilities for the current environment."""

    pdf_renderer: str = "local"
    docx_renderer: str = "local"
    reactive_resume_configured: bool = False


class ResumeBuildRequest(BaseModel):
    """Request body for building a tailored resume plan."""

    boosted_accomplishment_ids: list[str] = Field(default_factory=list)
    boost_multiplier: float = 1.5
    top_n: int = 4
    persona_override: ResumePersona | None = None
    export_preferences: ExportPreferences = Field(default_factory=ExportPreferences)


class ResumePlan(BaseModel):
    """The full, combined output of the resume pipeline for a job posting."""

    job_posting_id: int
    selection: AchievementSelectionResult
    strategy: ResumeStrategy
    keyword_coverage: KeywordCoverageReport
    data_model: ResumeDataModel
    quality_score: ResumeQualityScore
    export_preferences: ExportPreferences = Field(default_factory=ExportPreferences)
    export_capabilities: ExportCapabilities = Field(default_factory=ExportCapabilities)
    generated_content: GeneratedResumeContent | None = None
    validation: ResumeValidationResult | None = None
    markdown: str = ""
