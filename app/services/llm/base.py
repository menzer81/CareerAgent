"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import AccomplishmentEntry, GeneratedResumeContent, ResumeStrategy
from app.schemas.scoring import FullAnalysisResult


class BaseLLMProvider(ABC):
    """All LLM interactions go through this interface.

    Swap implementations by injecting a different provider — no service code changes needed.
    """

    @abstractmethod
    async def extract_job_requirements(self, job_text: str) -> JobRequirements:
        """Parse a raw job posting and return structured requirements."""
        ...

    @abstractmethod
    async def score_and_analyze(
        self,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        job_posting_id: int,
    ) -> FullAnalysisResult:
        """Score the candidate against the job requirements and produce a full analysis."""
        ...

    @abstractmethod
    async def generate_resume_content(
        self,
        job_posting_id: int,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        strategy: ResumeStrategy,
        selected_accomplishments: list[AccomplishmentEntry],
    ) -> GeneratedResumeContent:
        """Rewrite the executive summary and experience/accomplishment bullets.

        The LLM should synthesize and improve wording/framing based on the
        candidate profile, resume strategy, and selected accomplishments — it
        must not invent facts, employers, metrics, or experience that aren't
        already present in the supplied data.
        """
        ...
