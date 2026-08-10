"""Unit tests for DOCX/PDF resume export service."""

from app.schemas.resume import (
    AchievementSelectionResult,
    KeywordCoverageReport,
    ResumeDataModel,
    ResumePersona,
    ResumePlan,
    ResumeQualityScore,
    ResumeStrategy,
)
from app.services.resume_export_service import ResumeExportService


def _sample_plan() -> ResumePlan:
    return ResumePlan(
        job_posting_id=42,
        selection=AchievementSelectionResult(job_posting_id=42),
        strategy=ResumeStrategy(job_posting_id=42, persona=ResumePersona.TECHNICAL_DELIVERY_LEADER),
        keyword_coverage=KeywordCoverageReport(
            required_keywords=1,
            covered_keywords=1,
            coverage_percent=100.0,
            matched_keywords=["Python"],
            missing_keywords=[],
        ),
        data_model=ResumeDataModel(job_posting_id=42, executive_summary="Summary"),
        quality_score=ResumeQualityScore(
            keyword_coverage=90,
            leadership_signal_strength=90,
            ai_relevance=80,
            manager_of_managers_alignment=85,
            overall_resume_quality=87,
        ),
        markdown="# Jane Smith\n\n## Summary\n\n- Led platform modernization\n- Scaled team outcomes\n",
    )


class TestResumeExportService:
    def test_saves_docx(self):
        service = ResumeExportService()
        plan = _sample_plan()
        path = service.save_docx(plan.job_posting_id, plan)
        assert path.exists()
        assert path.suffix == ".docx"
        assert path.stat().st_size > 0

    def test_saves_pdf(self):
        service = ResumeExportService()
        plan = _sample_plan()
        path = service.save_pdf(plan.job_posting_id, plan)
        assert path.exists()
        assert path.suffix == ".pdf"
        assert path.stat().st_size > 0
