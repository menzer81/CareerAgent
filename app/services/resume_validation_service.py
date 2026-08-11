"""Resume Validation Layer (architecture recommendation: "Quality Control").

Runs a set of lightweight, deterministic checks over the assembled resume
document before it is rendered/exported:

- Contact information exists
- Metrics are preserved (numbers present in source accomplishments aren't
  dropped by content generation)
- No duplicate accomplishments
- No corrupted characters
- Required sections are present
- Formatting requirements are met (non-empty summary/sections)
"""

from __future__ import annotations

import re
from collections import Counter

from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import (
    AccomplishmentEntry,
    GeneratedResumeContent,
    ResumeDocument,
    ResumeValidationIssue,
    ResumeValidationResult,
)

_METRIC_PATTERN = re.compile(r"\d")
_CORRUPTED_CHAR_PATTERN = re.compile(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]")
_REQUIRED_SECTION_HEADINGS = {"professional experience", "core skills"}


class ResumeValidationService:
    """Validates a ``ResumeDocument`` (+ its generated content) before rendering."""

    def validate(
        self,
        profile: CandidateProfileData,
        document: ResumeDocument,
        generated_content: GeneratedResumeContent | None = None,
        selected_accomplishments: list[AccomplishmentEntry] | None = None,
    ) -> ResumeValidationResult:
        issues: list[ResumeValidationIssue] = []

        issues.extend(self._check_contact_info(profile))
        issues.extend(self._check_no_corrupted_characters(document))
        issues.extend(self._check_no_duplicate_accomplishments(document))
        issues.extend(self._check_required_sections(document))
        issues.extend(self._check_formatting(document))
        if generated_content is not None and selected_accomplishments:
            issues.extend(self._check_metrics_preserved(generated_content, selected_accomplishments))

        passed = not any(issue.severity == "error" for issue in issues)
        return ResumeValidationResult(passed=passed, issues=issues)

    def _check_contact_info(self, profile: CandidateProfileData) -> list[ResumeValidationIssue]:
        issues: list[ResumeValidationIssue] = []
        if not profile.full_name.strip():
            issues.append(
                ResumeValidationIssue(
                    check="contact_information", message="Candidate full name is missing."
                )
            )
        if not (profile.email or profile.phone or profile.linkedin_url):
            issues.append(
                ResumeValidationIssue(
                    check="contact_information",
                    message="No contact method found (email, phone, or LinkedIn URL).",
                )
            )
        return issues

    def _check_no_corrupted_characters(self, document: ResumeDocument) -> list[ResumeValidationIssue]:
        issues: list[ResumeValidationIssue] = []
        texts = [document.executive_summary] + [
            bullet for section in document.sections for bullet in section.bullets
        ]
        for text in texts:
            if _CORRUPTED_CHAR_PATTERN.search(text):
                issues.append(
                    ResumeValidationIssue(
                        check="corrupted_characters",
                        message=f"Corrupted/control characters found in resume text: {text!r}",
                    )
                )
        return issues

    def _check_no_duplicate_accomplishments(self, document: ResumeDocument) -> list[ResumeValidationIssue]:
        issues: list[ResumeValidationIssue] = []
        for section in document.sections:
            normalized = [b.strip().lower() for b in section.bullets if b.strip()]
            counts = Counter(normalized)
            duplicates = [text for text, count in counts.items() if count > 1]
            if duplicates:
                issues.append(
                    ResumeValidationIssue(
                        check="duplicate_accomplishments",
                        message=f"Duplicate bullets found in section '{section.heading}': {duplicates}",
                    )
                )
        return issues

    def _check_required_sections(self, document: ResumeDocument) -> list[ResumeValidationIssue]:
        headings = {section.heading.strip().lower() for section in document.sections}
        # Handle "Company (dates)" style headings for Professional Experience sub-entries
        has_experience = any("professional experience" in h for h in headings) or any(
            "(" in section.heading and section.level == 3 for section in document.sections
        )
        issues: list[ResumeValidationIssue] = []
        if not document.executive_summary.strip():
            issues.append(
                ResumeValidationIssue(
                    check="required_sections",
                    severity="warning",
                    message="Executive summary is empty.",
                )
            )
        if not has_experience:
            issues.append(
                ResumeValidationIssue(
                    check="required_sections",
                    message="No professional experience section found in the resume document.",
                )
            )
        return issues

    def _check_formatting(self, document: ResumeDocument) -> list[ResumeValidationIssue]:
        issues: list[ResumeValidationIssue] = []
        if not document.full_name.strip():
            issues.append(
                ResumeValidationIssue(check="formatting", message="Resume document has no full name set.")
            )
        empty_sections = [s.heading for s in document.sections if not s.bullets]
        if empty_sections:
            issues.append(
                ResumeValidationIssue(
                    check="formatting",
                    severity="warning",
                    message=f"Sections with no bullet content: {empty_sections}",
                )
            )
        return issues

    def _check_metrics_preserved(
        self,
        generated_content: GeneratedResumeContent,
        selected_accomplishments: list[AccomplishmentEntry],
    ) -> list[ResumeValidationIssue]:
        """Flag accomplishments whose source metrics were dropped during rewriting."""
        issues: list[ResumeValidationIssue] = []
        if generated_content.generated_by != "llm":
            return issues

        generated_by_id = {b.id: b.generated_text for b in generated_content.accomplishment_bullets}
        for acc in selected_accomplishments:
            if not acc.metrics:
                continue
            generated_text = generated_by_id.get(acc.id)
            if generated_text is None:
                continue
            if not _METRIC_PATTERN.search(generated_text):
                issues.append(
                    ResumeValidationIssue(
                        check="metrics_preserved",
                        message=(
                            f"Accomplishment '{acc.id}' has source metrics but the generated "
                            "bullet contains no numbers; metrics may have been dropped."
                        ),
                    )
                )
        return issues
