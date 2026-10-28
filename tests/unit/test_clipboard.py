from __future__ import annotations

import os
import subprocess
import sys
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
        lambda container_id, script, **kwargs: subprocess.CompletedProcess(
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
        lambda container_id, script, **kwargs: subprocess.CompletedProcess(
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


def test_write_command_returns_while_clipboard_owner_is_alive(tmp_path: Path) -> None:
    release_owner = tmp_path / "release-owner"
    xclip = tmp_path / "xclip"
    xclip.write_text(
        f"#!{sys.executable}\n"
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "sys.stdin.read()\n"
        "if os.fork():\n"
        "    os._exit(0)\n"
        "deadline = time.monotonic() + 5\n"
        f"while not Path({str(release_owner)!r}).exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
        "os._exit(0)\n"
    )
    xclip.chmod(0o755)
    command = ClipboardService()._write_command(_sandbox(), "synthetic clipboard text")
    code = command.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=2)
        assert proc.returncode == 0, stderr
        assert '"status": "ok"' in stdout
        assert not release_owner.exists()
    finally:
        release_owner.touch()
        proc.communicate(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["read", "write"])
async def test_clipboard_exec_timeout_is_structured(monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    def exec_shell(container_id, script, *, timeout):
        assert timeout == 10
        raise subprocess.TimeoutExpired("synthetic command", timeout)

    monkeypatch.setattr("app.services.clipboard.docker_adapter.exec_shell", exec_shell)
    service = ClipboardService()
    with pytest.raises(ClipboardError) as exc:
        if action == "read":
            await service.read_text(_sandbox())
        else:
            await service.write_text(_sandbox(), "synthetic text")
    assert exc.value.status_code == 502
    assert exc.value.code == "clipboard_timeout"


def test_write_command_preserves_display_errors(tmp_path: Path) -> None:
    xclip = tmp_path / "xclip"
    xclip.write_text("#!/bin/sh\necho \"Error: Can't open display: :99\" >&2\nexit 1\n")
    xclip.chmod(0o755)
    command = ClipboardService()._write_command(_sandbox(), "synthetic text")
    code = command.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True, text=True, timeout=2,
    )
    with pytest.raises(ClipboardError) as exc:
        ClipboardService()._parse_exec_payload(proc)
    assert exc.value.code == "display_unavailable"
