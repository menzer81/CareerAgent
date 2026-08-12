from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_title: str = "CareerAgent"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite+aiosqlite:///./career_agent.db"

    # OpenAI-compatible LLM
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # Optional dual-provider setup
    llm_routing_mode: str = "single"  # single | local_first | cloud_first
    local_openai_api_key: str = ""
    local_openai_base_url: str = ""
    local_openai_model: str = ""
    cloud_openai_api_key: str = ""
    cloud_openai_base_url: str = "https://api.openai.com/v1"
    cloud_openai_model: str = "gpt-5-mini"
    llm_extract_timeout_seconds: int = Field(default=75, ge=1)
    llm_scoring_timeout_seconds: int = Field(default=90, ge=1)

    # Reports output directory
    reports_dir: Path = Path("./reports")

    # Accomplishment/story bank used by the Achievement Selection Engine
    accomplishments_file: Path = Path("./data/accomplishments.json")

    # Reactive Resume hosted rendering
    reactive_resume_api_key: str = ""
    reactive_resume_base_url: str = "https://rxresu.me/api/openapi"
    reactive_resume_template: str = "onyx"
    reactive_resume_page_format: str = "letter"

    def llm_configured(self) -> bool:
        """Return True if LLM credentials are available."""
        return bool(
            self.openai_api_key
            or self.local_llm_configured()
            or self.cloud_llm_configured()
        )

    def local_llm_configured(self) -> bool:
        return bool(self.local_openai_base_url and self.local_openai_model)

    def cloud_llm_configured(self) -> bool:
        return bool(self.cloud_openai_api_key and self.cloud_openai_model)

    def reactive_resume_configured(self) -> bool:
        return bool(self.reactive_resume_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
