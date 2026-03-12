from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi import Request
from fastapi import WebSocketDisconnect

from app.routes import session
from app.models.sandbox import RuntimeEndpoint, SandboxKind, SandboxRecord, SandboxStatus
from app.schemas.sandbox import CreateSessionTicketRequest
from app.services.session import session_service


def test_create_session_prunes_expired_entries() -> None:
    now = datetime.now(timezone.utc)
    session._sessions["expired"] = {
        "sandbox_id": "sb_old",
        "expires_at": now - timedelta(seconds=1),
    }

    session_id = session._create_session("sb_new")

    assert session_id in session._sessions
    assert "expired" not in session._sessions
    session._sessions.clear()


def test_upstream_ws_url_points_to_session_root() -> None:
    sandbox = SandboxRecord(
        id="sb_test",
        kind=SandboxKind.XPRA,
        status=SandboxStatus.RUNNING,
        workspace_dir=Path("/tmp/sb_test/workspace"),
        downloads_dir=Path("/tmp/sb_test/workspace/downloads"),
        uploads_dir=Path("/tmp/sb_test/workspace/uploads"),
        browser_profile_dir=Path("/tmp/sb_test/workspace/profile"),
        container_id="cid-1",
        runtime=RuntimeEndpoint(host="127.0.0.1", session_port=14500),
        metadata={},
    )
    xvfb_sandbox = SandboxRecord(
        id="sb_vnc",
        kind=SandboxKind.XVFB_VNC,
        status=SandboxStatus.RUNNING,
        workspace_dir=Path("/tmp/sb_vnc/workspace"),
        downloads_dir=Path("/tmp/sb_vnc/workspace/downloads"),
        uploads_dir=Path("/tmp/sb_vnc/workspace/uploads"),
        browser_profile_dir=Path("/tmp/sb_vnc/workspace/profile"),
        container_id="cid-2",
        runtime=RuntimeEndpoint(host="127.0.0.1", session_port=6080, display=":99"),
        metadata={},
    )

    assert session_service.upstream_ws_url(sandbox) == "ws://127.0.0.1:14500/"
    assert session_service.upstream_ws_url(sandbox, "foo=bar") == "ws://127.0.0.1:14500/?foo=bar"
    assert session_service.upstream_ws_url(xvfb_sandbox) == "ws://127.0.0.1:6080/websockify"


@pytest.mark.asyncio
async def test_session_ws_proxy_negotiates_binary_subprotocol(monkeypatch: pytest.MonkeyPatch) -> None:
    sandbox = SandboxRecord(
        id="sb_test",
        kind=SandboxKind.XPRA,
        status=SandboxStatus.RUNNING,
        workspace_dir=Path("/tmp/sb_test/workspace"),
        downloads_dir=Path("/tmp/sb_test/workspace/downloads"),
        uploads_dir=Path("/tmp/sb_test/workspace/uploads"),
        browser_profile_dir=Path("/tmp/sb_test/workspace/profile"),
        container_id="cid-1",
        runtime=RuntimeEndpoint(host="127.0.0.1", session_port=14500),
        metadata={},
    )

    monkeypatch.setattr(session, "require_sandbox", lambda sandbox_id: sandbox)
    monkeypatch.setattr(session, "_validate_session", lambda session_id, sandbox_id: None)
    monkeypatch.setattr("app.routes.session.session_service.upstream_ws_url", lambda sandbox, query: "ws://127.0.0.1:14500/")

    accepted: list[str | None] = []
    connect_kwargs: dict[str, object] = {}

    class FakeWebSocket:
        def __init__(self) -> None:
            self.headers = {"sec-websocket-protocol": "binary"}
            self.cookies = {"sandbox_session": "session-1"}
            self.query_params = {}

        async def accept(self, subprotocol: str | None = None) -> None:
            accepted.append(subprotocol)

        async def receive(self):
            raise WebSocketDisconnect()

        async def close(self, code: int, reason: str | None = None) -> None:
            del code, reason

    class FakeUpstream:
        def __init__(self) -> None:
            self.closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        async def send(self, message):
            del message

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def close(self) -> None:
            self.closed = True

    async def fake_connect(url: str, **kwargs):
        connect_kwargs["url"] = url
        connect_kwargs.update(kwargs)
        return FakeUpstream()

    monkeypatch.setattr("app.routes.session.websockets.connect", fake_connect)

    await session.session_ws_proxy(FakeWebSocket(), "sb_test")

    assert accepted == ["binary"]
    assert connect_kwargs["subprotocols"] == ["binary"]
    assert connect_kwargs["max_size"] is None
    assert connect_kwargs["max_queue"] is None


def test_validate_session_rejects_expired_session() -> None:
    session._sessions["expired"] = {
        "sandbox_id": "sb_1",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    }

    with pytest.raises(HTTPException) as exc:
        session._validate_session("expired", "sb_1")

    assert exc.value.status_code == 401
    assert "expired" not in session._sessions
    session._sessions.clear()


@pytest.mark.asyncio
async def test_session_entry_sets_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "verify_ticket", lambda *args, **kwargs: None)

    async def fake_proxy_http(*args, **kwargs):
        from fastapi import Response
        return Response(content=b"<html></html>", media_type="text/html")

    monkeypatch.setattr("app.routes.session.session_service.proxy_http", fake_proxy_http)
    sandbox = SandboxRecord(
        id="sb_test",
        kind=SandboxKind.XPRA,
        status=SandboxStatus.RUNNING,
        workspace_dir=Path("/tmp/sb_test/workspace"),
        downloads_dir=Path("/tmp/sb_test/workspace/downloads"),
        uploads_dir=Path("/tmp/sb_test/workspace/uploads"),
        browser_profile_dir=Path("/tmp/sb_test/workspace/profile"),
        container_id="cid-1",
        runtime=RuntimeEndpoint(host="127.0.0.1", session_port=14500),
        metadata={},
    )
    response = await session.session_entry(Request({"type": "http", "headers": [], "scheme": "http", "server": ("test", 80), "path": "/"}), "sb_test", ticket="ticket", sandbox=sandbox)

    assert response.status_code == 200
    assert "sandbox_session=" in response.headers["set-cookie"]
    assert "Path=/sandbox/sb_test/session" in response.headers["set-cookie"]
    session._sessions.clear()


@pytest.mark.asyncio
async def test_xvfb_session_entry_redirects_to_novnc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "verify_ticket", lambda *args, **kwargs: None)
    sandbox = SandboxRecord(
        id="sb_test",
        kind=SandboxKind.XVFB_VNC,
        status=SandboxStatus.RUNNING,
        workspace_dir=Path("/tmp/sb_test/workspace"),
        downloads_dir=Path("/tmp/sb_test/workspace/downloads"),
        uploads_dir=Path("/tmp/sb_test/workspace/uploads"),
        browser_profile_dir=Path("/tmp/sb_test/workspace/profile"),
        container_id="cid-1",
        runtime=RuntimeEndpoint(host="127.0.0.1", session_port=6080, display=":99"),
        metadata={},
    )

    response = await session.session_entry(
        Request({"type": "http", "headers": [], "scheme": "http", "server": ("test", 80), "path": "/"}),
        "sb_test",
        ticket="ticket",
        sandbox=sandbox,
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith("/sandbox/sb_test/session/vnc.html?")
    assert "Path=/sandbox/sb_test/session" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_create_session_ticket_supports_permanent_mode() -> None:
    request = Request({"type": "http", "headers": [], "scheme": "http", "server": ("test", 80), "path": "/"})
    response = await session.create_session_ticket(
        request,
        "sb_test",
        request=CreateSessionTicketRequest(mode="permanent"),
        subject="user-1",
        sandbox=object(),
    )

    payload = response.data
    assert payload is not None
    if isinstance(payload, dict):
        assert payload["mode"] == "permanent"
        assert payload["ttl_sec"] is None
        assert payload["expires_at"] is None
    else:
        assert payload.mode == "permanent"
        assert payload.ttl_sec is None
        assert payload.expires_at is None


@pytest.mark.asyncio
async def test_create_session_ticket_supports_custom_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "get_settings", lambda: type("Settings", (), {"ticket_ttl_sec": 60})())
    request = Request({"type": "http", "headers": [], "scheme": "http", "server": ("test", 80), "path": "/"})

    response = await session.create_session_ticket(
        request,
        "sb_test",
        request=CreateSessionTicketRequest(mode="reusable", ttl_sec=120),
        subject="user-1",
        sandbox=object(),
    )

    payload = response.data
    assert payload is not None
    if isinstance(payload, dict):
        assert payload["mode"] == "reusable"
        assert payload["ttl_sec"] == 120
        assert payload["expires_at"] is not None
    else:
        assert payload.mode == "reusable"
        assert payload.ttl_sec == 120
        assert payload.expires_at is not None


@pytest.mark.asyncio
async def test_proxy_http_rejects_failed_sandbox() -> None:
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

    with pytest.raises(HTTPException):
        await session_service.proxy_http(sandbox)
