"""OpenAI-compatible LLM provider.

Uses the openai SDK with a configurable base_url — works with:
  - OpenAI (https://api.openai.com/v1)
  - Azure OpenAI
  - OpenRouter (https://openrouter.ai/api/v1)
  - Local models via Ollama or LM Studio
"""

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings
from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.resume import AccomplishmentEntry, GeneratedResumeContent, ResumePersona, ResumeStrategy
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

_PERSONA_SYSTEM_PROMPT = """You are an expert resume strategist. Given a set of structured job
requirements, choose the single resume persona (framing of the candidate's experience) that will
resonate most with this specific job. Return valid JSON exactly matching the provided schema —
your "persona" field must be one of the allowed enum values, copied verbatim."""

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

⚠️  ABSOLUTE RULE — NO INVENTED NUMBERS OR STATISTICS ⚠️
Every percentage, count, dollar amount, or any other number that appears in your output MUST
come verbatim from the supplied candidate data (profile, work history, accomplishments).
Do NOT invent, estimate, round, or extrapolate any metric that is not explicitly present in the
input data. If no number exists for a claim, write the claim without any number.
Violation of this rule makes the resume legally and professionally harmful to the candidate.

Your job is to REWRITE resume copy so it is CLEARLY AND SPECIFICALLY tailored to THIS job:

EXECUTIVE SUMMARY rules:
- Write 4-6 sentences targeted at this specific job — mention the role type, key skills from the
    job requirements, and the candidate's most relevant experience. Do NOT write a generic summary.
- Mirror the language and priorities from the job's requirements and important_keywords.
- The summary should read differently for a compliance role vs an AI role vs a cloud role.
- The summary must include role fit, leadership/delivery strengths, and relevant technical domain
    strengths (AI/cloud/compliance) that are supported by the candidate profile.
- If the job is AI-heavy relative to leadership demand, include at least two AI references in
    the summary using candidate-supported terms (AI, Copilot, agents, LLM, automation).
- Use terminology from the job posting,
  but do not reference the employer's internal team names,
  departments, products, or business units (e.g. "FIIG Technology", "Transformers").
- Avoid presumptive terminology from the job posting,
  such as "Ready to lead @<company>'s team" or "positioned to lead Manager, Engineering (Transformers) efforts".  
  The resume should be tailored to the job's requirements, not the employer's internal org.
- Do not overstate experience or job titles. Allowed: "Software Development Manager", "Engineering Manager", 
  "Software Engineer", "Engineering Leader", "Senior Engineering Manager", etc. Important!!! - Not allowed: 
  "Director-level engineering leader", "Head of Engineering", "Chief Engineer", 
  "Principal Engineer", "Executive leader", "Enterprise AI executive", etc.

EXPERIENCE BULLETS rules:
- Reorder bullets within each role to lead with the accomplishments most relevant to THIS job.
- Reframe language to echo the job's terminology (e.g. if job says "platform engineering", use
  that phrase where it fits; if job emphasizes "cost reduction", lead with cost-related bullets).
- Keep facts, employers, and metrics unchanged — only reframe emphasis and word choice.
- Omit or shorten bullets for the themes listed in the strategy's "omit" and "deemphasize" lists.
- Only use numbers that appear in the source key_accomplishments text for that role.
- Keep present tense for current-role accomplishments when the source text is present tense.

ACCOMPLISHMENT BULLETS rules:
- Rewrite each accomplishment bullet to call out the specific dimension this job cares about.
  (e.g. if job is AI-focused, frame compliance automation as "AI-driven compliance automation").
- Only use the exact numbers present in the accomplishment's impact and metrics fields.

Rules for all content:
- Every fact, employer, technology, and metric must come directly from the supplied data.
- Never fabricate numbers, percentages, team sizes, or statistics not present in the input.
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


_AI_SIGNAL_TERMS = (
    "ai",
    "artificial intelligence",
    "machine learning",
    "ml",
    "llm",
    "copilot",
    "agent",
    "automation",
)

_LEADERSHIP_SIGNAL_TERMS = (
    "lead",
    "leadership",
    "manager",
    "management",
    "director",
    "vp",
    "stakeholder",
    "organization",
    "team",
)


def _count_keyword_hits(keywords: list[str], terms: tuple[str, ...]) -> int:
    count = 0
    lowered = [kw.lower() for kw in keywords]
    for kw in lowered:
        if any(term in kw for term in terms):
            count += 1
    return count


def summarize_signal_balance(requirements: JobRequirements) -> tuple[int, int, bool]:
    """Return AI and leadership signal counts and whether AI should be emphasized.

    AI-heavy means AI signal count is at least leadership signal count and AI
    signals are present.
    """
    role_summary = (requirements.role_summary or "").lower()

    ai_count = len(requirements.ai_requirements)
    ai_count += _count_keyword_hits(requirements.important_keywords, _AI_SIGNAL_TERMS)
    if any(term in role_summary for term in _AI_SIGNAL_TERMS):
        ai_count += 1

    leadership_count = len(requirements.leadership_requirements)
    leadership_count += _count_keyword_hits(requirements.important_keywords, _LEADERSHIP_SIGNAL_TERMS)
    if requirements.manager_of_managers_required or requirements.director_level_or_above:
        leadership_count += 1
    if any(term in role_summary for term in _LEADERSHIP_SIGNAL_TERMS):
        leadership_count += 1

    should_emphasize_ai = ai_count > 0 and ai_count >= leadership_count
    return ai_count, leadership_count, should_emphasize_ai


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
        user_prompt = f"""Extract structured requirements from the following job posting.
        
Look for these key pieces of information:
- Job title/position (often at the top, or labeled "Job Title:", "Position:", "Role:", "Job Family:")
- Company name (often in header or near bottom in "About [Company]", or deducible from context)
- Required skills, technologies, and frameworks
- Preferred/nice-to-have skills
- Leadership or management requirements
- Cloud platform requirements (AWS, Azure, GCP)
- AI/ML/automation requirements

Return a JSON object that STRICTLY follows this schema and captures these elements:
{json.dumps(schema, indent=2)}

Make especially sure to populate:
- inferred_title: The job title or role name (e.g. "Senior Software Engineer", "Engineering Manager")
- inferred_company: The company hiring for this role (e.g. "Microsoft", "Acme Corp")
- required_skills, preferred_skills: Technology stacks, frameworks, languages
- required_keywords, important_keywords: Key terms and phrases that appear multiple times

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

    async def select_resume_persona(self, requirements: JobRequirements) -> ResumePersona:
        persona_values = [p.value for p in ResumePersona]
        user_prompt = f"""Choose the resume persona that best fits this job's requirements.

Allowed personas (return the "persona" field as EXACTLY one of these strings):
{json.dumps(persona_values, indent=2)}

JOB REQUIREMENTS:
{requirements.model_dump_json(indent=2)}

Return a JSON object of the form: {{"persona": "<one of the allowed persona strings>"}}"""

        logger.debug("Calling LLM to select resume persona")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _PERSONA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature(0.0),
        )
        data, _source, _parse_mode = _extract_response_json_payload(response)
        raw_persona = str(data.get("persona", "")).strip()
        try:
            return ResumePersona(raw_persona)
        except ValueError:
            # Some models return the enum member name instead of its value
            # (e.g. "AI_TRANSFORMATION_LEADER" instead of "AI Transformation Leader").
            normalized = raw_persona.strip().lower().replace("_", " ").replace("-", " ")
            for persona in ResumePersona:
                if persona.value.lower() == normalized or persona.name.lower().replace("_", " ") == normalized:
                    return persona
            raise ValueError(f"LLM returned unrecognized persona: {raw_persona!r}")

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

CRITICAL ANALYSIS INSTRUCTIONS:

Scoring guidance per dimension:
- leadership_match: Compare leadership history, team size, org complexity, MoM experience
- technical_match: Compare REQUIRED and PREFERRED technologies:
  * List what the job requires/prefers (languages, frameworks, databases, tools)
  * List what the candidate demonstrably has (from core_skills and work history)
  * Identify specific GAPS (required tech the candidate lacks) and MISMATCHES (e.g., Java vs C#)
  * Score based on overlap; tech stack gaps should significantly lower this score
- cloud_match: Cloud platform alignment and specific service experience
- ai_match: AI/ML product and engineering experience alignment
- management_scope_match: Team size, direct reports, cross-functional scope, budget
- industry_match: Domain/vertical experience alignment

For gap_analysis:
- Potential Gaps section MUST explicitly call out TECHNOLOGY/SKILL MISMATCHES:
  * If job requires Java/Spring Boot and candidate has C#/.NET, flag as "Java/Spring Boot experience" gap
  * If job requires specific databases (NoSQL, etc) and candidate has different tech, flag it
  * Do NOT omit tech stack gaps from the analysis
- Include these alongside other gaps like leadership level, scale experience, etc.

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
        return await self._generate_resume_content(
            job_posting_id,
            profile,
            requirements,
            strategy,
            selected_accomplishments,
            summary_guidance=None,
        )

    async def generate_resume_content_with_guidance(
        self,
        job_posting_id: int,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        strategy: ResumeStrategy,
        selected_accomplishments: list[AccomplishmentEntry],
        summary_guidance: str,
    ) -> GeneratedResumeContent:
        """Generate resume content with additional summary constraints for retry flows."""
        return await self._generate_resume_content(
            job_posting_id,
            profile,
            requirements,
            strategy,
            selected_accomplishments,
            summary_guidance=summary_guidance,
        )

    async def _generate_resume_content(
        self,
        job_posting_id: int,
        profile: CandidateProfileData,
        requirements: JobRequirements,
        strategy: ResumeStrategy,
        selected_accomplishments: list[AccomplishmentEntry],
        summary_guidance: str | None,
    ) -> GeneratedResumeContent:
        schema = GeneratedResumeContent.model_json_schema()
        # Build a concise job-signal summary to prime the model before the full data dump
        top_keywords = ", ".join(requirements.important_keywords[:10]) if requirements.important_keywords else "none"
        top_ai_reqs = ", ".join(requirements.ai_requirements[:5]) if requirements.ai_requirements else "none"
        top_cloud_reqs = ", ".join(requirements.cloud_requirements[:5]) if requirements.cloud_requirements else "none"
        role_summary_line = requirements.role_summary or "Not specified"
        ai_signal_count, leadership_signal_count, should_emphasize_ai = summarize_signal_balance(requirements)

        # Normalize accomplishment metrics to integers for clean serialization (500.0 → 500)
        normalized_accs = []
        for acc in selected_accomplishments:
            acc_dict = acc.model_dump()
            if acc_dict.get("metrics"):
                normalized_metrics = {}
                for k, v in acc_dict["metrics"].items():
                    # Convert float 500.0 to int 500
                    if isinstance(v, float) and v == int(v):
                        normalized_metrics[k] = int(v)
                    else:
                        normalized_metrics[k] = v
                acc_dict["metrics"] = normalized_metrics
            normalized_accs.append(acc_dict)

        # Build an explicit inventory of permitted numbers per role so the model
        # cannot claim it was "inferring" — if it's not in this list, it's fabricated.
        permitted_numbers_by_company: dict[str, set[str]] = {}
        for entry in profile.work_history:
            nums: set[str] = set()
            for text in entry.key_accomplishments:
                nums |= {m.replace(",", "") for m in re.findall(r"\d+(?:[.,]\d+)?", text)}
            for field in (entry.team_size, entry.direct_reports, entry.largest_org_influence):
                if field is not None:
                    nums.add(str(int(field) if isinstance(field, float) and field == int(field) else field))
            permitted_numbers_by_company[entry.company] = nums

        permitted_numbers_lines = "\n".join(
            f"  {company}: {sorted(nums) if nums else ['none — do not use any numbers']}"
            for company, nums in permitted_numbers_by_company.items()
            if company in {e.company for e in profile.work_history}
        )

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

=== PERMITTED NUMBERS PER ROLE (EXHAUSTIVE — use ONLY these numbers in experience_bullets) ===
{permitted_numbers_lines}

=== SUMMARY CONSTRAINTS ===
Executive summary sentence target: 4-6 sentences.
AI signal count: {ai_signal_count}
Leadership signal count: {leadership_signal_count}
AI-heavy-or-equal profile: {should_emphasize_ai}
{f"Additional retry guidance: {summary_guidance}" if summary_guidance else ""}

=== FULL DATA ===

CANDIDATE PROFILE:
{profile.model_dump_json(indent=2)}

JOB REQUIREMENTS:
{requirements.model_dump_json(indent=2)}

RESUME STRATEGY:
{strategy.model_dump_json(indent=2)}

SELECTED ACCOMPLISHMENTS:
{json.dumps(normalized_accs, indent=2)}

CRITICAL rules (do NOT deviate):
- ⚠️  NUMBERS: You may ONLY use numbers listed in "PERMITTED NUMBERS PER ROLE" above for
  experience_bullets, and numbers from each accomplishment's impact/metrics for
  accomplishment_bullets. Any other number is fabricated and must NOT appear.
- Executive summary must be 4-6 sentences and include role fit, leadership/delivery strengths,
    and candidate-supported domain strengths.
- If "AI-heavy-or-equal profile" is true, executive_summary must include at least two mentions
    of AI-related terms grounded in the candidate data.
- Use terminology from the job posting,
  but do not reference the employer's internal team names,
  departments, products, or business units (e.g. "FIIG Technology", "Transformers").
- Avoid presumptive terminology from the job posting,
  such as "Ready to lead @<company>'s team" or "positioned to lead Manager, Engineering (Transformers) efforts".  
  The resume should be tailored to the job's requirements, not the employer's internal org.
- Do not overstate experience or job titles. Allowed: "Software Development Manager", "Engineering Manager", "Software Engineer", "Engineering Leader", "Senior Engineering Manager", etc.
  Important!!! - Not allowed: "Director-level engineering leader", "Head of Engineering", "Chief Engineer", "Principal Engineer", "Executive leader", "Enterprise AI executive", etc.
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
