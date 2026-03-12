from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.models.sandbox import RuntimeEndpoint, SandboxRecord, SandboxStatus
from app.services.browser import BrowserService


def _sandbox(status: SandboxStatus) -> SandboxRecord:
    root = Path("test-artifacts") / "verge-browser"
    return SandboxRecord(
        id="sb_test",
        status=status,
        workspace_dir=root / "workspace",
        downloads_dir=root / "workspace" / "downloads",
        uploads_dir=root / "workspace" / "uploads",
        browser_profile_dir=root / "workspace" / "browser-profile",
        container_id="cid-1",
        runtime=RuntimeEndpoint(host="127.0.0.1", cdp_port=9223, display=":100"),
        metadata={},
    )


@pytest.mark.asyncio
async def test_browser_version_starting_probe_failure_logs_without_traceback(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    service = BrowserService()
    sandbox = _sandbox(SandboxStatus.STARTING)

    async def fake_get(*args, **kwargs):
        del args, kwargs
        request = httpx.Request("GET", "http://127.0.0.1:9223/json/version")
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
    monkeypatch.setattr(service, "_browser_version_via_exec", lambda sandbox: {"Browser": "Chromium"})

    with caplog.at_level("INFO", logger="app.services.browser"):
        payload = await service.browser_version(sandbox)

    assert payload["Browser"] == "Chromium"
    assert "not ready" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.asyncio
async def test_browser_version_running_probe_failure_logs_with_traceback(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    service = BrowserService()
    sandbox = _sandbox(SandboxStatus.RUNNING)

    async def fake_get(*args, **kwargs):
        del args, kwargs
        request = httpx.Request("GET", "http://127.0.0.1:9223/json/version")
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
    monkeypatch.setattr(service, "_browser_version_via_exec", lambda sandbox: {"Browser": "Chromium"})

    with caplog.at_level("WARNING", logger="app.services.browser"):
        payload = await service.browser_version(sandbox)

    assert payload["Browser"] == "Chromium"
    assert "falling back to exec" in caplog.text
    assert "Traceback" in caplog.text
