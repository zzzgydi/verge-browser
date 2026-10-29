from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import httpx
import pytest
from fastapi import HTTPException

from app.models.sandbox import BrowserEngine, RuntimeEndpoint, SandboxKind, SandboxRecord, SandboxStatus
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


@pytest.mark.parametrize("kind", [SandboxKind.XPRA, SandboxKind.XVFB_VNC])
@pytest.mark.parametrize("engine", [BrowserEngine.CHROMIUM, BrowserEngine.CLOAKBROWSER])
def test_window_screenshot_uses_runtime_specific_capture(kind, engine, monkeypatch):
    service = BrowserService()
    sandbox = _sandbox(SandboxStatus.RUNNING)
    sandbox.kind = kind
    sandbox.browser_engine = engine
    monkeypatch.setattr(service, "_discover_window", lambda _: {
        "window_id": "8388611", "width": 1280, "height": 1024, "x": 12, "y": 34,
    })
    commands = []

    def capture(container_id, command, *, text):
        assert container_id == "cid-1" and text is False
        commands.append(command)
        return CompletedProcess([], 0, stdout=b"png-bytes", stderr=b"")

    monkeypatch.setattr("app.services.browser.docker_adapter.exec_shell", capture)
    assert service._window_screenshot(sandbox) == b"png-bytes"
    command = commands[0]
    if kind == SandboxKind.XPRA:
        assert "import -window 8388611 png:-" in command
        assert "-window root" not in command
        assert "Map State: IsViewable" in command
        assert "_XPRA_WID" in command
        assert 'xpra control "$DISPLAY" map "$xpra_wid"' in command
        assert "set -e" in command
    else:
        assert 'import -window root -crop "1280x1024+12+34" png:-' in command
        assert "xpra control" not in command


def test_window_screenshot_reports_capture_failure(monkeypatch):
    service = BrowserService()
    sandbox = _sandbox(SandboxStatus.RUNNING)
    sandbox.kind = SandboxKind.XPRA
    monkeypatch.setattr(service, "_discover_window", lambda _: {
        "window_id": "42", "width": 1280, "height": 1024, "x": 0, "y": 0,
    })
    monkeypatch.setattr("app.services.browser.docker_adapter.exec_shell", lambda *args, **kwargs:
                        CompletedProcess([], 1, stdout=b"", stderr=b"Xpra window ID unavailable"))
    with pytest.raises(HTTPException) as error:
        service._window_screenshot(sandbox)
    assert error.value.status_code == 502
    assert error.value.detail == "window screenshot failed"


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
