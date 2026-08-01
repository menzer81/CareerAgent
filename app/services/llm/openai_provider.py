"""OpenAI-compatible LLM provider.

Uses the openai SDK with a configurable base_url — works with:
  - OpenAI (https://api.openai.com/v1)
  - Azure OpenAI
  - OpenRouter (https://openrouter.ai/api/v1)
  - Local models via Ollama or LM Studio
"""

import json
import logging

from openai import AsyncOpenAI

from app.config import Settings
from app.schemas.analysis import JobRequirements
from app.schemas.candidate_profile import CandidateProfileData
from app.schemas.scoring import (
    DimensionScore,
    FullAnalysisResult,
    GapAnalysis,
    Recommendation,
    ScoringBreakdown,
)
from app.services.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

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


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, settings: Settings) -> None:
        self.model = settings.openai_model
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

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
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
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
            temperature=0.2,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return FullAnalysisResult.model_validate(data)
