"""Rule-based job requirement extraction — fallback when no LLM is configured.

This mirrors the structured output of the LLM-based extractor
(``BaseLLMProvider.extract_job_requirements``) using keyword and regex
heuristics so the full analysis pipeline (``POST /api/v1/analysis/{job_id}``)
can run end-to-end without an ``OPENAI_API_KEY``, as advertised in the README's
"Rule-Based Fallback" feature.

This is intentionally simple/heuristic. Results will generally be less
nuanced than LLM extraction, but should surface the most common signals:
required/preferred skills, cloud & AI requirements, leadership signals,
industry domain, years of experience, and seniority level.
"""

from __future__ import annotations

import re

from app.schemas.analysis import JobRequirements

# Broad vocabulary of skills/technologies to look for in the posting text.
# Order matters only for de-duplication display; matching is case-insensitive.
_SKILL_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang", "C#", ".NET",
    "C++", "Ruby", "PHP", "Rust", "Scala", "Swift", "Kotlin",
    "React", "Angular", "Vue", "Node.js", "Django", "Flask", "FastAPI",
    "Spring", "ASP.NET",
    "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Cassandra", "DynamoDB",
    "Microservices", "REST", "GraphQL", "gRPC", "Distributed Systems",
    "CI/CD", "DevOps", "SRE", "Site Reliability", "Terraform", "Ansible",
    "Docker", "Kubernetes", "Helm",
    "Agile", "Scrum", "Kanban",
    "Data Engineering", "Data Platform", "Data Warehouse", "Streaming",
    "Observability", "Monitoring",
    "Security", "AppSec", "Compliance", "PCI DSS", "SOC 2", "ISO 27001",
    "Networking", "Platform Engineering", "Developer Experience",
    "Budget Management", "Cost Optimization", "Vendor Management",
    "Hiring", "Recruiting", "Performance Management", "Org Design",
]

_CLOUD_KEYWORDS = [
    "AWS", "Amazon Web Services", "Azure", "Microsoft Azure", "GCP",
    "Google Cloud", "Kubernetes", "EKS", "GKE", "AKS", "Docker",
    "Terraform", "Cloud Infrastructure", "Cloud Platform", "Multi-Cloud",
]

_AI_KEYWORDS = [
    "AI", "LLM", "LLMs", "Machine Learning", "ML", "GPT", "OpenAI",
    "Copilot", "RAG", "Generative AI", "AI Agents", "Agentic",
    "Artificial Intelligence", "NLP", "Deep Learning", "AI Tooling",
    "AI/LLM",
]

_INDUSTRY_KEYWORDS = [
    "Fintech", "Healthcare", "SaaS", "Government", "Insurance", "Banking",
    "Payments", "E-commerce", "Retail", "Manufacturing", "Logistics",
    "Education", "EdTech", "Biotech", "Pharma", "Telecom", "Media",
    "Gaming", "Automotive", "Real Estate", "Property Management",
    "Transportation", "Construction", "Compliance", "Cybersecurity",
    "Regulated Industry",
]

_ROLE_LEVEL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bsvp\b|\bsenior vice president\b", re.IGNORECASE), "SVP"),
    (re.compile(r"\bvp\b|\bvice president\b", re.IGNORECASE), "VP"),
    (re.compile(r"\bdirector\b", re.IGNORECASE), "Director"),
    (re.compile(r"\bsenior manager\b", re.IGNORECASE), "Senior Manager"),
    (re.compile(r"\bmanager\b", re.IGNORECASE), "Manager"),
]

_TEAM_SIZE_PATTERN = re.compile(
    r"(\d+)\+?\s*(?:-|\s)?\s*(?:person|people|engineers?|developers?|"
    r"direct reports?|reports?|employees)",
    re.IGNORECASE,
)
_YEARS_EXPERIENCE_PATTERN = re.compile(
    r"(\d+)\+?\s*years?\s*[a-zA-Z\s]{0,40}?(?:experience|management)",
    re.IGNORECASE,
)
_PREFERRED_SECTION_PATTERN = re.compile(
    r"(?:preferred qualifications|nice to have|bonus points|good to have)"
    r"(.*?)(?=\n#{1,3}\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_REQUIRED_SECTION_PATTERN = re.compile(
    r"(?:^|\n)#{0,3}\s*requirements\b(.*?)(?=\n#{1,3}\s|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _find_keywords(text: str, keywords: list[str]) -> list[str]:
    """Return the subset of `keywords` that appear as whole words/phrases in `text`."""
    found: list[str] = []
    for keyword in keywords:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(keyword) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, re.IGNORECASE):
            found.append(keyword)
    return found


def _extract_section(text: str, pattern: re.Pattern) -> str:
    match = pattern.search(text)
    return match.group(1) if match else ""


def _extract_role_level(text: str) -> str | None:
    for pattern, label in _ROLE_LEVEL_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _extract_max_team_size(text: str) -> int | None:
    matches = [int(m) for m in _TEAM_SIZE_PATTERN.findall(text)]
    return max(matches) if matches else None


def _extract_years_experience(text: str) -> int | None:
    matches = [int(m) for m in _YEARS_EXPERIENCE_PATTERN.findall(text)]
    return min(matches) if matches else None


def _extract_role_summary(text: str) -> str:
    """Best-effort one-paragraph summary: first non-heading paragraph of reasonable length."""
    for paragraph in re.split(r"\n\s*\n", text):
        cleaned = " ".join(
            line.strip(" -*#") for line in paragraph.splitlines() if line.strip()
        ).strip()
        if len(cleaned) >= 40:
            return cleaned[:500]
    return ""


def heuristic_extract_requirements(job_text: str) -> JobRequirements:
    """Extract structured requirements from raw job posting text without an LLM.

    Uses keyword and regex heuristics. Less nuanced than LLM-based extraction,
    but sufficient to drive rule-based scoring end-to-end.
    """
    required_section = _extract_section(job_text, _REQUIRED_SECTION_PATTERN) or job_text
    preferred_section = _extract_section(job_text, _PREFERRED_SECTION_PATTERN)

    required_skills = _find_keywords(required_section, _SKILL_KEYWORDS)
    preferred_skills = [
        kw for kw in _find_keywords(preferred_section, _SKILL_KEYWORDS)
        if kw not in required_skills
    ]

    cloud_requirements = _find_keywords(job_text, _CLOUD_KEYWORDS)
    ai_requirements = _find_keywords(job_text, _AI_KEYWORDS)
    industry_domain = _find_keywords(job_text, _INDUSTRY_KEYWORDS)

    manager_of_managers_required = bool(
        re.search(r"manager of managers", job_text, re.IGNORECASE)
    )
    role_level = _extract_role_level(job_text)
    director_level_or_above = role_level in {"Director", "VP", "SVP"}
    p_and_l_responsibility = bool(
        re.search(r"p&l|p and l|profit and loss", job_text, re.IGNORECASE)
    )

    max_team_size = _extract_max_team_size(job_text)
    years_min = _extract_years_experience(job_text)

    is_remote = bool(re.search(r"\bremote\b", job_text, re.IGNORECASE)) or None
    is_hybrid = bool(re.search(r"\bhybrid\b", job_text, re.IGNORECASE)) or None

    important_keywords: list[str] = []
    for kw in required_skills + preferred_skills + cloud_requirements + ai_requirements:
        if kw not in important_keywords:
            important_keywords.append(kw)
    important_keywords = important_keywords[:15]

    return JobRequirements(
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        leadership_requirements=[],
        manager_of_managers_required=manager_of_managers_required,
        director_level_or_above=director_level_or_above,
        min_team_size_managed=max_team_size,
        max_team_size_managed=max_team_size,
        p_and_l_responsibility=p_and_l_responsibility,
        cloud_requirements=cloud_requirements,
        ai_requirements=ai_requirements,
        industry_domain=industry_domain,
        years_of_experience_min=years_min,
        years_of_experience_max=None,
        inferred_title=None,
        inferred_company=None,
        role_level=role_level,
        is_remote=is_remote,
        is_hybrid=is_hybrid,
        important_keywords=important_keywords,
        role_summary=_extract_role_summary(job_text),
    )
