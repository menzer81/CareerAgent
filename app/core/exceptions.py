from fastapi import HTTPException, status


class CareerAgentError(Exception):
    """Base exception for CareerAgent."""


class NotFoundError(CareerAgentError):
    def __init__(self, resource: str, resource_id: int | str) -> None:
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} with id '{resource_id}' not found")


class ProfileNotFoundError(CareerAgentError):
    def __init__(self) -> None:
        super().__init__("Candidate profile has not been created yet")


class LLMNotConfiguredError(CareerAgentError):
    def __init__(self) -> None:
        super().__init__(
            "LLM provider is not configured. Set OPENAI_API_KEY in your environment."
        )


class AnalysisNotFoundError(CareerAgentError):
    def __init__(self, job_id: int) -> None:
        super().__init__(f"No analysis found for job posting {job_id}. Run analysis first.")


def not_found_exception(resource: str, resource_id: int | str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} with id '{resource_id}' not found",
    )
