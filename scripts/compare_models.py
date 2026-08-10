"""Compare local and cloud LLM outputs across stored job postings.

By default this compares the current job_postings table. If the table is empty,
it falls back to the golden benchmark dataset in data/golden_jobs.json so you can
still evaluate the local model vs the cloud model immediately.

Usage:
    python -m scripts.compare_models
    python -m scripts.compare_models --source golden
    python -m scripts.compare_models --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Literal

from app.config import Settings, get_settings
from app.database import AsyncSessionLocal, init_db
from app.repositories.candidate_profile_repository import CandidateProfileRepository
from app.repositories.job_posting_repository import JobPostingRepository
from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.services.llm.openai_provider import OpenAIProvider

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def _format_seconds(total_seconds: float) -> str:
    seconds = max(0, int(total_seconds))
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}h {mins:02d}m {secs:02d}s"
    return f"{mins:02d}m {secs:02d}s"


@dataclass(slots=True)
class PostingRecord:
    source: str
    posting_id: int
    label: str
    title: str | None
    company: str | None
    raw_text: str


@dataclass(slots=True)
class ProviderResult:
    requirements: JobRequirements
    overall_score: float
    recommendation: str
    technical_score: float
    cloud_score: float
    ai_score: float
    leadership_score: float
    management_score: float
    industry_score: float


@dataclass(slots=True)
class ComparisonRow:
    posting: PostingRecord
    local: ProviderResult
    cloud: ProviderResult

    @property
    def score_delta(self) -> float:
        return round(self.local.overall_score - self.cloud.overall_score, 1)

    @property
    def recommendation_match(self) -> bool:
        return self.local.recommendation == self.cloud.recommendation

    @property
    def abs_score_delta(self) -> float:
        return abs(self.score_delta)

    @property
    def local_required_count(self) -> int:
        return len(self.local.requirements.required_skills)

    @property
    def cloud_required_count(self) -> int:
        return len(self.cloud.requirements.required_skills)


async def load_profile() -> tuple[CandidateProfileData, str]:
    async with AsyncSessionLocal() as session:
        repo = CandidateProfileRepository(session)
        record = await repo.get_profile()
        if record is not None:
            return CandidateProfileData.model_validate(record.profile_data), "db"

    fallback_path = DATA_DIR / "candidate_profile.json"
    raw = json.loads(fallback_path.read_text(encoding="utf-8"))
    return CandidateProfileData.model_validate(raw), "data/candidate_profile.json"


async def load_postings(source: Literal["db", "golden"], limit: int) -> list[PostingRecord]:
    if source == "golden":
        return load_golden_postings(limit)

    async with AsyncSessionLocal() as session:
        repo = JobPostingRepository(session)
        records = await repo.get_all(limit=limit, offset=0)
        postings = [
            PostingRecord(
                source="db",
                posting_id=record.id,
                label=f"job_{record.id}",
                title=record.title,
                company=record.company,
                raw_text=record.raw_text,
            )
            for record in records
        ]
        if postings:
            return postings

    return load_golden_postings(limit)


def load_golden_postings(limit: int) -> list[PostingRecord]:
    golden_path = DATA_DIR / "golden_jobs.json"
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    postings: list[PostingRecord] = []
    for index, job in enumerate(raw["jobs"][:limit], start=1):
        job_file = job["job_file"]
        text_path = DATA_DIR / "job_descriptions" / job_file
        raw_text = text_path.read_text(encoding="utf-8")
        postings.append(
            PostingRecord(
                source="golden",
                posting_id=index,
                label=job_file,
                title=job.get("title"),
                company=job.get("company"),
                raw_text=raw_text,
            )
        )
    return postings


def build_local_provider(settings: Settings) -> OpenAIProvider:
    if not settings.local_llm_configured():
        raise ValueError(
            "Local LLM is not configured. Set LOCAL_OPENAI_BASE_URL and LOCAL_OPENAI_MODEL."
        )
    return OpenAIProvider(
        settings,
        api_key=settings.local_openai_api_key or "ollama",
        base_url=settings.local_openai_base_url,
        model=settings.local_openai_model,
        provider_name="local",
    )


def build_cloud_provider(settings: Settings) -> OpenAIProvider:
    if settings.cloud_llm_configured():
        return OpenAIProvider(
            settings,
            api_key=settings.cloud_openai_api_key,
            base_url=settings.cloud_openai_base_url,
            model=settings.cloud_openai_model,
            provider_name="cloud",
        )

    if settings.openai_api_key:
        return OpenAIProvider(
            settings,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            provider_name="cloud",
        )

    raise ValueError(
        "Cloud LLM is not configured. Set OPENAI_API_KEY or CLOUD_OPENAI_API_KEY."
    )


async def analyze_with_provider(
    provider: OpenAIProvider,
    profile: CandidateProfileData,
    posting: PostingRecord,
    *,
    extract_timeout_s: float,
    score_timeout_s: float,
) -> ProviderResult:
    requirements = await asyncio.wait_for(
        provider.extract_job_requirements(posting.raw_text),
        timeout=extract_timeout_s,
    )
    scored = await asyncio.wait_for(
        provider.score_and_analyze(profile, requirements, posting.posting_id),
        timeout=score_timeout_s,
    )
    scoring = scored.scoring
    return ProviderResult(
        requirements=requirements,
        overall_score=scoring.overall_score,
        recommendation=scoring.recommendation.value,
        technical_score=scoring.technical_match.score,
        cloud_score=scoring.cloud_match.score,
        ai_score=scoring.ai_match.score,
        leadership_score=scoring.leadership_match.score,
        management_score=scoring.management_scope_match.score,
        industry_score=scoring.industry_match.score,
    )


async def compare_postings(
    source: Literal["db", "golden"],
    limit: int,
    extract_timeout_s: float,
    score_timeout_s: float,
    posting_timeout_s: float,
) -> list[ComparisonRow]:
    settings = get_settings()
    profile, profile_source = await load_profile()
    postings = await load_postings(source, limit)

    local_provider = build_local_provider(settings)
    cloud_provider = build_cloud_provider(settings)

    print(f"Profile source: {profile_source}")
    print(f"Postings source: {source} ({len(postings)} rows)")
    print(f"Local provider: {local_provider.provider_name} / {local_provider.model}")
    print(f"Cloud provider: {cloud_provider.provider_name} / {cloud_provider.model}")
    print()

    rows: list[ComparisonRow] = []
    total = len(postings)
    run_started = time.perf_counter()
    for index, posting in enumerate(postings, start=1):
        elapsed_before = time.perf_counter() - run_started
        if index > 1:
            avg_per_posting = elapsed_before / (index - 1)
            eta_seconds = avg_per_posting * (total - index + 1)
            eta_text = _format_seconds(eta_seconds)
        else:
            eta_text = "estimating..."

        print(
            f"Comparing {posting.label} ({index}/{total}) "
            f"| elapsed {_format_seconds(elapsed_before)} "
            f"| ETA {eta_text}"
        )

        posting_started = time.perf_counter()
        try:
            local_task = analyze_with_provider(
                local_provider,
                profile,
                posting,
                extract_timeout_s=extract_timeout_s,
                score_timeout_s=score_timeout_s,
            )
            cloud_task = analyze_with_provider(
                cloud_provider,
                profile,
                posting,
                extract_timeout_s=extract_timeout_s,
                score_timeout_s=score_timeout_s,
            )
            local, cloud = await asyncio.wait_for(
                asyncio.gather(local_task, cloud_task),
                timeout=posting_timeout_s,
            )
            rows.append(ComparisonRow(posting=posting, local=local, cloud=cloud))
            posting_elapsed = time.perf_counter() - posting_started
            print(f"  -> done in {_format_seconds(posting_elapsed)}")
        except TimeoutError:
            posting_elapsed = time.perf_counter() - posting_started
            print(f"  -> skipped {posting.label}: timed out after {_format_seconds(posting_elapsed)}")
        except Exception as exc:
            posting_elapsed = time.perf_counter() - posting_started
            print(f"  -> skipped {posting.label} after {_format_seconds(posting_elapsed)}: {exc}")

    if len(rows) < total:
        print()
        print(f"Completed {len(rows)}/{total} postings (skipped {total - len(rows)}).")

    total_elapsed = time.perf_counter() - run_started
    print(f"Total runtime: {_format_seconds(total_elapsed)}")
    return rows


def print_summary(rows: list[ComparisonRow]) -> None:
    if not rows:
        print("No postings were found to compare.")
        return

    abs_deltas = [row.abs_score_delta for row in rows]
    rec_matches = sum(1 for row in rows if row.recommendation_match)
    local_higher = sum(1 for row in rows if row.score_delta > 0)
    cloud_higher = sum(1 for row in rows if row.score_delta < 0)

    print()
    print("Summary")
    print("-------")
    print(f"Average absolute score delta: {mean(abs_deltas):.1f}")
    print(f"Max absolute score delta: {max(abs_deltas):.1f}")
    print(f"Recommendation agreement: {rec_matches}/{len(rows)} ({rec_matches / len(rows):.0%})")
    print(f"Local higher score: {local_higher}")
    print(f"Cloud higher score: {cloud_higher}")
    print()

    print("Per-job comparison")
    print("------------------")
    header = (
        "| Job | Local | Cloud | Delta | Rec Match | Req Count L/C |"
    )
    print(header)
    print("|---|---:|---:|---:|---|---:|")
    for row in rows:
        job_name = row.posting.title or row.posting.label
        if row.posting.company:
            job_name = f"{job_name} ({row.posting.company})"
        print(
            f"| {job_name} | {row.local.overall_score:.1f} {row.local.recommendation} | "
            f"{row.cloud.overall_score:.1f} {row.cloud.recommendation} | "
            f"{row.score_delta:+.1f} | {'yes' if row.recommendation_match else 'no'} | "
            f"{row.local_required_count}/{row.cloud_required_count} |"
        )

    print()
    top_deltas = sorted(rows, key=lambda row: row.abs_score_delta, reverse=True)[:5]
    print("Largest divergences")
    print("-------------------")
    for row in top_deltas:
        job_name = row.posting.title or row.posting.label
        print(
            f"- {job_name}: local {row.local.overall_score:.1f} vs cloud {row.cloud.overall_score:.1f} "
            f"(Delta {row.score_delta:+.1f}, local rec {row.local.recommendation}, cloud rec {row.cloud.recommendation})"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare local and cloud model outputs over job postings.")
    parser.add_argument(
        "--source",
        choices=("db", "golden"),
        default="db",
        help="Compare stored job postings from the database or the golden benchmark dataset.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of postings to compare.",
    )
    parser.add_argument(
        "--extract-timeout",
        type=float,
        default=90.0,
        help="Timeout in seconds for each extraction call.",
    )
    parser.add_argument(
        "--score-timeout",
        type=float,
        default=120.0,
        help="Timeout in seconds for each scoring call.",
    )
    parser.add_argument(
        "--posting-timeout",
        type=float,
        default=180.0,
        help="Overall timeout in seconds for both local+cloud evaluation of one posting.",
    )
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    await init_db()
    rows = await compare_postings(
        args.source,
        args.limit,
        extract_timeout_s=args.extract_timeout,
        score_timeout_s=args.score_timeout,
        posting_timeout_s=args.posting_timeout,
    )
    print_summary(rows)


if __name__ == "__main__":
    asyncio.run(async_main())
