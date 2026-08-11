"""Achievement Selection Engine.

Ranks the candidate's accomplishments/stories against a job's extracted
requirements, with:

- Recommendation 2: ``boosted_accomplishment_ids`` + ``boost_multiplier`` instead
  of a hard "must include" list, so boosted items rank higher without being
  forced onto a resume where they aren't relevant.
- Recommendation 5: explainability — each ranking carries a list of reasons.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from app.schemas.analysis import JobRequirements
from app.schemas.resume import (
    AccomplishmentEntry,
    AccomplishmentRanking,
    AchievementSelectionResult,
)
from app.services.accomplishment_loader import load_accomplishments

DEFAULT_BOOST_MULTIPLIER = 1.5
DEFAULT_TOP_N = 5
_BASE_SCORE = 40.0
_MAX_MATCH_BONUS = 60.0
_FUZZY_THRESHOLD = 0.8
_NEUTRAL_IMPORTANCE = 5
_IMPORTANCE_WEIGHT = 2.0
_METRIC_BONUS = 15.0


def requirement_signals(req: JobRequirements) -> list[str]:
    """Flatten all requirement fields relevant to accomplishment matching."""
    signals = [
        *req.required_skills,
        *req.preferred_skills,
        *req.leadership_requirements,
        *req.cloud_requirements,
        *req.ai_requirements,
        *req.industry_domain,
        *req.important_keywords,
    ]
    # De-dupe while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for sig in signals:
        key = sig.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(sig)
    return deduped


def _accomplishment_tokens(acc: AccomplishmentEntry) -> set[str]:
    return {tag.lower() for tag in acc.tags} | {acc.category.lower()}


def _accomplishment_text(acc: AccomplishmentEntry) -> str:
    return f"{acc.title} {acc.impact} {acc.category} {' '.join(acc.tags)}".lower()


def _signal_matches(signal: str, tokens: set[str], text: str) -> bool:
    sig = signal.lower().strip()
    if not sig:
        return False
    if sig in text:
        return True
    return any(
        sig in tok or tok in sig or SequenceMatcher(None, sig, tok).ratio() > _FUZZY_THRESHOLD
        for tok in tokens
    )


def rank_accomplishments(
    accomplishments: list[AccomplishmentEntry],
    requirements: JobRequirements,
    boosted_accomplishment_ids: list[str] | None = None,
    boost_multiplier: float = DEFAULT_BOOST_MULTIPLIER,
) -> list[AccomplishmentRanking]:
    """Score every accomplishment against the job requirements, best-first."""
    boosted_ids = set(boosted_accomplishment_ids or [])
    signals = requirement_signals(requirements)

    rankings: list[AccomplishmentRanking] = []
    for acc in accomplishments:
        tokens = _accomplishment_tokens(acc)
        text = _accomplishment_text(acc)

        matched = [sig for sig in signals if _signal_matches(sig, tokens, text)]
        score = _BASE_SCORE + min(_MAX_MATCH_BONUS, len(matched) * 12.0)
        reasons = [f"Matches '{sig}' requirement" for sig in matched]

        # Priority 2: weight inherently stronger accomplishments higher, independent
        # of job relevance, using the accomplishment's importance rating.
        importance_delta = (acc.importance - _NEUTRAL_IMPORTANCE) * _IMPORTANCE_WEIGHT
        if importance_delta:
            score += importance_delta
            if acc.importance >= 9:
                reasons.append("Signature accomplishment")
            elif acc.importance <= 3:
                reasons.append("Supporting accomplishment")

        # Priority 4: quantified/measurable outcomes stand out to reviewers, so
        # give accomplishments with metrics a ranking bonus.
        if acc.metrics:
            score += _METRIC_BONUS
            reasons.append("Includes a measurable, quantified outcome")

        if requirements.manager_of_managers_required and (
            "leadership" in tokens or acc.category.lower() == "leadership"
        ):
            score += 5.0
            reasons.append("Leadership emphasis requested by role")

        if not reasons:
            reasons.append("No direct requirement match")

        is_boosted = acc.id in boosted_ids
        applied_multiplier = 1.0
        if is_boosted:
            applied_multiplier = boost_multiplier
            score = score * boost_multiplier
            reasons.append(f"Boosted by user selection (x{boost_multiplier})")

        score = max(0.0, min(100.0, round(score, 1)))
        rankings.append(
            AccomplishmentRanking(
                id=acc.id,
                ranking_score=score,
                ranking_reason=reasons,
                boosted=is_boosted,
                boost_multiplier=applied_multiplier,
            )
        )

    rankings.sort(key=lambda r: (-r.ranking_score, r.id))
    return rankings


class AchievementSelectionService:
    """Selects the strongest accomplishments to feature for a given job posting."""

    def __init__(self, accomplishments: list[AccomplishmentEntry] | None = None) -> None:
        self.accomplishments = (
            accomplishments if accomplishments is not None else load_accomplishments()
        )

    def select_achievements(
        self,
        job_posting_id: int,
        requirements: JobRequirements,
        boosted_accomplishment_ids: list[str] | None = None,
        boost_multiplier: float = DEFAULT_BOOST_MULTIPLIER,
        top_n: int = DEFAULT_TOP_N,
    ) -> AchievementSelectionResult:
        rankings = rank_accomplishments(
            self.accomplishments,
            requirements,
            boosted_accomplishment_ids=boosted_accomplishment_ids,
            boost_multiplier=boost_multiplier,
        )
        selected = [r.id for r in rankings[:top_n]]

        return AchievementSelectionResult(
            job_posting_id=job_posting_id,
            rankings=rankings,
            selected_accomplishment_ids=selected,
            boosted_accomplishment_ids=list(boosted_accomplishment_ids or []),
            boost_multiplier=boost_multiplier,
        )

    def get_accomplishment(self, accomplishment_id: str) -> AccomplishmentEntry | None:
        for acc in self.accomplishments:
            if acc.id == accomplishment_id:
                return acc
        return None
