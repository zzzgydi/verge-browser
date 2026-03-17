from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.models.sandbox import RuntimeEndpoint, SandboxKind, SandboxRecord, SandboxStatus
from app.services.clipboard import ClipboardError, ClipboardService


def _sandbox() -> SandboxRecord:
    root = Path("test-artifacts") / "verge-browser"
    return SandboxRecord(
        id="sb_test",
        kind=SandboxKind.XVFB_VNC,
        status=SandboxStatus.RUNNING,
        workspace_dir=root / "workspace",
        downloads_dir=root / "workspace" / "downloads",
        uploads_dir=root / "workspace" / "uploads",
        browser_profile_dir=root / "workspace" / "browser-profile",
        container_id="cid-1",
        runtime=RuntimeEndpoint(host="127.0.0.1", cdp_port=9223, session_port=6080, display=":99"),
        metadata={},
    )


@pytest.mark.asyncio
async def test_read_clipboard_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ClipboardService()
    sandbox = _sandbox()

    monkeypatch.setattr(
        "app.services.clipboard.docker_adapter.exec_shell",
        lambda container_id, script: subprocess.CompletedProcess(
            args=["docker", "exec", container_id],
            returncode=0,
            stdout='{"status":"ok","stdout":"hello"}\n',
            stderr="",
        ),
    )

    assert await service.read_text(sandbox) == "hello"


@pytest.mark.asyncio
async def test_read_clipboard_maps_display_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ClipboardService()
    sandbox = _sandbox()

    monkeypatch.setattr(
        "app.services.clipboard.docker_adapter.exec_shell",
        lambda container_id, script: subprocess.CompletedProcess(
            args=["docker", "exec", container_id],
            returncode=1,
            stdout="",
            stderr="DISPLAY_UNAVAILABLE\n",
        ),
    )

    with pytest.raises(ClipboardError) as exc:
        await service.read_text(sandbox)

    assert exc.value.status_code == 409
    assert exc.value.code == "display_unavailable"


@pytest.mark.asyncio
async def test_write_clipboard_rejects_large_payload() -> None:
    service = ClipboardService()
    sandbox = _sandbox()

    with pytest.raises(ClipboardError) as exc:
        await service.write_text(sandbox, "x" * ((64 * 1024) + 1))

    assert exc.value.status_code == 413
    assert exc.value.code == "payload_too_large"
