"""Unit tests for the Resume Validation Layer (Quality Control)."""

import pytest

from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import (
    AccomplishmentEntry,
    GeneratedAccomplishmentBullet,
    GeneratedResumeContent,
    ResumeDocument,
    ResumeSection,
)
from app.services.resume_validation_service import ResumeValidationService


def _profile(**overrides) -> CandidateProfileData:
    defaults = dict(
        full_name="Jane Smith",
        current_title="Engineering Director",
        email="jane@example.com",
        summary="Experienced leader.",
    )
    defaults.update(overrides)
    return CandidateProfileData(**defaults)


def _document(**overrides) -> ResumeDocument:
    defaults = dict(
        full_name="Jane Smith",
        current_title="Engineering Director",
        executive_summary="Experienced leader.",
        sections=[
            ResumeSection(heading="Core Skills", bullets=["Python", "AWS"]),
            ResumeSection(heading="Professional Experience", bullets=[]),
            ResumeSection(
                heading="Engineering Director, TechCorp (2019 – Present)",
                bullets=["Led migration.", "Scaled team."],
                level=3,
            ),
        ],
    )
    defaults.update(overrides)
    return ResumeDocument(**defaults)


class TestResumeValidationService:
    def test_valid_document_passes(self):
        service = ResumeValidationService()
        result = service.validate(_profile(), _document())
        assert result.passed
        assert not any(issue.severity == "error" for issue in result.issues)

    def test_missing_contact_info_fails(self):
        service = ResumeValidationService()
        profile = _profile(email=None, phone=None, linkedin_url=None)
        result = service.validate(profile, _document())
        assert not result.passed
        assert any(issue.check == "contact_information" for issue in result.issues)

    def test_missing_full_name_fails(self):
        service = ResumeValidationService()
        profile = _profile(full_name="")
        result = service.validate(profile, _document())
        assert not result.passed
        assert any(issue.check == "contact_information" for issue in result.issues)

    def test_duplicate_accomplishments_flagged(self):
        service = ResumeValidationService()
        document = _document(
            sections=[
                ResumeSection(
                    heading="Featured Accomplishments",
                    bullets=["Led migration.", "Led migration."],
                )
            ]
        )
        result = service.validate(_profile(), document)
        assert not result.passed
        assert any(issue.check == "duplicate_accomplishments" for issue in result.issues)

    def test_corrupted_characters_flagged(self):
        service = ResumeValidationService()
        document = _document(executive_summary="Bad text \x00 here")
        result = service.validate(_profile(), document)
        assert not result.passed
        assert any(issue.check == "corrupted_characters" for issue in result.issues)

    def test_no_professional_experience_section_fails(self):
        service = ResumeValidationService()
        document = _document(sections=[ResumeSection(heading="Core Skills", bullets=["Python"])])
        result = service.validate(_profile(), document)
        assert not result.passed
        assert any(issue.check == "required_sections" for issue in result.issues)

    def test_empty_summary_is_warning_not_error(self):
        service = ResumeValidationService()
        document = _document(executive_summary="")
        result = service.validate(_profile(), document)
        summary_issues = [i for i in result.issues if i.check == "required_sections"]
        assert any(i.severity == "warning" for i in summary_issues)

    def test_metrics_dropped_from_llm_generated_bullet_flagged(self):
        service = ResumeValidationService()
        accomplishment = AccomplishmentEntry(
            id="acc-1",
            title="Led migration",
            company="TechCorp",
            category="Leadership",
            impact="Saved $2M/year",
            metrics={"savings_usd": 2_000_000},
        )
        generated_content = GeneratedResumeContent(
            job_posting_id=1,
            executive_summary="Summary",
            accomplishment_bullets=[
                GeneratedAccomplishmentBullet(id="acc-1", generated_text="Delivered major cost savings.")
            ],
            generated_by="llm",
        )
        result = service.validate(
            _profile(),
            _document(),
            generated_content=generated_content,
            selected_accomplishments=[accomplishment],
        )
        assert not result.passed
        assert any(issue.check == "metrics_preserved" for issue in result.issues)

    def test_metrics_preserved_passes(self):
        service = ResumeValidationService()
        accomplishment = AccomplishmentEntry(
            id="acc-1",
            title="Led migration",
            company="TechCorp",
            category="Leadership",
            impact="Saved $2M/year",
            metrics={"savings_usd": 2_000_000},
        )
        generated_content = GeneratedResumeContent(
            job_posting_id=1,
            executive_summary="Summary",
            accomplishment_bullets=[
                GeneratedAccomplishmentBullet(id="acc-1", generated_text="Saved $2M/year in cloud costs.")
            ],
            generated_by="llm",
        )
        result = service.validate(
            _profile(),
            _document(),
            generated_content=generated_content,
            selected_accomplishments=[accomplishment],
        )
        assert result.passed

    def test_fabricated_metric_is_flagged_as_error(self):
        service = ResumeValidationService()
        accomplishment = AccomplishmentEntry(
            id="acc-1",
            title="AWS Enablement",
            company="Entrata",
            category="Leadership",
            impact="Trained 500 engineers with 98% completion rate.",
            metrics={"engineers_trained": 500, "completion_rate_percent": 98},
        )
        generated_content = GeneratedResumeContent(
            job_posting_id=1,
            executive_summary="Summary",
            accomplishment_bullets=[
                GeneratedAccomplishmentBullet(
                    id="acc-1",
                    # 150000 is fabricated — not in source data
                    generated_text="Scaled SaaS platform to 150000+ units by training 500 engineers, achieving 98% completion.",
                )
            ],
            generated_by="llm",
        )
        result = service.validate(
            _profile(),
            _document(),
            generated_content=generated_content,
            selected_accomplishments=[accomplishment],
        )
        assert not result.passed
        fabricated_issues = [i for i in result.issues if i.check == "fabricated_metrics"]
        assert fabricated_issues
        assert "150000" in fabricated_issues[0].message

    def test_no_fabrication_when_numbers_match_source(self):
        service = ResumeValidationService()
        accomplishment = AccomplishmentEntry(
            id="acc-1",
            title="AWS Enablement",
            company="Entrata",
            category="Leadership",
            impact="Trained 500 engineers with 98% completion rate.",
            metrics={"engineers_trained": 500, "completion_rate_percent": 98},
        )
        generated_content = GeneratedResumeContent(
            job_posting_id=1,
            executive_summary="Summary",
            accomplishment_bullets=[
                GeneratedAccomplishmentBullet(
                    id="acc-1",
                    generated_text="Led AWS training program for 500 engineers across US and India, achieving 98% completion.",
                )
            ],
            generated_by="llm",
        )
        result = service.validate(
            _profile(),
            _document(),
            generated_content=generated_content,
            selected_accomplishments=[accomplishment],
        )
        assert not any(i.check == "fabricated_metrics" for i in result.issues)

    def test_static_generated_content_skips_metrics_check(self):
        service = ResumeValidationService()
        accomplishment = AccomplishmentEntry(
            id="acc-1",
            title="Led migration",
            company="TechCorp",
            category="Leadership",
            impact="Saved money",
            metrics={"savings_usd": 2_000_000},
        )
        generated_content = GeneratedResumeContent(
            job_posting_id=1,
            executive_summary="Summary",
            accomplishment_bullets=[
                GeneratedAccomplishmentBullet(id="acc-1", generated_text="Led migration: Saved money")
            ],
            generated_by="static",
        )
        result = service.validate(
            _profile(),
            _document(),
            generated_content=generated_content,
            selected_accomplishments=[accomplishment],
        )
        assert not any(issue.check == "metrics_preserved" for issue in result.issues)
