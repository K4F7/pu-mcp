from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pu_mcp.mcp_launch import SESSION_FALLBACK_DIRNAME


def default_data_dir() -> Path:
    path = Path.home() / SESSION_FALLBACK_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PU_", env_file=".env", extra="ignore")

    base_url: str = Field("https://apis.pocketuni.net", alias="PU_BASE_URL")
    db_path: Path = Field(
        default_factory=lambda: default_data_dir() / "pu.sqlite", alias="PU_DB_PATH"
    )
    request_timeout_seconds: float = Field(10, alias="PU_REQUEST_TIMEOUT_SECONDS")
    min_request_interval_seconds: float = Field(2, alias="PU_MIN_REQUEST_INTERVAL_SECONDS")
    max_retries: int = Field(2, alias="PU_MAX_RETRIES")
    activity_cache_ttl_seconds: float = Field(300, alias="PU_ACTIVITY_CACHE_TTL_SECONDS")
    max_signup_attempts: int = Field(3, alias="PU_MAX_SIGNUP_ATTEMPTS")
    web_host: str = Field("127.0.0.1", alias="PU_WEB_HOST")
    web_port: int = Field(8000, alias="PU_WEB_PORT")
