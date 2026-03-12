from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.sandbox import SandboxKind


class Settings(BaseSettings):
    app_name: str = "verge-browser"
    env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    sandbox_base_dir: Path = Field(default=Path(".local/sandboxes"))
    admin_static_dir: Path = Field(default=Path(__file__).resolve().parent / "static" / "admin")
    workspace_subdir: str = "workspace"
    downloads_subdir: str = "downloads"
    uploads_subdir: str = "uploads"
    browser_profile_subdir: str = "browser-profile"

    sandbox_default_kind: SandboxKind = SandboxKind.XVFB_VNC
    sandbox_runtime_image: str = "verge-browser-runtime-xvfb:latest"
    sandbox_runtime_image_xvfb_vnc: str = "verge-browser-runtime-xvfb:latest"
    sandbox_runtime_image_xpra: str = "verge-browser-runtime-xpra:latest"
    sandbox_runtime_network: str = "bridge"
    sandbox_runtime_mode: str = "docker"
    sandbox_default_url: str = "https://github.com/zzzgydi/verge-browser"
    sandbox_default_width: int = 1280
    sandbox_default_height: int = 1024
    sandbox_session_port: int = 6080
    sandbox_session_port_xvfb_vnc: int = 6080
    sandbox_session_port_xpra: int = 14500
    sandbox_display: str = ":99"
    sandbox_display_xvfb_vnc: str = ":99"
    sandbox_display_xpra: str = ":100"
    sandbox_default_session_path: str = "/"

    admin_auth_token: str = "dev-admin-token"
    ticket_secret: str = "ticket-secret"
    ticket_ttl_sec: int = 60
    file_upload_limit_bytes: int = 100 * 1024 * 1024
    sandbox_start_timeout_sec: int = 60

    model_config = SettingsConfigDict(
        env_prefix="VERGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if not self.admin_auth_token:
            raise ValueError("VERGE_ADMIN_AUTH_TOKEN must be set")
        if self.env == "development":
            return self
        if self.admin_auth_token == "dev-admin-token" or len(self.admin_auth_token) < 16:
            raise ValueError("VERGE_ADMIN_AUTH_TOKEN must be set to a non-default value outside development")
        if self.ticket_secret == "ticket-secret" or len(self.ticket_secret) < 32:
            raise ValueError("VERGE_TICKET_SECRET must be set to a non-default value with at least 32 characters outside development")
        return self

    def runtime_image_for_kind(self, kind: SandboxKind) -> str:
        if kind == SandboxKind.XPRA:
            return self.sandbox_runtime_image_xpra
        return self.sandbox_runtime_image_xvfb_vnc

    def session_port_for_kind(self, kind: SandboxKind) -> int:
        if kind == SandboxKind.XPRA:
            return self.sandbox_session_port_xpra
        return self.sandbox_session_port_xvfb_vnc

    def display_for_kind(self, kind: SandboxKind) -> str:
        if kind == SandboxKind.XPRA:
            return self.sandbox_display_xpra
        return self.sandbox_display_xvfb_vnc


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.sandbox_base_dir.mkdir(parents=True, exist_ok=True)
    return settings
