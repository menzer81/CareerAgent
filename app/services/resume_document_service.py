"""Resume Document Service (Recommendation 7).

Builds a renderer-agnostic ``ResumeDocument`` from the ``ResumeDataModel`` and
candidate profile, then renders it to markdown. Future ``DocxRenderer`` /
``PdfRenderer`` implementations can consume the same ``ResumeDocument`` without
touching the business logic that produced it.

All content is drawn directly from ``CandidateProfileData`` / accomplishment
entries — nothing is fabricated. If a section has no supporting evidence, it
is simply omitted.
"""

from __future__ import annotations

from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import (
    AccomplishmentEntry,
    ResumeDataModel,
    ResumeDocument,
    ResumeSection,
    ResumeStrategy,
)

_FULL_BULLET_LIMIT = 5
_SHORTENED_BULLET_LIMIT = 2


class ResumeDocumentService:
    """Assembles a ``ResumeDocument`` from upstream resume pipeline outputs."""

    def build(
        self,
        profile: CandidateProfileData,
        data_model: ResumeDataModel,
        strategy: ResumeStrategy,
        accomplishments: list[AccomplishmentEntry] | None = None,
    ) -> ResumeDocument:
        sections: list[ResumeSection] = []

        if data_model.skills_to_highlight:
            sections.append(
                ResumeSection(heading="Core Skills", bullets=list(data_model.skills_to_highlight))
            )

        selected_companies = set(data_model.selected_work_history)
        shortened_companies = set(data_model.roles_to_shorten)
        work_entries = [e for e in profile.work_history if e.company in selected_companies]
        if work_entries:
            sections.append(ResumeSection(heading="Professional Experience", bullets=[]))
        for entry in work_entries:
            if entry.company not in selected_companies:
                continue
            limit = (
                _SHORTENED_BULLET_LIMIT
                if entry.company in shortened_companies
                else _FULL_BULLET_LIMIT
            )
            date_range = f"{entry.start_date} – {entry.end_date or 'Present'}"
            heading = f"{entry.title}, {entry.company} ({date_range})"
            bullets = list(entry.key_accomplishments[:limit])
            sections.append(ResumeSection(heading=heading, bullets=bullets, level=3))

        if data_model.selected_accomplishments and accomplishments:
            featured = [
                acc for acc in accomplishments if acc.id in data_model.selected_accomplishments
            ]
            if featured:
                sections.append(
                    ResumeSection(
                        heading="Featured Accomplishments",
                        bullets=[f"{acc.title}: {acc.impact}" for acc in featured],
                    )
                )

        if profile.certifications:
            sections.append(
                ResumeSection(
                    heading="Certifications",
                    bullets=[
                        f"{c.name} ({c.issuer}, {c.year})" if c.year else f"{c.name} ({c.issuer})"
                        for c in profile.certifications
                        if c.is_active
                    ],
                )
            )

        if profile.education:
            sections.append(
                ResumeSection(
                    heading="Education",
                    bullets=[
                        f"{e.degree}, {e.field_of_study} — {e.institution}"
                        if e.field_of_study
                        else f"{e.degree} — {e.institution}"
                        for e in profile.education
                    ],
                )
            )

        return ResumeDocument(
            full_name=profile.full_name,
            current_title=profile.current_title,
            location=profile.location,
            executive_summary=data_model.executive_summary,
            sections=sections,
        )


class MarkdownResumeRenderer:
    """Renders a ``ResumeDocument`` to markdown text."""

    def render(self, document: ResumeDocument) -> str:
        lines: list[str] = [f"# {document.full_name}"]
        subtitle = document.current_title
        if document.location:
            subtitle += f" — {document.location}"
        lines += [subtitle, ""]

        if document.executive_summary:
            lines += ["## Professional Summary", "", document.executive_summary, ""]

        for section in document.sections:
            marker = "#" * max(2, min(6, section.level))
            lines.append(f"{marker} {section.heading}")
            lines.append("")
            lines.extend(f"- {bullet}" for bullet in section.bullets)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"
