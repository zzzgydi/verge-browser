from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.sandbox import SandboxStatus


class CreateSandboxRequest(BaseModel):
    alias: str | None = Field(default=None, min_length=1, max_length=63)
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


class BrowserInfo(BaseModel):
    cdp_url: str
    vnc_entry_base_url: str
    vnc_ticket_endpoint: str
    browser_version: str | None = None
    protocol_version: str | None = None
    viewport: ViewportInfo


class SandboxResponse(BaseModel):
    id: str
    alias: str | None = None
    status: SandboxStatus
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime
    width: int
    height: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    browser: BrowserInfo
    container_id: str | None = None


class RestartBrowserRequest(BaseModel):
    level: Literal["hard"] = "hard"


class CreateVncTicketRequest(BaseModel):
    mode: Literal["one_time", "reusable", "permanent"] = "one_time"
    ttl_sec: int | None = Field(default=None, ge=1, le=86400)


class CreateVncTicketResponse(BaseModel):
    ticket: str
    mode: Literal["one_time", "reusable", "permanent"]
    ttl_sec: int | None
    expires_at: datetime | None
