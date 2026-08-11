"""OpenAI-compatible LLM provider.

Uses the openai SDK with a configurable base_url — works with:
  - OpenAI (https://api.openai.com/v1)
  - Azure OpenAI
  - OpenRouter (https://openrouter.ai/api/v1)
  - Local models via Ollama or LM Studio
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings
from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import AccomplishmentEntry, GeneratedResumeContent, ResumeStrategy
from app.schemas.scoring import (
    DimensionScore,
    FullAnalysisResult,
    GapAnalysis,
    Recommendation,
    ScoringBreakdown,
)
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_LLM_PATH_STATS = {
    "extract": {"native": 0, "adapted": 0},
    "score": {"native": 0, "adapted": 0},
}

_EXTRACT_SYSTEM_PROMPT = """You are an expert talent analyst. Extract structured requirements
from a job posting and return valid JSON matching the provided schema exactly.
Be thorough — capture all required skills, preferred skills, leadership requirements,
cloud requirements, AI/ML requirements, and key keywords.
For boolean fields, infer from the job description context."""

_SCORE_SYSTEM_PROMPT = """You are a senior technical recruiter and career coach specializing
in software engineering leadership roles. You are given a candidate profile and a structured
set of job requirements. Your task is to:
1. Score the candidate across six dimensions (0-100 each)
2. Identify gaps, strengths, and risks
3. Provide an actionable recommendation

Return valid JSON exactly matching the provided schema. Be specific and honest.
A score of 0-100 where: 90-100=exceptional match, 70-89=strong match, 50-69=moderate/stretch,
below 50=significant gap."""

_GENERATE_CONTENT_SYSTEM_PROMPT = """You are an expert executive resume writer specializing in tailoring resumes to specific job postings.
You are given a candidate's structured profile, a job's structured requirements, a resume strategy
(persona, themes to emphasize/deemphasize/omit), and the candidate's top selected accomplishments.

Your job is to REWRITE resume copy so it is CLEARLY AND SPECIFICALLY tailored to THIS job:

EXECUTIVE SUMMARY rules:
- Write 2-4 sentences targeted at this specific job — mention the role type, key skills from the
  job requirements, and the candidate's most relevant experience. Do NOT write a generic summary.
- Mirror the language and priorities from the job's requirements and important_keywords.
- The summary should read differently for a compliance role vs an AI role vs a cloud role.

EXPERIENCE BULLETS rules:
- Reorder bullets within each role to lead with the accomplishments most relevant to THIS job.
- Reframe language to echo the job's terminology (e.g. if job says "platform engineering", use
  that phrase where it fits; if job emphasizes "cost reduction", lead with cost-related bullets).
- Keep facts, employers, and metrics unchanged — only reframe emphasis and word choice.
- Omit or shorten bullets for the themes listed in the strategy's "omit" and "deemphasize" lists.

ACCOMPLISHMENT BULLETS rules:
- Rewrite each accomplishment bullet to call out the specific dimension this job cares about.
  (e.g. if job is AI-focused, frame compliance automation as "AI-driven compliance automation").
- Keep every fact and metric exactly as supplied — never fabricate numbers or employers.

Rules for all content:
- Every fact, employer, technology, and metric must come directly from the supplied data.
- Prefer active voice and quantified impact when metrics are already present in the source data.
- Keep bullets concise (1-2 sentences each).
- Return valid JSON exactly matching the provided schema."""


def _try_parse_json_object(raw_text: str) -> tuple[dict[str, Any], str]:
    """Parse the first JSON object found in raw_text.

    Some local models return extra prose before/after JSON. This helper scans
    for a decodable JSON object rather than requiring a perfect raw object.
    """
    text = raw_text.strip()
    decoder = json.JSONDecoder()
    if text.startswith("{"):
        try:
            obj, end = decoder.raw_decode(text)
            if isinstance(obj, dict):
                mode = "direct" if end == len(text) else "prefixed"
                return obj, mode
        except json.JSONDecodeError:
            pass

    for idx, ch in enumerate(raw_text):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(raw_text[idx:])
            if isinstance(obj, dict):
                return obj, "scanned"
        except json.JSONDecodeError:
            continue
    raise ValueError("No JSON object found in model response")


def _extract_response_json_payload(response: Any) -> tuple[dict[str, Any], str, str]:
    """Extract JSON payload from chat completion response.

    OpenAI-compatible local providers may emit an empty `content` string and
    place output-like text in a `reasoning` field. We prefer `content` but
    fall back to `reasoning` when needed.
    """
    message = response.choices[0].message
    content = (message.content or "").strip()
    reasoning = (getattr(message, "reasoning", None) or "").strip()

    source = "content" if content else "reasoning"
    raw = content or reasoning
    if not raw:
        raise ValueError("Model response did not include content or reasoning text")

    payload, parse_mode = _try_parse_json_object(raw)
    return payload, source, parse_mode


_DIMENSION_WEIGHTS = {
    "leadership_match": 0.20,
    "technical_match": 0.25,
    "cloud_match": 0.15,
    "ai_match": 0.10,
    "management_scope_match": 0.15,
    "industry_match": 0.15,
}


def _normalize_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return [p for p in parts if p]
    return []


def _clamp_score(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(100.0, score))


def _pick_value(payload: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        if alias in payload:
            return payload.get(alias)
    nested_scores = payload.get("scores")
    if isinstance(nested_scores, dict):
        for alias in aliases:
            if alias in nested_scores:
                return nested_scores.get(alias)
    return None


def _normalize_dimension(payload: dict[str, Any], aliases: list[str], label: str) -> dict[str, Any]:
    raw = _pick_value(payload, aliases)
    if isinstance(raw, dict):
        score = _clamp_score(raw.get("score"), default=0.0)
        explanation = str(raw.get("explanation") or f"{label} score from LLM response.")
        matched = _normalize_str_list(raw.get("matched"))
        missing = _normalize_str_list(raw.get("missing"))
        return {
            "score": score,
            "explanation": explanation,
            "matched": matched,
            "missing": missing,
        }

    score = _clamp_score(raw, default=0.0)
    return {
        "score": score,
        "explanation": f"{label} score from LLM response.",
        "matched": [],
        "missing": [],
    }


def _normalize_recommendation(raw: Any, overall_score: float) -> str:
    text = str(raw or "").strip().lower()
    if "strong" in text:
        return Recommendation.STRONG_APPLY.value
    if "stretch" in text:
        return Recommendation.STRETCH_OPPORTUNITY.value
    if "low" in text:
        return Recommendation.LOW_PRIORITY.value
    if text == "apply" or " apply" in text:
        return Recommendation.APPLY.value

    if overall_score >= 85:
        return Recommendation.STRONG_APPLY.value
    if overall_score >= 70:
        return Recommendation.APPLY.value
    if overall_score >= 55:
        return Recommendation.STRETCH_OPPORTUNITY.value
    return Recommendation.LOW_PRIORITY.value


def _normalize_full_analysis_payload(payload: dict[str, Any], job_posting_id: int) -> tuple[dict[str, Any], str]:
    """Normalize variant LLM outputs into FullAnalysisResult schema.

    Some local models return flattened or partially structured scoring objects.
    This adapter maps common variants into the strict schema our API persists.
    """
    if "scoring" in payload and "gap_analysis" in payload:
        normalized = dict(payload)
        normalized.setdefault("job_posting_id", job_posting_id)
        return normalized, "native"

    leadership = _normalize_dimension(
        payload,
        ["leadership_match", "leadership", "leadership_score"],
        "Leadership",
    )
    technical = _normalize_dimension(
        payload,
        ["technical_match", "technical", "technical_score"],
        "Technical",
    )
    cloud = _normalize_dimension(
        payload,
        ["cloud_match", "cloud", "cloud_score"],
        "Cloud",
    )
    ai = _normalize_dimension(
        payload,
        ["ai_match", "ai", "ai_score", "ml_match"],
        "AI/ML",
    )
    management_scope = _normalize_dimension(
        payload,
        ["management_scope_match", "management_scope", "management", "management_score"],
        "Management Scope",
    )
    industry = _normalize_dimension(
        payload,
        ["industry_match", "industry", "industry_score"],
        "Industry",
    )

    inferred_overall = round(
        leadership["score"] * _DIMENSION_WEIGHTS["leadership_match"]
        + technical["score"] * _DIMENSION_WEIGHTS["technical_match"]
        + cloud["score"] * _DIMENSION_WEIGHTS["cloud_match"]
        + ai["score"] * _DIMENSION_WEIGHTS["ai_match"]
        + management_scope["score"] * _DIMENSION_WEIGHTS["management_scope_match"]
        + industry["score"] * _DIMENSION_WEIGHTS["industry_match"],
        1,
    )

    scoring_block = payload.get("scoring") if isinstance(payload.get("scoring"), dict) else {}
    overall_score = _clamp_score(
        scoring_block.get("overall_score", payload.get("overall_score", inferred_overall)),
        default=inferred_overall,
    )
    recommendation = _normalize_recommendation(
        scoring_block.get("recommendation", payload.get("recommendation")),
        overall_score,
    )
    recommendation_reasoning = str(
        scoring_block.get("recommendation_reasoning")
        or payload.get("recommendation_reasoning")
        or "Recommendation inferred from normalized LLM scoring output."
    )

    gap_payload = payload.get("gap_analysis") if isinstance(payload.get("gap_analysis"), dict) else payload
    gap_analysis = {
        "missing_experiences": _normalize_str_list(gap_payload.get("missing_experiences")),
        "missing_keywords": _normalize_str_list(
            gap_payload.get("missing_keywords") or gap_payload.get("gaps") or gap_payload.get("missing")
        ),
        "missing_certifications": _normalize_str_list(gap_payload.get("missing_certifications")),
        "missing_leadership_signals": _normalize_str_list(gap_payload.get("missing_leadership_signals")),
        "strengths": _normalize_str_list(gap_payload.get("strengths")),
        "risks": _normalize_str_list(gap_payload.get("risks") or gap_payload.get("concerns")),
        "resume_focus_areas": _normalize_str_list(
            gap_payload.get("resume_focus_areas") or gap_payload.get("recommendations")
        ),
    }

    return {
        "job_posting_id": int(payload.get("job_posting_id", job_posting_id)),
        "scoring": {
            "leadership_match": leadership,
            "technical_match": technical,
            "cloud_match": cloud,
            "ai_match": ai,
            "management_scope_match": management_scope,
            "industry_match": industry,
            "overall_score": overall_score,
            "recommendation": recommendation,
            "recommendation_reasoning": recommendation_reasoning,
        },
        "gap_analysis": gap_analysis,
    }, "adapted"


def get_llm_path_summary() -> dict[str, dict[str, int]]:
    """Return a shallow copy of the current LLM path counters."""
    return {stage: dict(counts) for stage, counts in _LLM_PATH_STATS.items()}


def _bump_llm_path(stage: str, mode: str) -> None:
    if stage in _LLM_PATH_STATS and mode in _LLM_PATH_STATS[stage]:
        _LLM_PATH_STATS[stage][mode] += 1


def _normalize_generated_resume_content(
    data: dict[str, Any],
    selected_accomplishments: list,
) -> dict[str, Any]:
    """Repair common LLM schema drift in GeneratedResumeContent payloads.

    Some local models (e.g. Qwen) return accomplishment_bullets items with a
    ``title`` key (mirroring the AccomplishmentEntry input) instead of the
    required ``id`` + ``generated_text`` fields.  This adapter fixes that in
    place so validation doesn't fail needlessly.
    """
    acc_id_by_title: dict[str, str] = {a.title: a.id for a in selected_accomplishments}

    raw_bullets = data.get("accomplishment_bullets")
    if not isinstance(raw_bullets, list):
        return data

    fixed: list[dict[str, Any]] = []
    for item in raw_bullets:
        if not isinstance(item, dict):
            fixed.append(item)
            continue
        if "id" in item and "generated_text" in item:
            fixed.append(item)
            continue
        # Try to recover id from title field
        title = item.get("title", "")
        recovered_id = acc_id_by_title.get(title, "")
        if not recovered_id and ":" in title:
            # Qwen sometimes prefixes "JJK-003: ..." — the part before ":" is the id
            candidate = title.split(":")[0].strip()
            if any(a.id == candidate for a in selected_accomplishments):
                recovered_id = candidate
        generated_text = (
            item.get("generated_text")
            or item.get("description")
            or item.get("impact")
            or item.get("content")
            or title
        )
        fixed.append({"id": recovered_id or title, "generated_text": generated_text})
        if recovered_id:
            logger.debug("Normalized accomplishment_bullet title=%r → id=%r", title, recovered_id)
        else:
            logger.warning(
                "Could not resolve accomplishment id for bullet title=%r; using title as id", title
            )

    data["accomplishment_bullets"] = fixed
    return data


class OpenAIProvider(BaseLLMProvider):
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider_name: str = "openai-compatible",
    ) -> None:
        self.model = model or settings.openai_model
        self.provider_name = provider_name
        self.client = AsyncOpenAI(
            api_key=api_key if api_key is not None else settings.openai_api_key,
            base_url=base_url if base_url is not None else settings.openai_base_url,
        )

    def _temperature(self, default: float) -> float:
        """Return a temperature that the configured model accepts."""
        if self.provider_name == "cloud" and self.model.startswith("gpt-5"):
            return 1.0
        return default

    async def extract_job_requirements(self, job_text: str) -> JobRequirements:
        schema = JobRequirements.model_json_schema()
        user_prompt = f"""Extract the job requirements from the following job posting.
Return a JSON object that strictly follows this schema:
{json.dumps(schema, indent=2)}

JOB POSTING:
{job_text}"""

        logger.debug("Calling LLM to extract job requirements")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature(0.1),
        )
        data, source, parse_mode = _extract_response_json_payload(response)
        _bump_llm_path("extract", "native" if source == "content" and parse_mode == "direct" else "adapted")
        logger.info(
            "LLM extract payload parsed provider=%s model=%s source=%s parse_mode=%s keys=%d",
            self.provider_name,
            self.model,
            source,
            parse_mode,
            len(data),
        )
        return JobRequirements.model_validate(data)

    async def score_and_analyze(
        self,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        job_posting_id: int,
    ) -> FullAnalysisResult:
        result_schema = FullAnalysisResult.model_json_schema()
        user_prompt = f"""Score and analyze the following candidate against the job requirements.
Return a JSON object that strictly follows this schema:
{json.dumps(result_schema, indent=2)}

CANDIDATE PROFILE:
{profile.model_dump_json(indent=2)}

JOB REQUIREMENTS:
{requirements.model_dump_json(indent=2)}

The job_posting_id field must be: {job_posting_id}

Scoring guidance per dimension:
- leadership_match: Compare leadership history, team size, org complexity, MoM experience
- technical_match: Overlap of required+preferred skills vs candidate technologies
- cloud_match: Cloud platform alignment and specific service experience
- ai_match: AI/ML product and engineering experience alignment
- management_scope_match: Team size, direct reports, cross-functional scope, budget
- industry_match: Domain/vertical experience alignment

For overall_score: weighted sum using
  leadership=20%, technical=25%, cloud=15%, ai=10%, management=15%, industry=15%

Recommendation tiers:
  Strong Apply >= 85, Apply >= 70, Stretch Opportunity >= 55, Low Priority < 55"""

        logger.debug("Calling LLM for scoring and analysis")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SCORE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature(0.2),
        )
        data, source, parse_mode = _extract_response_json_payload(response)
        normalized, normalization_mode = _normalize_full_analysis_payload(data, job_posting_id)
        _bump_llm_path("score", "native" if normalization_mode == "native" else "adapted")
        logger.info(
            "LLM scoring payload normalized provider=%s model=%s source=%s parse_mode=%s normalization=%s",
            self.provider_name,
            self.model,
            source,
            parse_mode,
            normalization_mode,
        )
        data = normalized
        return FullAnalysisResult.model_validate(data)

    async def generate_resume_content(
        self,
        job_posting_id: int,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        strategy: ResumeStrategy,
        selected_accomplishments: list[AccomplishmentEntry],
    ) -> GeneratedResumeContent:
        schema = GeneratedResumeContent.model_json_schema()
        # Build a concise job-signal summary to prime the model before the full data dump
        top_keywords = ", ".join(requirements.important_keywords[:10]) if requirements.important_keywords else "none"
        top_ai_reqs = ", ".join(requirements.ai_requirements[:5]) if requirements.ai_requirements else "none"
        top_cloud_reqs = ", ".join(requirements.cloud_requirements[:5]) if requirements.cloud_requirements else "none"
        role_summary_line = requirements.role_summary or "Not specified"

        user_prompt = f"""Rewrite the resume content for this candidate/job pairing.
Return a JSON object that strictly follows this schema:
{json.dumps(schema, indent=2)}

The job_posting_id field must be: {job_posting_id}

=== JOB SIGNAL SUMMARY (use these to drive tailoring) ===
Role summary: {role_summary_line}
Persona to present: {strategy.persona}
Key themes to emphasize: {", ".join(strategy.key_themes)}
Skills/areas to emphasize: {", ".join(strategy.emphasize) if strategy.emphasize else "none"}
Content to deemphasize: {", ".join(strategy.deemphasize) if strategy.deemphasize else "none"}
Content to omit: {", ".join(strategy.omit[:3]) if strategy.omit else "none"}
Top job keywords: {top_keywords}
AI requirements: {top_ai_reqs}
Cloud requirements: {top_cloud_reqs}
Director/MoM required: {requirements.director_level_or_above or requirements.manager_of_managers_required}

=== FULL DATA ===

CANDIDATE PROFILE:
{profile.model_dump_json(indent=2)}

JOB REQUIREMENTS:
{requirements.model_dump_json(indent=2)}

RESUME STRATEGY:
{strategy.model_dump_json(indent=2)}

SELECTED ACCOMPLISHMENTS:
{json.dumps([a.model_dump() for a in selected_accomplishments], indent=2)}

CRITICAL field-name rules (do NOT deviate):
- For experience_bullets: each item must have "company" (string) and "bullets" (list of strings).
  Include one entry per company in the candidate's work_history that has key_accomplishments.
  Use the exact "company" name from work_history.
- For accomplishment_bullets: each item must have exactly two fields:
    "id": the accomplishment's original id value (e.g. "JJK-003") — copy it exactly
    "generated_text": your rewritten bullet text as a single string
  Include one entry per selected accomplishment. Do NOT use "title", "description",
  "impact", or any other key — only "id" and "generated_text"."""

        logger.debug("Calling LLM to generate resume content")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _GENERATE_CONTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature(0.4),
        )
        data, source, parse_mode = _extract_response_json_payload(response)
        logger.info(
            "LLM resume content payload parsed provider=%s model=%s source=%s parse_mode=%s",
            self.provider_name,
            self.model,
            source,
            parse_mode,
        )
        data.setdefault("job_posting_id", job_posting_id)
        data["generated_by"] = "llm"
        data = _normalize_generated_resume_content(data, selected_accomplishments)
        return GeneratedResumeContent.model_validate(data)
