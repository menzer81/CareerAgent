from app.services.requirement_extraction_service import heuristic_extract_requirements
from app.services.resume_strategy_service import select_persona

text = """Director of AI Enablement

We are seeking a strategic and execution-focused Director of AI Enablement to lead the adoption of AI-driven workflows across the organization. This role is responsible for identifying high-impact opportunities, designing scalable solutions, and embedding agentic AI capabilities into core business processes. As a key leader in technology, you will partner with functional leaders to transform how work gets done through intelligent automation, AI agents, and modern workflow design. You will also build and lead a high-impact team focused on AI workflow design and implementation.

AI Strategy & Business Transformation:
Define and execute the organization’s AI Enablement strategy.
Build and manage a pipeline of AI initiatives.
Ensure responsible and secure use of AI, including governance, compliance, and risk management practices.

Education And Experience
8+ years of experience in technology, digital transformation, automation, or AI-related roles.
Strong understanding of AI/ML concepts, particularly LLMs, automation, and workflow orchestration.
"""
req = heuristic_extract_requirements(text)
print('ai_requirements=', req.ai_requirements)
print('important_keywords=', req.important_keywords)
print('director_level_or_above=', req.director_level_or_above)
print('manager_of_managers_required=', req.manager_of_managers_required)
print('persona=', select_persona(req))
