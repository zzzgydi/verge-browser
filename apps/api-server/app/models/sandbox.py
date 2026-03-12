from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SandboxStatus(StrEnum):
    CREATING = "CREATING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class SandboxKind(StrEnum):
    XVFB_VNC = "xvfb_vnc"
    XPRA = "xpra"


class RuntimeEndpoint(BaseModel):
    host: str = "127.0.0.1"
    cdp_port: int = 9223
    session_port: int = 6080
    display: str = ":99"
    browser_debug_port: int = 9222


def runtime_endpoint_for_kind(kind: SandboxKind) -> RuntimeEndpoint:
    if kind == SandboxKind.XPRA:
        return RuntimeEndpoint(session_port=14500, display=":100")
    return RuntimeEndpoint(session_port=6080, display=":99")


class SandboxRecord(BaseModel):
    id: str
    alias: str | None = None
    kind: SandboxKind = SandboxKind.XVFB_VNC
    status: SandboxStatus
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_active_at: datetime = Field(default_factory=utcnow)
    width: int = 1280
    height: int = 1024
    image: str | None = None
    workspace_dir: Path
    downloads_dir: Path
    uploads_dir: Path
    browser_profile_dir: Path
    container_id: str | None = None
    runtime: RuntimeEndpoint = Field(default_factory=RuntimeEndpoint)
    metadata: dict[str, Any] = Field(default_factory=dict)
