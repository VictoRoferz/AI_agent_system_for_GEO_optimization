"""Application settings, loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Model provider keys (role #1 analysis brain)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    default_model: str = "claude-default"

    # Live-query mode (role #2 real engines)
    perplexity_api_key: str = ""
    serpapi_api_key: str = ""

    # Peec AI mode
    peec_api_key: str = ""
    peec_base_url: str = "https://api.peec.ai"

    # App
    knowledge_base_dir: str = "../Knowledge_base"
    database_url: str = "sqlite+aiosqlite:///./geo_assistant.db"
    cors_origins: str = "http://localhost:3000"
    enable_playwright: bool = True

    # Optimization agent
    agent_default_depth: str = "quick"  # quick | full
    agent_max_concurrency: int = 4

    @property
    def kb_path(self) -> Path:
        p = Path(self.knowledge_base_dir)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
