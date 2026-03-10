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


class RuntimeEndpoint(BaseModel):
    host: str = "127.0.0.1"
    cdp_port: int = 9223
    vnc_port: int = 6080
    display: str = ":99"
    browser_port: int = 5900


class SandboxRecord(BaseModel):
    id: str
    status: SandboxStatus
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    workspace_dir: Path
    downloads_dir: Path
    uploads_dir: Path
    browser_profile_dir: Path
    container_id: str | None = None
    runtime: RuntimeEndpoint = Field(default_factory=RuntimeEndpoint)
    metadata: dict[str, Any] = Field(default_factory=dict)
