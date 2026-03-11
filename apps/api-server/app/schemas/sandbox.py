from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.sandbox import SandboxStatus


class CreateSandboxRequest(BaseModel):
    image: str | None = None
    default_url: str | None = None
    width: int = Field(default=1280, ge=320, le=7680)
    height: int = Field(default=1024, ge=240, le=4320)
    metadata: dict[str, str] = Field(default_factory=dict)


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
    status: SandboxStatus
    created_at: datetime
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
