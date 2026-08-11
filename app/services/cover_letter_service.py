"""Cover letter generation service (Sprint 4)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AnalysisNotFoundError, NotFoundError
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.career_documents_repository import CoverLetterRepository
from app.repositories.job_analysis_repository import JobAnalysisRepository, ScoringResultRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.repositories.resume_plan_repository import ResumePlanRepository
from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.career_documents import CoverLetterDraft, CoverLetterStyle, CoverLetterTone
from app.schemas.resume import ResumePersona, ResumePlan
from app.schemas.scoring import FullAnalysisResult
from app.services.resume_strategy_service import select_persona


def _persona_line(persona: ResumePersona) -> str:
    if persona == ResumePersona.AI_TRANSFORMATION_LEADER:
        return "I specialize in leading practical AI adoption in engineering organizations."
    if persona == ResumePersona.COMPLIANCE_GOVERNANCE_LEADER:
        return "I bring strong compliance, governance, and execution leadership for regulated environments."
    if persona == ResumePersona.ENGINEERING_TURNAROUND_SPECIALIST:
        return "I have repeatedly rebuilt underperforming teams into high-trust, high-output organizations."
    if persona == ResumePersona.GROWTH_ENGINEERING_LEADER:
        return "I excel at scaling engineering teams and systems during high-growth phases."
    if persona == ResumePersona.CLOUD_TRANSFORMATION_LEADER:
        return "I lead cloud migration and infrastructure modernization initiatives at scale."
    if persona == ResumePersona.DIRECTOR_TRACK_CANDIDATE:
        return "I bring proven manager-of-managers and organizational leadership experience."
    return "I focus on dependable technical delivery and strong people leadership."


def _infer_signature_name(profile: CandidateProfileData) -> str:
    return profile.full_name.strip() or "Candidate"


def _opening_by_tone(
    tone: CoverLetterTone,
    title: str,
    company: str,
    current_title: str,
    years_total_experience: float | None,
) -> str:
    years = years_total_experience or "extensive"
    if tone == CoverLetterTone.CONFIDENT:
        return (
            f"I am highly motivated to apply for the {title} role at {company}. "
            f"As a {current_title} with {years} years of leadership experience, I can deliver measurable "
            "engineering and business outcomes quickly."
        )
    if tone == CoverLetterTone.CONVERSATIONAL:
        return (
            f"I'm excited to apply for the {title} role at {company}. "
            f"In my current work as a {current_title}, I've spent {years} years helping teams ship faster and lead better."
        )
    return (
        f"I am excited to apply for the {title} role at {company}. "
        f"With {current_title} experience and {years} years leading engineering delivery, I am confident I can help "
        "your organization execute with speed and quality."
    )


def _body_by_style(
    style: CoverLetterStyle,
    persona: ResumePersona,
    strengths: list[str],
    focus_areas: list[str],
) -> list[str]:
    strengths_text = (
        ", ".join(strengths)
        if strengths
        else "engineering execution, team leadership, and stakeholder alignment"
    )

    if style == CoverLetterStyle.EXECUTIVE:
        body = [
            _persona_line(persona),
            "My recent leadership impact includes: " + strengths_text + ".",
            "For this role, I would focus first on: "
            + ("; ".join(focus_areas) if focus_areas else "execution cadence, talent development, and technical quality")
            + ".",
        ]
        return body

    if style == CoverLetterStyle.STORYTELLING:
        body = [
            _persona_line(persona),
            "Across recent roles, I have consistently improved outcomes in areas such as "
            + strengths_text
            + ".",
        ]
        if focus_areas:
            body.append("At your organization, I would bring that same playbook to: " + "; ".join(focus_areas) + ".")
        return body

    body = [
        _persona_line(persona),
        "I can directly contribute in areas such as " + strengths_text + ".",
    ]
    if focus_areas:
        body.append("Top priorities I would focus on include: " + "; ".join(focus_areas) + ".")
    return body


def _closing_by_tone(tone: CoverLetterTone) -> str:
    if tone == CoverLetterTone.CONFIDENT:
        return (
            "I would welcome the opportunity to discuss how I can help your team deliver meaningful results from day one."
        )
    if tone == CoverLetterTone.CONVERSATIONAL:
        return "I'd welcome the chance to talk through how I could support your team and goals."
    return (
        "I would welcome the opportunity to discuss how my background aligns with your goals and "
        "how I can create measurable impact for the team."
    )


def _draft_markdown(letter: CoverLetterDraft) -> str:
    lines = [
        f"# {letter.subject_line}",
        "",
        letter.greeting,
        "",
        letter.opening_paragraph,
        "",
    ]
    for paragraph in letter.body_paragraphs:
        lines.extend([paragraph, ""])
    lines.extend([letter.closing_paragraph, "", letter.signature])
    return "\n".join(lines)


class CoverLetterService:
    def __init__(self, session: AsyncSession) -> None:
        self.profile_repo = CandidateProfileRepository(session)
        self.job_repo = JobPostingRepository(session)
        self.analysis_repo = JobAnalysisRepository(session)
        self.scoring_repo = ScoringResultRepository(session)
        self.resume_repo = ResumePlanRepository(session)
        self.cover_letter_repo = CoverLetterRepository(session)
        self.settings = get_settings()

    async def build_letter(
        self,
        job_posting_id: int,
        tone: CoverLetterTone = CoverLetterTone.PROFESSIONAL,
        style: CoverLetterStyle = CoverLetterStyle.CONCISE,
    ) -> CoverLetterDraft:
        profile_record = await self.profile_repo.get_profile()
        if profile_record is None:
            raise NotFoundError("CandidateProfile", "singleton")

        job = await self.job_repo.get(job_posting_id)
        if job is None:
            raise NotFoundError("JobPosting", job_posting_id)

        analysis_record = await self.analysis_repo.get_by_job_id(job_posting_id)
        scoring_record = await self.scoring_repo.get_by_job_id(job_posting_id)
        if analysis_record is None or scoring_record is None:
            raise AnalysisNotFoundError(job_posting_id)

        profile = CandidateProfileData.model_validate(profile_record.profile_data)
        requirements = JobRequirements.model_validate(analysis_record.requirements_data)
        scoring = FullAnalysisResult.model_validate(scoring_record.scoring_data)

        resume_record = await self.resume_repo.get_by_job_id(job_posting_id)
        resume_plan: ResumePlan | None = None
        if resume_record is not None:
            resume_plan = ResumePlan.model_validate(resume_record.plan_data)

        persona = (
            resume_plan.strategy.persona
            if resume_plan is not None
            else select_persona(requirements)
        )

        title = job.title or requirements.inferred_title or "Engineering Leadership Role"
        company = job.company or requirements.inferred_company or "your team"
        subject = f"Application for {title}"
        opening = _opening_by_tone(
            tone,
            title,
            company,
            profile.current_title,
            profile.years_total_experience,
        )

        strengths = scoring.gap_analysis.strengths[:3]
        focus_areas = scoring.gap_analysis.resume_focus_areas[:3]
        body_paragraphs = _body_by_style(style, persona, strengths, focus_areas)
        closing = _closing_by_tone(tone)

        draft = CoverLetterDraft(
            job_posting_id=job_posting_id,
            persona=persona,
            tone=tone,
            style=style,
            subject_line=subject,
            greeting="Dear Hiring Team,",
            opening_paragraph=opening,
            body_paragraphs=body_paragraphs,
            closing_paragraph=closing,
            signature=_infer_signature_name(profile),
            markdown="",
        )
        draft.markdown = _draft_markdown(draft)

        await self.cover_letter_repo.upsert(job_posting_id, draft.model_dump(mode="json"))
        return draft

    async def get_letter(self, job_posting_id: int) -> CoverLetterDraft | None:
        record = await self.cover_letter_repo.get_by_job_id(job_posting_id)
        if record is None:
            return None
        return CoverLetterDraft.model_validate(record.letter_data)

    async def save_letter(self, job_posting_id: int) -> Path:
        letter = await self.get_letter(job_posting_id)
        if letter is None:
            letter = await self.build_letter(job_posting_id)

        out_dir = self.settings.reports_dir / "cover_letters"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"job_{job_posting_id}_cover_letter.md"
        out_path.write_text(letter.markdown, encoding="utf-8")
        return out_path
