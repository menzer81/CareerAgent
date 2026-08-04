"""Unit tests for the rule-based job requirement extraction fallback."""

from app.services.requirement_extraction_service import heuristic_extract_requirements

SAMPLE_JOB_TEXT = """# Director of Engineering — Platform & Infrastructure

**Company:** Meridian Financial Technologies
**Location:** Remote (US-based)
**Level:** Director

## About Meridian Financial Technologies

Meridian is a Series C fintech company processing $15B+ in annual payment volume.

## About the Role

We're looking for a Director of Engineering to lead our Platform & Infrastructure
organization, a 45-person team. This is a manager-of-managers role.

## Requirements

- 8+ years of software engineering experience, including 5+ years in engineering management
- Demonstrated experience as a manager of managers
- Strong technical background in cloud infrastructure (AWS preferred), Kubernetes
- Experience managing teams of 30+ engineers across multiple functions
- Experience with budget management and P&L responsibility

## Preferred Qualifications

- Director-level or above prior experience
- Fintech, payments, or regulated industry experience
- AI/LLM tooling experience
- Experience with Kubernetes at scale (EKS, GKE, or similar)
"""


class TestHeuristicExtractRequirements:
    def test_extracts_cloud_requirements(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert "AWS" in result.cloud_requirements
        assert "Kubernetes" in result.cloud_requirements

    def test_extracts_ai_requirements(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert any("AI" in kw or "LLM" in kw for kw in result.ai_requirements)

    def test_extracts_industry_domain(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert "Fintech" in result.industry_domain

    def test_manager_of_managers_detected(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert result.manager_of_managers_required is True

    def test_director_level_detected(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert result.director_level_or_above is True
        assert result.role_level == "Director"

    def test_p_and_l_detected(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert result.p_and_l_responsibility is True

    def test_team_size_extracted(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert result.min_team_size_managed is not None
        assert result.min_team_size_managed >= 30

    def test_years_experience_extracted(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert result.years_of_experience_min is not None

    def test_remote_detected(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert result.is_remote is True

    def test_important_keywords_populated(self):
        result = heuristic_extract_requirements(SAMPLE_JOB_TEXT)
        assert len(result.important_keywords) > 0

    def test_handles_empty_text(self):
        result = heuristic_extract_requirements("")
        assert result.required_skills == []
        assert result.cloud_requirements == []
        assert result.manager_of_managers_required is False
