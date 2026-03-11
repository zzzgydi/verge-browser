from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routes import vnc
from app.models.sandbox import RuntimeEndpoint, SandboxRecord, SandboxStatus
from app.schemas.sandbox import CreateVncTicketRequest


def test_create_vnc_session_prunes_expired_entries() -> None:
    now = datetime.now(timezone.utc)
    vnc._vnc_sessions["expired"] = {
        "sandbox_id": "sb_old",
        "expires_at": now - timedelta(seconds=1),
    }

    session_id = vnc._create_vnc_session("sb_new")

    assert session_id in vnc._vnc_sessions
    assert "expired" not in vnc._vnc_sessions
    vnc._vnc_sessions.clear()


def test_validate_vnc_session_rejects_expired_session() -> None:
    vnc._vnc_sessions["expired"] = {
        "sandbox_id": "sb_1",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    }

    with pytest.raises(HTTPException) as exc:
        vnc._validate_vnc_session("expired", "sb_1")

    assert exc.value.status_code == 401
    assert "expired" not in vnc._vnc_sessions
    vnc._vnc_sessions.clear()


@pytest.mark.asyncio
async def test_vnc_entry_enables_autoconnect_and_scaling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vnc, "verify_ticket", lambda *args, **kwargs: None)

    response = await vnc.vnc_entry("sb_test", ticket="ticket", sandbox=object())

    assert response.status_code == 302
    assert response.headers["location"] == "/sandboxes/sb_test/vnc/vnc.html?path=/sandboxes/sb_test/vnc/websockify&resize=scale&autoconnect=true"
    assert "vnc_session=" in response.headers["set-cookie"]
    vnc._vnc_sessions.clear()


@pytest.mark.asyncio
async def test_create_vnc_ticket_supports_permanent_mode() -> None:
    response = await vnc.create_vnc_ticket(
        "sb_test",
        request=CreateVncTicketRequest(mode="permanent"),
        subject="user-1",
        sandbox=object(),
    )

    assert response.mode == "permanent"
    assert response.ttl_sec is None
    assert response.expires_at is None


@pytest.mark.asyncio
async def test_create_vnc_ticket_supports_custom_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vnc, "get_settings", lambda: type("Settings", (), {"ticket_ttl_sec": 60})())

    response = await vnc.create_vnc_ticket(
        "sb_test",
        request=CreateVncTicketRequest(mode="reusable", ttl_sec=120),
        subject="user-1",
        sandbox=object(),
    )

    assert response.mode == "reusable"
    assert response.ttl_sec == 120
    assert response.expires_at is not None


def test_ensure_vnc_proxy_ready_rejects_failed_sandbox_with_runtime_error() -> None:
    sandbox = SandboxRecord(
        id="sb_failed",
        status=SandboxStatus.FAILED,
        workspace_dir=Path("/tmp/sb_failed/workspace"),
        downloads_dir=Path("/tmp/sb_failed/workspace/downloads"),
        uploads_dir=Path("/tmp/sb_failed/workspace/uploads"),
        browser_profile_dir=Path("/tmp/sb_failed/workspace/profile"),
        container_id=None,
        runtime=RuntimeEndpoint(host="127.0.0.1"),
        metadata={"runtime_error": "docker daemon unavailable"},
    )

    with pytest.raises(HTTPException) as exc:
        vnc._ensure_vnc_proxy_ready(sandbox)

    assert exc.value.status_code == 409
    assert exc.value.detail == "vnc unavailable: docker daemon unavailable"
