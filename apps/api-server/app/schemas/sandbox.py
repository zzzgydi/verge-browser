from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.sandbox import SandboxKind, SandboxStatus


class CreateSandboxRequest(BaseModel):
    alias: str | None = Field(default=None, min_length=1, max_length=63)
    kind: SandboxKind = SandboxKind.XVFB_VNC
    image: str | None = None
    default_url: str | None = None
    width: int = Field(default=1280, ge=320, le=7680)
    height: int = Field(default=1024, ge=240, le=4320)
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    status: SandboxStatus
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime
    width: int
    height: int
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
