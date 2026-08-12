from app.schemas.candidate_profile import CandidateProfileData, WorkHistoryEntry
from app.schemas.resume import (
    AchievementSelectionResult,
    KeywordCoverageReport,
    ResumeDataModel,
    ResumePersona,
    ResumePlan,
    ResumeQualityScore,
    ResumeStrategy,
)
from app.services.reactive_resume_service import ReactiveResumeService


def _sample_profile() -> CandidateProfileData:
    return CandidateProfileData(
        full_name="Jane Smith",
        current_title="Engineering Director",
        summary="Experienced engineering leader.",
        work_history=[
            WorkHistoryEntry(
                company="TechCorp",
                title="Engineering Director",
                start_date="2019-01",
                end_date=None,
                is_current=True,
                description="Lead platform engineering org.",
                key_accomplishments=[
                    "Reduced deploy time by 70%",
                    "Built SRE practice from scratch",
                ],
            )
        ],
        leadership_experience={"leadership_highlights": ["Built high-performing distributed teams"]},
        management_experience={"management_highlights": ["Reduced attrition from 25% to 8%"]},
        ai_experience={"ai_highlights": ["Built internal LLM-powered code review tool"]},
        career_highlights=["Migrated core platform to AWS"],
        technologies=["Python", "AWS"],
        certifications=[],
        education=[],
    )


def _sample_plan() -> ResumePlan:
    return ResumePlan(
        job_posting_id=42,
        selection=AchievementSelectionResult(
            job_posting_id=42,
            selected_accomplishment_ids=["ACC-1"],
        ),
        strategy=ResumeStrategy(
            job_posting_id=42,
            persona=ResumePersona.TECHNICAL_DELIVERY_LEADER,
        ),
        keyword_coverage=KeywordCoverageReport(
            required_keywords=1,
            covered_keywords=1,
            coverage_percent=100.0,
            matched_keywords=["Python"],
            missing_keywords=[],
        ),
        data_model=ResumeDataModel(
            job_posting_id=42,
            executive_summary="Summary",
            selected_work_history=["TechCorp"],
            selected_accomplishments=["ACC-1"],
            skills_to_highlight=["Python"],
        ),
        quality_score=ResumeQualityScore(
            keyword_coverage=90,
            leadership_signal_strength=90,
            ai_relevance=80,
            manager_of_managers_alignment=85,
            overall_resume_quality=87,
        ),
    )


class _FakeAccomplishment:
    def __init__(self, identifier: str, title: str, impact: str) -> None:
        self.id = identifier
        self.title = title
        self.impact = impact


def test_bullet_list_html_uses_inline_bullet_rows():
    html = ReactiveResumeService._bullet_list_html(["  One <Two>  ", "", "Three"])

    assert html == "<div><p>• One &lt;Two&gt;</p><p>• Three</p></div>"


def test_build_resume_data_uses_shared_bullet_rows_for_experience_and_custom_sections(monkeypatch):
    monkeypatch.setattr(
        "app.services.reactive_resume_service.load_accomplishments",
        lambda: [_FakeAccomplishment("ACC-1", "Delivered migration", "$2M savings")],
    )
    service = ReactiveResumeService()

    payload = service._build_resume_data(_sample_profile(), _sample_plan())

    experience_description = payload["sections"]["experience"]["items"][0]["description"]
    featured_content = payload["customSections"][0]["items"][0]["content"]
    leadership_content = next(
        section["items"][0]["content"]
        for section in payload["customSections"]
        if section["title"] == "Leadership Highlights"
    )

    assert experience_description.startswith("<div><p>• Reduced deploy time by 70%</p>")
    assert featured_content == "<div><p>• Delivered migration: $2M savings</p></div>"
    assert leadership_content == "<div><p>• Built high-performing distributed teams</p></div>"