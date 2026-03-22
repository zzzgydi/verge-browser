from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.models.sandbox import RuntimeEndpoint, SandboxRecord, SandboxStatus
from app.services.browser import BrowserService


def _sandbox() -> SandboxRecord:
    root = Path("test-artifacts") / "verge-browser"
    return SandboxRecord(
        id="sb_test",
        status=SandboxStatus.RUNNING,
        workspace_dir=root / "workspace",
        downloads_dir=root / "workspace" / "downloads",
        uploads_dir=root / "workspace" / "uploads",
        browser_profile_dir=root / "workspace" / "browser-profile",
        container_id="cid-1",
        runtime=RuntimeEndpoint(host="10.0.0.8", cdp_port=9223, display=":100"),
        metadata={},
    )


@pytest.mark.asyncio
async def test_upstream_browser_version_normalizes_exec_fallback_websocket_url(monkeypatch: pytest.MonkeyPatch) -> None:
    service = BrowserService()
    sandbox = _sandbox()

    async def fake_get(*args, **kwargs):
        del args, kwargs
        request = httpx.Request("GET", "http://10.0.0.8:9223/json/version")
        response = httpx.Response(502, request=request)
        raise httpx.HTTPStatusError("502", request=request, response=response)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        get = fake_get

    monkeypatch.setattr("app.services.browser.httpx.AsyncClient", lambda timeout=2.0: FakeClient())
    monkeypatch.setattr(
        service,
        "_browser_version_via_exec",
        lambda current: {
            "Browser": "Chromium",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/fallback-id",
        },
    )

    payload = await service.upstream_browser_version(sandbox)

    assert payload["Browser"] == "Chromium"
    assert payload["webSocketDebuggerUrl"] == "ws://10.0.0.8:9223/devtools/browser/fallback-id"
