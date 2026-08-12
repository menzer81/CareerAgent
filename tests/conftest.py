"""Shared pytest fixtures."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database as app_database
from app.api.deps import get_llm_provider
from app.database import Base, get_db
from app.main import app
from app.schemas.analysis import JobRequirements
from app.schemas.scoring import (
    DimensionScore,
    FullAnalysisResult,
    GapAnalysis,
    Recommendation,
    ScoringBreakdown,
)
from app.services.llm.base import BaseLLMProvider

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def mock_llm() -> BaseLLMProvider:
    """A mock LLM that returns canned responses."""
    provider = MagicMock(spec=BaseLLMProvider)

    provider.extract_job_requirements = AsyncMock(
        return_value=JobRequirements(
            required_skills=["Python", "AWS", "Team Leadership"],
            preferred_skills=["Go", "Kubernetes"],
            manager_of_managers_required=True,
            director_level_or_above=True,
            cloud_requirements=["AWS", "EKS"],
            ai_requirements=["LLM integration"],
            industry_domain=["fintech"],
            years_of_experience_min=8,
            inferred_title="Engineering Director",
            inferred_company="Acme Corp",
            important_keywords=["distributed systems", "platform engineering"],
            role_summary="Lead a large engineering org at a fintech company.",
        )
    )

    async def _select_resume_persona(requirements):
        from app.services.resume_strategy_service import select_persona

        return select_persona(requirements)

    provider.select_resume_persona = AsyncMock(side_effect=_select_resume_persona)

    provider.score_and_analyze = AsyncMock(
        return_value=FullAnalysisResult(
            job_posting_id=1,
            scoring=ScoringBreakdown(
                leadership_match=DimensionScore(
                    score=85.0,
                    explanation="Strong leadership match",
                    matched=["Manager of managers"],
                    missing=[],
                ),
                technical_match=DimensionScore(
                    score=80.0,
                    explanation="Good technical overlap",
                    matched=["Python", "AWS"],
                    missing=["Go"],
                ),
                cloud_match=DimensionScore(
                    score=75.0,
                    explanation="AWS experience matches",
                    matched=["AWS"],
                    missing=["EKS"],
                ),
                ai_match=DimensionScore(
                    score=70.0,
                    explanation="Some AI experience",
                    matched=["LLM integration"],
                    missing=[],
                ),
                management_scope_match=DimensionScore(
                    score=90.0,
                    explanation="Large team management fits",
                    matched=["Org design"],
                    missing=[],
                ),
                industry_match=DimensionScore(
                    score=60.0,
                    explanation="Limited fintech experience",
                    matched=[],
                    missing=["fintech"],
                ),
                overall_score=79.5,
                recommendation=Recommendation.APPLY,
                recommendation_reasoning="Strong overall match with minor gaps in fintech and cloud.",
            ),
            gap_analysis=GapAnalysis(
                missing_experiences=[],
                missing_keywords=["EKS", "Go"],
                missing_certifications=[],
                missing_leadership_signals=[],
                strengths=["Manager of managers experience", "Python", "AWS"],
                risks=["Limited fintech domain experience"],
                resume_focus_areas=["Highlight distributed systems work", "Emphasize cloud leadership"],
            ),
        )
    )

    async def _generate_resume_content(job_posting_id, profile, requirements, strategy, selected_accomplishments):
        from app.schemas.resume import GeneratedResumeContent

        return GeneratedResumeContent(
            job_posting_id=job_posting_id,
            executive_summary=profile.summary,
            experience_bullets=[],
            accomplishment_bullets=[],
            generated_by="static",
        )

    provider.generate_resume_content = AsyncMock(side_effect=_generate_resume_content)
    return provider


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, db_engine, mock_llm: BaseLLMProvider) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with in-memory database."""
    async def override_get_db():
        yield db_session

    async def override_get_llm_provider():
        return mock_llm

    app_database.AsyncSessionLocal = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_provider] = override_get_llm_provider
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# Shared sample data for tests
SAMPLE_PROFILE_DATA = {
    "full_name": "Jane Smith",
    "current_title": "Engineering Director",
    "location": "San Francisco, CA",
    "years_total_experience": 15.0,
    "years_management_experience": 8.0,
    "summary": "Experienced engineering director with strong platform and cloud background.",
    "work_history": [
        {
            "company": "TechCorp",
            "title": "Engineering Director",
            "start_date": "2019-01",
            "end_date": None,
            "is_current": True,
            "description": "Lead platform engineering org of 45 engineers across 4 teams.",
            "team_size": 45,
            "direct_reports": 6,
            "key_accomplishments": ["Reduced deploy time by 70%", "Built SRE practice from scratch"],
            "technologies": ["Python", "AWS", "Kubernetes", "Terraform"],
            "industries": ["SaaS"],
        }
    ],
    "leadership_experience": {
        "largest_team_managed": 45,
        "largest_org_managed": 45,
        "manager_of_managers": True,
        "director_level_or_above": True,
        "executive_level": False,
        "vp_or_above": False,
        "managed_multiple_teams": True,
        "cross_functional_leadership": True,
        "board_presentations": False,
        "p_and_l_responsibility": False,
        "hiring_scale": "Grew team from 12 to 45 in 18 months",
        "leadership_highlights": ["Built high-performing distributed teams"],
    },
    "ai_experience": {
        "worked_with_llms": True,
        "built_ai_products": True,
        "ml_engineering_background": False,
        "ai_product_management": False,
        "rag_systems": True,
        "fine_tuning_experience": False,
        "ai_agents": True,
        "tools_and_frameworks": ["OpenAI API", "LangChain"],
        "ai_highlights": ["Built internal LLM-powered code review tool"],
    },
    "management_experience": {
        "total_years_managing": 8.0,
        "total_years_ic": 7.0,
        "remote_team_management": True,
        "distributed_team_management": True,
        "offshore_team_management": False,
        "agile_practitioner": True,
        "scaled_agile": False,
        "org_design_experience": True,
        "performance_management": True,
        "executive_stakeholder_management": True,
        "management_highlights": ["Reduced attrition from 25% to 8%"],
    },
    "technologies": ["Python", "Go", "AWS", "Kubernetes", "Terraform", "PostgreSQL", "Redis"],
    "cloud_platforms": ["AWS", "GCP"],
    "certifications": [
        {"name": "AWS Solutions Architect - Professional", "issuer": "Amazon", "year": 2022, "is_active": True}
    ],
    "education": [
        {
            "institution": "UC Berkeley",
            "degree": "B.S.",
            "field_of_study": "Computer Science",
            "graduation_year": 2009,
        }
    ],
    "accomplishments": [
        "Led platform migration saving $2M/year in cloud costs",
        "Scaled engineering team 4x in 18 months",
    ],
    "industries": ["SaaS", "DevTools"],
    "career_goals": [
        "VP of Engineering or Engineering Director at a growth-stage company",
        "Technical leadership with significant organizational impact",
    ],
}

SAMPLE_JOB_TEXT = """# Engineering Director — Platform Engineering

Acme Corp is looking for an Engineering Director to lead our platform engineering organization.

## About the Role
You will manage a team of 40+ engineers across 4 teams, responsible for our core developer platform,
infrastructure, and internal tooling. This is a manager-of-managers role with significant org-level
responsibility.

## Requirements
- 8+ years of software engineering experience
- 5+ years of engineering management, including managing managers
- Strong experience with AWS and cloud-native architectures
- Experience with Python and distributed systems
- Director-level leadership skills
- Track record of building high-performing teams

## Preferred Qualifications
- Experience with Kubernetes and container orchestration
- Fintech industry experience
- AI/ML integration experience
- P&L responsibility

## About Acme Corp
Acme Corp is a leading fintech company processing $10B+ in annual transactions.
"""
