from __future__ import annotations

from pathlib import Path

import pytest

from app.models.sandbox import RuntimeEndpoint, SandboxKind, SandboxRecord, SandboxStatus
from app.services.docker_adapter import ContainerCreateResult
from app.services.lifecycle import SandboxLifecycleService
from app.services.registry import registry


@pytest.fixture(autouse=True)
def reset_registry() -> None:
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)
    yield
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)


def _sandbox(root: Path, *, status: SandboxStatus = SandboxStatus.RUNNING) -> SandboxRecord:
    workspace = root / "workspace"
    for path in (workspace / "downloads", workspace / "uploads", workspace / "browser-profile"):
        path.mkdir(parents=True, exist_ok=True)
    return SandboxRecord(
        id="sb_test",
        kind=SandboxKind.XVFB_VNC,
        status=status,
        width=1280,
        height=1024,
        image="custom-runtime:1",
        workspace_dir=workspace,
        downloads_dir=workspace / "downloads",
        uploads_dir=workspace / "uploads",
        browser_profile_dir=workspace / "browser-profile",
        container_id="cid-1" if status != SandboxStatus.STOPPED else None,
        runtime=RuntimeEndpoint(host="10.0.0.9"),
        metadata={"runtime_error": "stale"},
    )


def test_pause_removes_container_and_keeps_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox(tmp_path / "pause-case")
    registry.put(sandbox)
    removed: list[str] = []

    def fake_remove_container(container_id: str) -> None:
        removed.append(container_id)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.remove_container", fake_remove_container)

    assert service.pause("sb_test") is True

    updated = registry.get("sb_test")
    assert updated is not None
    assert removed == ["cid-1"]
    assert updated.status == SandboxStatus.STOPPED
    assert updated.container_id is None
    assert updated.workspace_dir.exists()
    assert "runtime_error" not in updated.metadata


@pytest.mark.asyncio
async def test_resume_recreates_container_for_stopped_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox(tmp_path / "resume-case", status=SandboxStatus.STOPPED)
    registry.put(sandbox)
    create_calls: list[dict[str, object]] = []

    def fake_is_available() -> bool:
        return True

    def fake_create_container(*, sandbox_id: str, kind: SandboxKind, workspace_dir: Path, width: int, height: int, default_url: str | None, image: str | None, enable_gpu: bool = False) -> ContainerCreateResult:
        create_calls.append(
            {
                "sandbox_id": sandbox_id,
                "kind": kind,
                "workspace_dir": workspace_dir,
                "width": width,
                "height": height,
                "default_url": default_url,
                "image": image,
                "enable_gpu": enable_gpu,
            }
        )
        return ContainerCreateResult(container_id="cid-2", host="10.0.0.22")

    async def fake_wait_until_ready(sandbox_id: str, *, timeout_sec: int) -> None:
        current = registry.get(sandbox_id)
        assert current is not None
        current.status = SandboxStatus.RUNNING
        registry.put(current)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.is_available", fake_is_available)
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.image_exists", lambda image_name: True)
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.create_container", fake_create_container)
    monkeypatch.setattr(service, "_wait_until_ready", fake_wait_until_ready)

    ok = await service.resume("sb_test")

    assert ok is True
    assert create_calls == [
        {
            "sandbox_id": "sb_test",
            "kind": SandboxKind.XVFB_VNC,
            "workspace_dir": sandbox.workspace_dir,
            "width": 1280,
            "height": 1024,
            "default_url": None,
            "image": "custom-runtime:1",
            "enable_gpu": False,
        }
    ]
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.RUNNING
    assert updated.container_id == "cid-2"
    assert updated.runtime.host == "10.0.0.22"


@pytest.mark.asyncio
async def test_resume_marks_failed_when_docker_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox(tmp_path / "resume-fail", status=SandboxStatus.STOPPED)
    registry.put(sandbox)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.is_available", lambda: False)

    ok = await service.resume("sb_test")

    assert ok is False
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.FAILED
    assert updated.metadata["runtime_error"] == "docker daemon unavailable"


@pytest.mark.asyncio
async def test_resume_preserves_failed_state_when_runtime_image_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox(tmp_path / "resume-missing-image", status=SandboxStatus.FAILED)
    registry.put(sandbox)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.is_available", lambda: True)
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.image_exists", lambda image_name: False)

    ok = await service.resume("sb_test")

    assert ok is False
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.FAILED
    assert "is not built locally" in updated.metadata["runtime_error"]


@pytest.mark.asyncio
async def test_resume_persists_docker_run_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox(tmp_path / "resume-run-error", status=SandboxStatus.FAILED)
    registry.put(sandbox)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.is_available", lambda: True)
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.image_exists", lambda image_name: True)
    monkeypatch.setattr(
        "app.services.lifecycle.docker_adapter.create_container",
        lambda **_: ContainerCreateResult(container_id=None, host="127.0.0.1", error="docker: Error response from daemon: network bridge not found"),
    )

    ok = await service.resume("sb_test")

    assert ok is False
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.FAILED
    assert updated.metadata["runtime_error"] == "docker: Error response from daemon: network bridge not found"
