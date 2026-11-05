from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: SecretStr | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_api_base_url: str = "https://api.github.com"
    github_api_version: str = "2022-11-28"
    github_timeout_seconds: float = Field(default=15.0, gt=0)
    github_max_files: int = Field(default=1000, ge=1, le=10_000)
    github_max_pages: int = Field(default=20, ge=1, le=100)
    groq_api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = Field(default=30.0, gt=0)
    groq_max_retries: int = Field(default=2, ge=0, le=5)
    groq_retry_base_seconds: float = Field(default=1.0, ge=0)
    groq_retry_max_seconds: float = Field(default=8.0, ge=0)
    groq_retry_after_max_seconds: float = Field(default=60.0, ge=0, le=300)
    groq_max_output_tokens: int = Field(default=2048, ge=256, le=8192)
    groq_reasoning_effort: str | None = "low"
    ai_max_tool_calls: int = Field(default=12, ge=1, le=100)
    ai_max_iterations: int = Field(default=8, ge=1, le=50)
    ai_max_tool_result_chars: int = Field(default=12_000, ge=1000, le=100_000)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

