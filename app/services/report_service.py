"""Report generation service — produces markdown reports."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.repositories.job_analysis_repository import JobAnalysisRepository, ScoringResultRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.analysis import JobRequirements
from app.schemas.scoring import FullAnalysisResult, Recommendation

logger = logging.getLogger(__name__)

_RECOMMENDATION_EMOJI = {
    Recommendation.STRONG_APPLY: "🟢",
    Recommendation.APPLY: "🔵",
    Recommendation.STRETCH_OPPORTUNITY: "🟡",
    Recommendation.LOW_PRIORITY: "🔴",
}


def _score_bar(score: float, width: int = 20) -> str:
    """Return a simple ASCII progress bar."""
    filled = round(score / 100 * width)
    return f"[{'█' * filled}{'░' * (width - filled)}] {score:.0f}/100"


def generate_markdown_report(result: FullAnalysisResult, title: str, company: str) -> str:
    scoring = result.scoring
    gap = result.gap_analysis
    rec = scoring.recommendation
    emoji = _RECOMMENDATION_EMOJI.get(rec, "")
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []

    # Header
    lines += [
        f"# CareerAgent Analysis Report",
        f"",
        f"**Role:** {title}  ",
        f"**Company:** {company}  ",
        f"**Generated:** {now}  ",
        f"**Job Posting ID:** {result.job_posting_id}",
        f"",
        "---",
        "",
    ]

    # Recommendation banner
    lines += [
        f"## {emoji} Recommendation: {rec.value}",
        f"",
        f"> {scoring.recommendation_reasoning}",
        f"",
        "---",
        "",
    ]

    # Scores table
    lines += [
        "## Match Scores",
        "",
        "| Dimension | Score | Bar |",
        "|-----------|------:|-----|",
        f"| **Overall Match** | **{scoring.overall_score:.0f}** | `{_score_bar(scoring.overall_score)}` |",
        f"| Leadership Match | {scoring.leadership_match.score:.0f} | `{_score_bar(scoring.leadership_match.score)}` |",
        f"| Technical Match | {scoring.technical_match.score:.0f} | `{_score_bar(scoring.technical_match.score)}` |",
        f"| Cloud Match | {scoring.cloud_match.score:.0f} | `{_score_bar(scoring.cloud_match.score)}` |",
        f"| AI Match | {scoring.ai_match.score:.0f} | `{_score_bar(scoring.ai_match.score)}` |",
        f"| Management Scope Match | {scoring.management_scope_match.score:.0f} | `{_score_bar(scoring.management_scope_match.score)}` |",
        f"| Industry Match | {scoring.industry_match.score:.0f} | `{_score_bar(scoring.industry_match.score)}` |",
        "",
    ]

    # Score explanations
    lines += ["## Score Explanations", ""]
    for label, dim in [
        ("Leadership Match", scoring.leadership_match),
        ("Technical Match", scoring.technical_match),
        ("Cloud Match", scoring.cloud_match),
        ("AI Match", scoring.ai_match),
        ("Management Scope Match", scoring.management_scope_match),
        ("Industry Match", scoring.industry_match),
    ]:
        lines.append(f"### {label}")
        lines.append(f"**Score:** {dim.score:.0f}/100")
        lines.append(f"")
        lines.append(dim.explanation)
        if dim.matched:
            lines.append("")
            lines.append("**✅ Matched:**")
            lines.extend(f"- {m}" for m in dim.matched)
        if dim.missing:
            lines.append("")
            lines.append("**❌ Missing:**")
            lines.extend(f"- {m}" for m in dim.missing)
        lines.append("")

    lines += ["---", ""]

    # Strengths
    if gap.strengths:
        lines += ["## 💪 Strengths", ""]
        lines.extend(f"- {s}" for s in gap.strengths)
        lines += [""]

    # Risks
    if gap.risks:
        lines += ["## ⚠️ Risks", ""]
        lines.extend(f"- {r}" for r in gap.risks)
        lines += [""]

    # Missing qualifications
    has_gaps = any([
        gap.missing_experiences,
        gap.missing_keywords,
        gap.missing_certifications,
        gap.missing_leadership_signals,
    ])
    if has_gaps:
        lines += ["## 🔍 Missing Qualifications", ""]
        if gap.missing_experiences:
            lines.append("**Experience Gaps:**")
            lines.extend(f"- {e}" for e in gap.missing_experiences)
            lines.append("")
        if gap.missing_keywords:
            lines.append("**Missing Keywords:**")
            lines.extend(f"- `{k}`" for k in gap.missing_keywords)
            lines.append("")
        if gap.missing_certifications:
            lines.append("**Missing Certifications:**")
            lines.extend(f"- {c}" for c in gap.missing_certifications)
            lines.append("")
        if gap.missing_leadership_signals:
            lines.append("**Leadership Signal Gaps:**")
            lines.extend(f"- {l}" for l in gap.missing_leadership_signals)
            lines.append("")

    # Resume focus areas
    if gap.resume_focus_areas:
        lines += ["## 📝 Recommended Resume Focus Areas", ""]
        lines.extend(f"{i+1}. {area}" for i, area in enumerate(gap.resume_focus_areas))
        lines += [""]

    lines += [
        "---",
        "",
        "*Generated by CareerAgent — your career intelligence assistant*",
    ]

    return "\n".join(lines)


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.job_repo = JobPostingRepository(session)
        self.analysis_repo = JobAnalysisRepository(session)
        self.scoring_repo = ScoringResultRepository(session)
        self.settings = get_settings()

    async def get_report(self, job_posting_id: int) -> str:
        """Generate a markdown report for a scored job posting."""
        posting = await self.job_repo.get(job_posting_id)
        if posting is None:
            raise NotFoundError("JobPosting", job_posting_id)

        scoring_record = await self.scoring_repo.get_by_job_id(job_posting_id)
        if scoring_record is None:
            raise AnalysisNotFoundError(job_posting_id)

        result = FullAnalysisResult.model_validate(scoring_record.scoring_data)

        title = posting.title or "Unknown Role"
        company = posting.company or "Unknown Company"

        return generate_markdown_report(result, title, company)

    async def save_report(self, job_posting_id: int) -> Path:
        """Generate report and save to the configured reports directory."""
        content = await self.get_report(job_posting_id)
        reports_dir = self.settings.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / f"job_{job_posting_id}_report.md"
        output_path.write_text(content, encoding="utf-8")
        logger.info("Report saved to %s", output_path)
        return output_path
