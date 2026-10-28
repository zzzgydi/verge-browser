from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.sandbox import BrowserEngine, SandboxKind, SandboxStatus


class CreateSandboxRequest(BaseModel):
    alias: str | None = Field(default=None, min_length=1, max_length=63)
    kind: SandboxKind = SandboxKind.XVFB_VNC
    browser_engine: BrowserEngine = BrowserEngine.CHROMIUM
    image: str | None = None
    default_url: str | None = None
    width: int = Field(default=1280, ge=320, le=7680)
    height: int = Field(default=1024, ge=240, le=4320)
    enable_gpu: bool = False
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_engine(self) -> "CreateSandboxRequest":
        if self.browser_engine == BrowserEngine.CLOAKBROWSER:
            if self.enable_gpu:
                raise ValueError("CloakBrowser currently requires GPU disabled")
            if self.image is not None:
                raise ValueError("Configure the CloakBrowser image on the server, not per sandbox")
            if any("@" in value for value in (self.http_proxy or "", self.https_proxy or "")):
                raise ValueError("Authenticated proxies are not supported for CloakBrowser yet")
        return self


class BrowserEngineAvailability(BaseModel):
    browser_engine: BrowserEngine
    available: bool
    reason: str | None = None
    kinds: list[SandboxKind]


class UpdateSandboxRequest(BaseModel):
    alias: str | None = Field(default=None, min_length=1, max_length=63)
    metadata: dict[str, Any] | None = None


class ViewportInfo(BaseModel):
    width: int
    height: int


class BrowserViewportRect(BaseModel):
    x: int
    y: int
    width: int
    height: int


class ActiveWindowInfo(BaseModel):
    window_id: str | None = None
    x: int
    y: int
    title: str


class BrowserRuntimeInfo(BaseModel):
    browser_version: str | None = None
    protocol_version: str | None = None
    web_socket_debugger_url_present: bool = False
    viewport: ViewportInfo
    window_viewport: BrowserViewportRect | None = None
    page_viewport: BrowserViewportRect | None = None
    active_window: ActiveWindowInfo | None = None


class SandboxResponse(BaseModel):
    id: str
    alias: str | None = None
    kind: SandboxKind
    browser_engine: BrowserEngine = BrowserEngine.CHROMIUM
    status: SandboxStatus
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime
    width: int
    height: int
    enable_gpu: bool = False
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    browser: BrowserRuntimeInfo
    container_id: str | None = None


class RestartBrowserRequest(BaseModel):
    level: Literal["hard"] = "hard"


class CreateSessionTicketRequest(BaseModel):
    mode: Literal["one_time", "reusable", "permanent"] = "one_time"
    ttl_sec: int | None = Field(default=None, ge=1, le=86400)


class CreateSessionTicketResponse(BaseModel):
    ticket: str
    session_url: str
    mode: Literal["one_time", "reusable", "permanent"]
    ttl_sec: int | None
    expires_at: datetime | None


class CreateCdpTicketRequest(BaseModel):
    mode: Literal["one_time", "reusable", "permanent"] = "reusable"
    ttl_sec: int | None = Field(default=None, ge=1, le=86400)


class CreateCdpTicketResponse(BaseModel):
    ticket: str
    cdp_url: str
    mode: Literal["one_time", "reusable", "permanent"]
    ttl_sec: int | None
    expires_at: datetime | None
