from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "verge-browser"
    env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    sandbox_base_dir: Path = Field(default=Path(".local/sandboxes"))
    workspace_subdir: str = "workspace"
    downloads_subdir: str = "downloads"
    uploads_subdir: str = "uploads"
    browser_profile_subdir: str = "browser-profile"

    sandbox_runtime_image: str = "verge-browser-runtime:latest"
    sandbox_runtime_network: str = "bridge"
    sandbox_runtime_mode: str = "docker"
    sandbox_default_url: str = "https://github.com/zzzgydi/verge-browser"
    sandbox_default_width: int = 1280
    sandbox_default_height: int = 1024

    jwt_secret: str = "dev-secret"
    jwt_algorithm: str = "HS256"
    ticket_secret: str = "ticket-secret"
    ticket_ttl_sec: int = 60
    shell_exec_timeout_sec: int = 30
    shell_exec_output_limit: int = 1024 * 1024
    file_upload_limit_bytes: int = 100 * 1024 * 1024
    sandbox_start_timeout_sec: int = 30

    model_config = SettingsConfigDict(
        env_prefix="VERGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if self.env == "development":
            return self
        if self.jwt_secret == "dev-secret" or len(self.jwt_secret) < 32:
            raise ValueError("VERGE_JWT_SECRET must be set to a non-default value with at least 32 characters outside development")
        if self.ticket_secret == "ticket-secret" or len(self.ticket_secret) < 32:
            raise ValueError("VERGE_TICKET_SECRET must be set to a non-default value with at least 32 characters outside development")
        return self


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.sandbox_base_dir.mkdir(parents=True, exist_ok=True)
    return settings
