"""
Central application configuration.

Design decisions:
- Pydantic v2 `BaseSettings` gives us validated, typed configuration loaded
  from environment variables / .env file, instead of scattering `os.getenv`
  calls (and their silent typos) across the codebase.
- Exposed as a process-wide singleton via `get_settings()` (cached with
  `functools.lru_cache`) so every layer (database, spiders, exporters,
  logger) reads the exact same configuration object without re-parsing
  the environment on every access. This is the "Config Singleton"
  requirement from the architecture spec.
- Settings is intentionally the ONLY module allowed to read environment
  variables. No other module in the codebase should call `os.getenv`
  directly — this keeps configuration concerns in a single place
  (Separation of Concerns).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Strongly-typed application settings, sourced from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_env: str = Field(default="development")
    app_name: str = Field(default="Iran Job Intelligence Platform")
    debug: bool = Field(default=False)

    # --- Database ---
    database_url: str = Field(
        ...,
        description="Async SQLAlchemy connection string (postgresql+asyncpg://...)",
    )
    database_url_sync: str = Field(
        ...,
        description="Sync SQLAlchemy connection string, used by Alembic migrations.",
    )
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=20, ge=0)
    db_echo: bool = Field(default=False)

    # --- Crawling ---
    playwright_headless: bool = Field(default=True)
    playwright_timeout_ms: int = Field(default=30_000, ge=1_000)
    request_delay_seconds: float = Field(default=2.0, ge=0.0)
    max_retries: int = Field(default=3, ge=0)
    retry_backoff_seconds: float = Field(default=5.0, ge=0.0)
    max_concurrent_spiders: int = Field(
        default=2,
        ge=1,
        description=(
            "Reserved for when multiple SITES (jobvision + jobinja + ...) "
            "run concurrently in one process — not yet wired up anywhere, "
            "since only one site is implemented so far. Not to be confused "
            "with max_concurrent_requests, which IS active today (concurrent "
            "page fetches within a single site's crawl)."
        ),
    )
    max_concurrent_requests: int = Field(
        default=5,
        ge=1,
        description=(
            "How many job/company detail pages the crawler is allowed to "
            "fetch at the same time (separate browser tabs in the same "
            "browser). Previously every page was fetched one at a time; "
            "raising this is the main lever for crawl speed. Keep it "
            "moderate (5-8) to avoid tripping the target site's rate "
            "limiting / bot detection."
        ),
    )

    # --- Logging ---
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="logs")
    log_rotation: str = Field(default="10 MB")
    log_retention: str = Field(default="14 days")

    # --- Output ---
    output_json_dir: str = Field(default="output/json")
    output_excel_dir: str = Field(default="output/excel")

    @field_validator("database_url")
    @classmethod
    def _must_be_postgres_async(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the 'postgresql+asyncpg://' driver. "
                "SQLite and other engines are not supported by this platform."
            )
        return value

    @field_validator("database_url_sync")
    @classmethod
    def _must_be_postgres_sync(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg2://"):
            raise ValueError(
                "DATABASE_URL_SYNC must use the 'postgresql+psycopg2://' driver "
                "(required by Alembic's synchronous migration runner)."
            )
        return value

    @property
    def log_dir_path(self) -> Path:
        path = BASE_DIR / self.log_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def output_json_path(self) -> Path:
        path = BASE_DIR / self.output_json_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def output_excel_path(self) -> Path:
        path = BASE_DIR / self.output_excel_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    `lru_cache(maxsize=1)` guarantees the `.env` file is parsed and validated
    exactly once per process, and every caller receives the same instance.
    """
    return Settings()
