"""Application settings, loaded from the environment (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ - resolved from this file so the app starts from any working
# directory (uvicorn --app-dir, Railway, a test runner).
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str
    anthropic_api_key: str = ""
    allowed_origins: str = "http://localhost:5173"

    # "anthropic" for the demo, "ollama" for free local iteration. The five
    # agents are identical either way - only the backend call differs.
    llm_provider: str = "anthropic"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_base_url: str = "http://127.0.0.1:11434"

    @property
    def sqlalchemy_url(self) -> str:
        """DATABASE_URL rewritten for SQLAlchemy's psycopg 3 driver.

        Railway hands out `postgresql://...` (and some tooling still emits the
        legacy `postgres://`), both of which SQLAlchemy resolves to psycopg2.
        We install psycopg 3, so the driver has to be named explicitly.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
