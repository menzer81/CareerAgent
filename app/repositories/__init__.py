from app.repositories.base import BaseRepository
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.repositories.job_analysis_repository import JobAnalysisRepository, ScoringResultRepository

__all__ = [
    "BaseRepository",
    "CandidateProfileRepository",
    "JobPostingRepository",
    "JobAnalysisRepository",
    "ScoringResultRepository",
]
