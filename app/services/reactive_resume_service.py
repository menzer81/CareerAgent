"""Reactive Resume API integration for higher-fidelity PDF rendering."""

from __future__ import annotations

from html import escape
from typing import Any
from uuid import uuid4

import httpx

from app.config import get_settings
from app.schemas.candidate_profile import CandidateProfileData, WorkHistoryEntry
from app.schemas.resume import ResumePlan
from app.services.accomplishment_loader import load_accomplishments

_FULL_BULLET_LIMIT = 5
_SHORTENED_BULLET_LIMIT = 2
_MAX_HIGHLIGHTS_PER_SECTION = 4


class ReactiveResumeService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.reactive_resume_api_key)

    async def render_resume_pdf(self, profile: CandidateProfileData, plan: ResumePlan) -> bytes:
        if not self.is_configured():
            raise RuntimeError(
                "Reactive Resume PDF export is not configured. Set REACTIVE_RESUME_API_KEY to enable hosted PDF rendering."
            )

        payload = {"data": self._build_resume_data(profile, plan)}
        headers = {"x-api-key": self.settings.reactive_resume_api_key}
        base_url = str(self.settings.reactive_resume_base_url).rstrip("/")

        async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
            import_response = await client.post("/resumes/import", headers=headers, json=payload)
            resume_id = self._parse_resume_id(import_response)

            pdf_response = await client.get(
                f"/resumes/{resume_id}/pdf",
                headers=headers,
                params={"target": "resume"},
            )
            if pdf_response.status_code != 200:
                raise RuntimeError(
                    f"Reactive Resume PDF download failed: {self._describe_error(pdf_response)}"
                )
            return pdf_response.content

    def _parse_resume_id(self, response: httpx.Response) -> str:
        if response.status_code != 200:
            raise RuntimeError(f"Reactive Resume import failed: {self._describe_error(response)}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Reactive Resume import returned invalid JSON.") from exc

        if isinstance(payload, str) and payload:
            return payload
        raise RuntimeError("Reactive Resume import did not return a resume ID.")

    @staticmethod
    def _describe_error(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            text = response.text.strip()
            return text or f"HTTP {response.status_code}"

        if isinstance(data, dict):
            message = data.get("message") or data.get("detail") or data.get("code")
            if message:
                return str(message)
        return f"HTTP {response.status_code}"

    def _build_resume_data(self, profile: CandidateProfileData, plan: ResumePlan) -> dict[str, Any]:
        selected_companies = set(plan.data_model.selected_work_history)
        shortened_companies = set(plan.data_model.roles_to_shorten)
        work_entries = [entry for entry in profile.work_history if entry.company in selected_companies]

        experience_items = [
            self._experience_item(entry, shortened=entry.company in shortened_companies)
            for entry in work_entries
        ]
        education_items = [self._education_item(entry) for entry in profile.education]
        certification_items = [
            self._certification_item(entry) for entry in profile.certifications if entry.is_active
        ]
        skill_items = self._skill_items(profile, plan)

        featured_accomplishments = self._featured_accomplishments_html(plan)

        custom_sections = []
        custom_main_sections: list[str] = []

        self._append_summary_section(
            custom_sections,
            custom_main_sections,
            "Featured Accomplishments",
            featured_accomplishments,
        )

        for title, content in self._job_specific_sections(profile, plan).items():
            self._append_summary_section(custom_sections, custom_main_sections, title, content)

        main_sections = ["summary", "experience"]
        main_sections.extend(custom_main_sections)
        if education_items:
            main_sections.append("education")

        sidebar_sections = []
        if skill_items:
            sidebar_sections.append("skills")
        if certification_items:
            sidebar_sections.append("certifications")

        return {
            "$schema": "https://rxresu.me/schema.json",
            "version": "5.0.0",
            "picture": {
                "hidden": True,
                "url": "",
                "size": 96,
                "rotation": 0,
                "aspectRatio": 1,
                "borderRadius": 0,
                "borderColor": "rgba(0, 0, 0, 0)",
                "borderWidth": 0,
                "shadowColor": "rgba(0, 0, 0, 0)",
                "shadowWidth": 0,
            },
            "basics": {
                "name": profile.full_name,
                "headline": profile.current_title,
                "email": profile.email or "",
                "phone": profile.phone or "",
                "location": profile.location or "",
                "website": self._website(profile.website_url),
                "customFields": self._contact_custom_fields(profile),
            },
            "summary": {
                "title": "Professional Summary",
                "columns": 1,
                "hidden": not bool(plan.data_model.executive_summary),
                "content": self._paragraph_html(plan.data_model.executive_summary),
            },
            "sections": {
                "profiles": self._empty_section("Profiles", hidden=True),
                "experience": self._section("Professional Experience", experience_items),
                "education": self._section("Education", education_items, hidden=not education_items),
                "projects": self._empty_section("Projects", hidden=True),
                "skills": self._section("Core Skills", skill_items, hidden=not skill_items),
                "languages": self._empty_section("Languages", hidden=True),
                "interests": self._empty_section("Interests", hidden=True),
                "awards": self._empty_section("Awards", hidden=True),
                "certifications": self._section(
                    "Certifications", certification_items, hidden=not certification_items
                ),
                "publications": self._empty_section("Publications", hidden=True),
                "volunteer": self._empty_section("Volunteer", hidden=True),
                "references": self._empty_section("References", hidden=True),
            },
            "customSections": custom_sections,
            "metadata": {
                "template": plan.export_preferences.reactive_resume_template,
                "layout": {
                    "sidebarWidth": 32,
                    "pages": [
                        {
                            "fullWidth": False,
                            "main": main_sections,
                            "sidebar": sidebar_sections,
                        }
                    ],
                },
                "page": {
                    "gapX": 16,
                    "gapY": 10,
                    "marginX": 18,
                    "marginY": 16,
                    "format": plan.export_preferences.reactive_resume_page_format,
                    "locale": "en-US",
                    "hideIcons": False,
                },
                "design": {
                    "level": {"icon": "", "type": "hidden"},
                    "colors": {
                        "primary": "rgba(30, 95, 116, 1)",
                        "text": "rgba(17, 24, 39, 1)",
                        "background": "rgba(255, 255, 255, 1)",
                    },
                },
                "typography": {
                    "body": {
                        "fontFamily": "IBM Plex Sans",
                        "fontWeights": ["400"],
                        "fontSize": 10,
                        "lineHeight": 1.35,
                    },
                    "heading": {
                        "fontFamily": "IBM Plex Sans",
                        "fontWeights": ["600", "700"],
                        "fontSize": 12,
                        "lineHeight": 1.2,
                    },
                },
                "notes": self._paragraph_html(
                    f"Generated by CareerAgent for job posting {plan.job_posting_id}."
                ),
            },
        }

    def _experience_item(self, entry: WorkHistoryEntry, *, shortened: bool) -> dict[str, Any]:
        limit = _SHORTENED_BULLET_LIMIT if shortened else _FULL_BULLET_LIMIT
        accomplishments = entry.key_accomplishments[:limit]
        description = self._bullet_list_html(accomplishments) or self._paragraph_html(entry.description)
        date_range = f"{entry.start_date} - {entry.end_date or 'Present'}"
        return {
            "id": self._id(),
            "hidden": False,
            "company": entry.company,
            "position": entry.title,
            "location": "",
            "period": date_range,
            "website": {"url": "", "label": "", "inlineLink": False},
            "description": description,
            "roles": [],
        }

    def _education_item(self, entry: Any) -> dict[str, Any]:
        area = entry.field_of_study or ""
        period = str(entry.graduation_year or "")
        description_parts = [part for part in [entry.honors, entry.minor] if part]
        description = self._paragraph_html("; ".join(description_parts))
        return {
            "id": self._id(),
            "hidden": False,
            "school": entry.institution,
            "degree": entry.degree,
            "area": area,
            "grade": "",
            "location": "",
            "period": period,
            "website": {"url": "", "label": "", "inlineLink": False},
            "description": description,
        }

    def _certification_item(self, entry: Any) -> dict[str, Any]:
        return {
            "id": self._id(),
            "hidden": False,
            "title": entry.name,
            "issuer": entry.issuer,
            "date": str(entry.year or ""),
            "website": {"url": "", "label": "", "inlineLink": False},
            "description": self._paragraph_html(entry.issuer),
        }

    def _skill_item(self, skill: str) -> dict[str, Any]:
        return {
            "id": self._id(),
            "hidden": False,
            "icon": "",
            "iconColor": "",
            "name": skill,
            "proficiency": "Relevant",
            "level": 0,
            "keywords": [],
        }

    def _skill_items(self, profile: CandidateProfileData, plan: ResumePlan) -> list[dict[str, Any]]:
        categories = profile.technology_categories or {}
        if categories:
            items: list[dict[str, Any]] = []
            for category, values in categories.items():
                normalized = [value for value in values if value]
                if not normalized:
                    continue
                items.append(
                    {
                        "id": self._id(),
                        "hidden": False,
                        "icon": "",
                        "iconColor": "",
                        "name": category.replace("_", " ").title(),
                        "proficiency": "Category",
                        "level": 0,
                        "keywords": normalized,
                    }
                )
            if items:
                return items

        return [self._skill_item(skill) for skill in plan.data_model.skills_to_highlight]

    def _job_specific_sections(self, profile: CandidateProfileData, plan: ResumePlan) -> dict[str, str]:
        sections: dict[str, str] = {}
        persona = plan.strategy.persona

        if persona == "AI Transformation Leader":
            content = self._bullet_list_html(
                self._top_role_specific_highlights(
                    profile.ai_experience.ai_highlights,
                    ["copilot", "ai", "agent", "llm", "automation", "training"],
                )
            )
            if content:
                sections["AI Transformation Highlights"] = content

        if persona == "Compliance & Governance Leader":
            compliance_pool = (
                profile.ai_experience.ai_highlights
                + profile.leadership_experience.leadership_highlights
                + profile.career_highlights
            )
            content = self._bullet_list_html(
                self._top_role_specific_highlights(
                    compliance_pool,
                    ["soc 2", "soc2", "iso 27001", "compliance", "audit", "governance"],
                )
            )
            if content:
                sections["Compliance Highlights"] = content

        if (
            persona in {"Technical Delivery Leader", "Growth Engineering Leader"}
            or "manager-of-managers" in plan.strategy.emphasize
        ):
            leadership_pool = (
                profile.leadership_experience.leadership_highlights
                + profile.management_experience.management_highlights
            )
            content = self._bullet_list_html(
                self._top_role_specific_highlights(
                    leadership_pool,
                    ["team", "lead", "manage", "organization", "hiring", "enablement"],
                )
            )
            if content:
                sections["Leadership Highlights"] = content

        if "cloud enablement" in plan.strategy.emphasize or plan.strategy.persona == "Growth Engineering Leader":
            cloud_pool = profile.leadership_experience.leadership_highlights + profile.career_highlights
            content = self._bullet_list_html(
                self._top_role_specific_highlights(
                    cloud_pool,
                    ["aws", "azure", "cloud", "container", "migration"],
                )
            )
            if content:
                sections["Cloud Transformation Highlights"] = content

        return sections

    def _top_role_specific_highlights(
        self, highlights: list[str], keywords: list[str]
    ) -> list[str]:
        ranked: list[str] = []
        for highlight in highlights:
            highlight_lower = highlight.lower()
            if any(keyword in highlight_lower for keyword in keywords):
                ranked.append(highlight)
        if not ranked:
            ranked = highlights
        return ranked[:_MAX_HIGHLIGHTS_PER_SECTION]

    def _append_summary_section(
        self,
        custom_sections: list[dict[str, Any]],
        custom_main_sections: list[str],
        title: str,
        content: str,
    ) -> None:
        if not content:
            return
        section_id = self._id()
        custom_sections.append(
            {
                "title": title,
                "columns": 1,
                "hidden": False,
                "id": section_id,
                "type": "summary",
                "items": [{"id": self._id(), "hidden": False, "content": content}],
            }
        )
        custom_main_sections.append(section_id)

    def _contact_custom_fields(self, profile: CandidateProfileData) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        if profile.linkedin_url:
            fields.append(
                {
                    "id": self._id(),
                    "icon": "linkedin-logo",
                    "text": profile.linkedin_url.replace("https://", "").replace("http://", ""),
                    "link": profile.linkedin_url,
                }
            )
        return fields

    @staticmethod
    def _website(url: str | None) -> dict[str, str]:
        if not url:
            return {"url": "", "label": ""}
        return {
            "url": url,
            "label": url.replace("https://", "").replace("http://", ""),
        }

    def _featured_accomplishments_html(self, plan: ResumePlan) -> str:
        selected = plan.selection.selected_accomplishment_ids
        if not selected:
            return ""
        accomplishments = {entry.id: entry for entry in load_accomplishments()}
        items = []
        for accomplishment_id in selected:
            accomplishment = accomplishments.get(accomplishment_id)
            if accomplishment is None:
                label = accomplishment_id
            elif accomplishment.impact:
                label = f"{accomplishment.title}: {accomplishment.impact}"
            else:
                label = accomplishment.title
            items.append(label)
        return self._bullet_list_html(items)

    @staticmethod
    def _section(title: str, items: list[dict[str, Any]], *, hidden: bool = False) -> dict[str, Any]:
        return {"title": title, "columns": 1, "hidden": hidden, "items": items}

    @staticmethod
    def _empty_section(title: str, *, hidden: bool) -> dict[str, Any]:
        return {"title": title, "columns": 1, "hidden": hidden, "items": []}

    @staticmethod
    def _bullet_list_html(items: list[str]) -> str:
        cleaned = [escape(item.strip()) for item in items if item and item.strip()]
        if not cleaned:
            return ""
        bullets = "".join(f"<li>{item}</li>" for item in cleaned)
        return f"<ul>{bullets}</ul>"

    @staticmethod
    def _paragraph_html(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return ""
        return f"<p>{escape(cleaned)}</p>"

    @staticmethod
    def _id() -> str:
        return str(uuid4())