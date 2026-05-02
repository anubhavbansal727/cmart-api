from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    gemini_api_key: str

    # Embeddings
    openai_api_key: str

    # Vector store
    pinecone_api_key: str
    pinecone_index_name: str = "cmart-index"
    pinecone_environment: str = "us-east-1-aws"
    pinecone_vector_dim: int = 1024

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # App
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Retrieval thresholds — tunable without code changes
    rs_strong_threshold: float = 0.82
    rs_moderate_threshold: float = 0.65

    # Session config
    session_ttl_seconds: int = 1800
    max_clarify_rounds: int = 2

    # Rate limiting
    rate_limit_per_minute: int = 100


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance. Safe to call repeatedly."""
    return Settings()  # type: ignore[call-arg]  # pydantic-settings reads fields from env
