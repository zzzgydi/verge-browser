from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.models.sandbox import RuntimeEndpoint, SandboxKind, SandboxRecord, SandboxStatus
from app.schemas.sandbox import CreateSandboxRequest
from app.services.docker_adapter import ContainerCreateResult
from app.services.lifecycle import SandboxLifecycleService
from app.services.registry import registry


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
        runtime=RuntimeEndpoint(),
        metadata={"runtime_error": "stale"},
    )


@pytest.fixture(autouse=True)
def reset_registry() -> None:
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)
    yield
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)


@pytest.mark.asyncio
async def test_restart_browser_waits_for_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox()
    registry.put(sandbox)

    calls: list[tuple[str, int]] = []

    def fake_restart_browser(container_id: str) -> bool:
        assert container_id == "cid-1"
        return True

    async def fake_wait_until_ready(sandbox_id: str, *, timeout_sec: int) -> None:
        calls.append((sandbox_id, timeout_sec))
        current = registry.get(sandbox_id)
        assert current is not None
        current.status = SandboxStatus.RUNNING
        registry.put(current)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.container_exists", lambda container_id: container_id == "cid-1")
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.restart_browser", fake_restart_browser)
    monkeypatch.setattr(service, "_wait_until_ready", fake_wait_until_ready)

    ok = await service.restart_browser("sb_test")

    assert ok is True
    assert calls == [("sb_test", 60)]
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.RUNNING
    assert "runtime_error" not in updated.metadata


@pytest.mark.asyncio
async def test_restart_browser_marks_degraded_when_restart_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox()
    registry.put(sandbox)

    def fake_restart_browser(container_id: str) -> bool:
        assert container_id == "cid-1"
        return False

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.container_exists", lambda container_id: container_id == "cid-1")
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.restart_browser", fake_restart_browser)

    ok = await service.restart_browser("sb_test")

    assert ok is False
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.DEGRADED


@pytest.mark.asyncio
async def test_restart_browser_returns_false_when_readiness_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox()
    registry.put(sandbox)

    def fake_restart_browser(container_id: str) -> bool:
        assert container_id == "cid-1"
        return True

    async def fake_wait_until_ready(sandbox_id: str, *, timeout_sec: int) -> None:
        current = registry.get(sandbox_id)
        assert current is not None
        current.status = SandboxStatus.DEGRADED
        current.metadata["runtime_error"] = "sandbox readiness timed out"
        registry.put(current)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.container_exists", lambda container_id: container_id == "cid-1")
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.restart_browser", fake_restart_browser)
    monkeypatch.setattr(service, "_wait_until_ready", fake_wait_until_ready)

    ok = await service.restart_browser("sb_test")

    assert ok is False
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.DEGRADED
    registry.delete("sb_test")


@pytest.mark.asyncio
async def test_wait_until_ready_records_generic_readiness_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox()
    registry.put(sandbox)

    async def fake_browser_version(current):
        del current
        return {"webSocketDebuggerUrl": "ws://127.0.0.1:9223/devtools/browser/1"}

    monkeypatch.setattr("app.services.lifecycle.browser_service.browser_version", fake_browser_version)
    monkeypatch.setattr(
        "app.services.lifecycle.browser_service.get_viewport",
        lambda current: {"window_viewport": {"width": 1280}},
    )
    monkeypatch.setattr(service, "_display_ready", lambda current: False)
    monkeypatch.setattr(service, "_session_ready", lambda current: True)

    await service._wait_until_ready("sb_test", timeout_sec=0)

    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.status == SandboxStatus.DEGRADED
    assert updated.metadata["display_error"] == "display unavailable"
    assert "session_error" not in updated.metadata
    assert "xpra_error" not in updated.metadata


@pytest.mark.asyncio
async def test_restart_browser_recreates_container_after_removing_stale_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SandboxLifecycleService()
    sandbox = _sandbox()
    registry.put(sandbox)

    removed: list[str] = []

    async def fake_wait_until_ready(sandbox_id: str, *, timeout_sec: int) -> None:
        current = registry.get(sandbox_id)
        assert current is not None
        current.status = SandboxStatus.RUNNING
        registry.put(current)

    monkeypatch.setattr("app.services.lifecycle.docker_adapter.container_exists", lambda container_id: False)
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.is_available", lambda: True)
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.remove_container", removed.append)
    monkeypatch.setattr(
        "app.services.lifecycle.docker_adapter.create_container",
        lambda **_: ContainerCreateResult(container_id="cid-2", host="10.0.0.2"),
    )
    monkeypatch.setattr(service, "_wait_until_ready", fake_wait_until_ready)

    ok = await service.restart_browser("sb_test")

    assert ok is True
    assert removed == ["cid-1"]
    updated = registry.get("sb_test")
    assert updated is not None
    assert updated.container_id == "cid-2"
    assert updated.runtime.host == "10.0.0.2"
    assert updated.status == SandboxStatus.RUNNING


@pytest.mark.asyncio
async def test_create_xpra_schedules_background_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SandboxLifecycleService()
    scheduled: list[tuple[str, int]] = []

    monkeypatch.setenv("VERGE_SANDBOX_BASE_DIR", str(tmp_path / "sandboxes"))
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.is_available", lambda: True)
    monkeypatch.setattr("app.services.lifecycle.docker_adapter.image_exists", lambda image_name: True)
    monkeypatch.setattr(
        "app.services.lifecycle.docker_adapter.create_container",
        lambda **_: ContainerCreateResult(container_id="cid-xpra", host="10.0.0.10"),
    )
    monkeypatch.setattr(
        service,
        "_schedule_readiness_probe",
        lambda sandbox_id, *, timeout_sec: scheduled.append((sandbox_id, timeout_sec)),
    )

    async def fail_wait_until_ready(*args, **kwargs):
        raise AssertionError("xpra create should not wait inline for readiness")

    monkeypatch.setattr(service, "_wait_until_ready", fail_wait_until_ready)

    try:
        created = await service.create(CreateSandboxRequest(kind=SandboxKind.XPRA))
    finally:
        get_settings.cache_clear()

    assert created.status == SandboxStatus.STARTING
    assert created.container_id == "cid-xpra"
    assert len(scheduled) == 1
    assert scheduled[0][0] == created.id
    assert scheduled[0][1] == 60
