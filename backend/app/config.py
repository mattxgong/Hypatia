"""Application configuration via Pydantic Settings.

Values are read from environment variables prefixed with ``HYPATIA_`` or from
a ``.env`` file in the working directory (e.g. ``HYPATIA_DATA_DIR``,
``HYPATIA_LLM_PROVIDER``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HYPATIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".hypatia" / "data")
    logs_dir: Path = Field(default_factory=lambda: Path.home() / ".hypatia" / "logs")
    log_level: str = "INFO"

    llm_provider: str = "copilot"
    llm_model: str | None = None
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.3
    copilot_model: str = "gpt-5.4"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    github_token: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    whisper_model_size: str = "base"

    max_upload_size_bytes: int = 3 * 1024 * 1024 * 1024  # 3GB, per Task 2.9


settings = Settings()
