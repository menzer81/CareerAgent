"""Keyword Coverage Service (Recommendation 4).

Computes how many of a job's important keywords are demonstrably covered by
the candidate's profile before a resume is generated — a useful job-fit
diagnostic independent of the overall match score.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import KeywordCoverageReport

_FUZZY_THRESHOLD = 0.8


def _candidate_keyword_pool(profile: CandidateProfileData) -> list[str]:
    pool = list(profile.technologies) + profile.cloud_platform_names + list(profile.industries)
    for entry in profile.work_history:
        pool.extend(entry.technologies)
        pool.extend(entry.industries)
        pool.extend(entry.leadership_areas)
    pool.extend(profile.accomplishments)
    pool.extend(profile.career_highlights)
    return pool


def _is_covered(keyword: str, candidate_lower: list[str]) -> bool:
    kw = keyword.lower()
    return any(
        kw in cand or cand in kw or SequenceMatcher(None, kw, cand).ratio() > _FUZZY_THRESHOLD
        for cand in candidate_lower
    )


class KeywordCoverageService:
    """Computes keyword coverage of a job's required/important keywords."""

    def compute_coverage(
        self, requirements: JobRequirements, profile: CandidateProfileData
    ) -> KeywordCoverageReport:
        keywords = list(requirements.important_keywords)
        if not keywords:
            keywords = list(requirements.required_skills) + list(requirements.preferred_skills)

        # De-dupe while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for kw in keywords:
            key = kw.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(kw)
        keywords = deduped

        if not keywords:
            return KeywordCoverageReport(
                required_keywords=0,
                covered_keywords=0,
                coverage_percent=100.0,
                matched_keywords=[],
                missing_keywords=[],
            )

        candidate_lower = [c.lower() for c in _candidate_keyword_pool(profile)]
        matched: list[str] = []
        missing: list[str] = []
        for kw in keywords:
            if _is_covered(kw, candidate_lower):
                matched.append(kw)
            else:
                missing.append(kw)

        coverage_percent = round(len(matched) / len(keywords) * 100, 1)
        return KeywordCoverageReport(
            required_keywords=len(keywords),
            covered_keywords=len(matched),
            coverage_percent=coverage_percent,
            matched_keywords=matched,
            missing_keywords=missing,
        )
