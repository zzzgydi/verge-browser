from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.main import app
from app.models.sandbox import RuntimeEndpoint, SandboxKind, SandboxRecord, SandboxStatus
from app.services.docker_adapter import ManagedContainer
from app.services.registry import SandboxRegistry, registry

AUTH_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def body(response):
    return response.json()["data"]


@pytest.fixture(autouse=True)
def reset_registry_and_settings() -> None:
    get_settings.cache_clear()
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)
    yield
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)
    get_settings.cache_clear()


def test_registry_persists_metadata_and_recovers_stopped_sandbox(tmp_path: Path) -> None:
    base_dir = tmp_path / "sandboxes"
    workspace_dir = base_dir / "sb_saved" / "workspace"
    sandbox = SandboxRecord(
        id="sb_saved",
        alias="saved",
        kind=SandboxKind.XVFB_VNC,
        status=SandboxStatus.RUNNING,
        created_at="2026-03-11T00:00:00+00:00",
        updated_at="2026-03-11T01:00:00+00:00",
        last_active_at="2026-03-11T01:00:00+00:00",
        width=1440,
        height=900,
        image="custom-runtime:1",
        workspace_dir=workspace_dir,
        downloads_dir=workspace_dir / "downloads",
        uploads_dir=workspace_dir / "uploads",
        browser_profile_dir=workspace_dir / "browser-profile",
        container_id="cid-live",
        runtime=RuntimeEndpoint(host="10.0.0.5"),
        metadata={"tag": "persisted"},
    )

    registry.put(sandbox)

    meta_file = base_dir / "sb_saved" / "meta.json"
    assert meta_file.exists()
    payload = json.loads(meta_file.read_text())
    assert "workspace_dir" not in payload
    assert payload["alias"] == "saved"
    assert payload["kind"] == "xvfb_vnc"
    assert payload["image"] == "custom-runtime:1"

    restored = SandboxRegistry()
    restored.load_from_disk(
        base_dir,
        workspace_subdir="workspace",
        downloads_subdir="downloads",
        uploads_subdir="uploads",
        browser_profile_subdir="browser-profile",
    )

    recovered = restored.get("sb_saved")
    assert recovered is not None
    assert recovered.status == SandboxStatus.STOPPED
    assert recovered.container_id is None
    assert recovered.alias == "saved"
    assert recovered.kind == SandboxKind.XVFB_VNC
    assert recovered.image == "custom-runtime:1"
    assert recovered.workspace_dir == workspace_dir
    assert recovered.downloads_dir == workspace_dir / "downloads"
    assert recovered.runtime.host == "127.0.0.1"


def test_app_startup_recovers_sandbox_from_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = tmp_path / "sandboxes"
    sandbox_dir = base_dir / "sb_boot"
    sandbox_dir.mkdir(parents=True)
    (sandbox_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": "sb_boot",
                "alias": "boot",
                "created_at": "2026-03-11T00:00:00+00:00",
                "updated_at": "2026-03-11T00:05:00+00:00",
                "last_active_at": "2026-03-11T00:05:00+00:00",
                "kind": "xpra",
                "status": "RUNNING",
                "width": 1280,
                "height": 720,
                "image": None,
                "runtime": {"host": "10.0.0.8", "cdp_port": 9223, "session_port": 14500, "display": ":100", "browser_debug_port": 9222},
                "metadata": {"restored": "yes"},
            }
        )
    )
    monkeypatch.setenv("VERGE_SANDBOX_BASE_DIR", str(base_dir))
    monkeypatch.setattr("app.main.docker_adapter.list_managed_container_refs", lambda: [])
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/sandbox/sb_boot", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert body(response)["id"] == "sb_boot"
    assert body(response)["status"] == "STOPPED"


def test_app_startup_reconciles_running_runtime_container(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = tmp_path / "sandboxes"
    sandbox_dir = base_dir / "sb_keep"
    sandbox_dir.mkdir(parents=True)
    (sandbox_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": "sb_keep",
                "alias": "keep",
                "created_at": "2026-03-11T00:00:00+00:00",
                "updated_at": "2026-03-11T00:05:00+00:00",
                "last_active_at": "2026-03-11T00:05:00+00:00",
                "kind": "xpra",
                "status": "RUNNING",
                "width": 1280,
                "height": 720,
                "image": None,
                "runtime": {"host": "10.0.0.8", "cdp_port": 9223, "session_port": 14500, "display": ":100", "browser_debug_port": 9222},
                "metadata": {"runtime_error": "stale"},
            }
        )
    )
    monkeypatch.setenv("VERGE_SANDBOX_BASE_DIR", str(base_dir))
    monkeypatch.setattr(
        "app.main.docker_adapter.list_managed_container_refs",
        lambda: [ManagedContainer(container_id="cid-running", sandbox_id="sb_keep")],
    )
    monkeypatch.setattr("app.main.docker_adapter.container_exists", lambda container_id: container_id == "cid-running")
    monkeypatch.setattr("app.main.docker_adapter.inspect_container_ip", lambda container_id: "172.18.0.10")

    async def fake_browser_version(sandbox):
        del sandbox
        return {"Browser": "Chromium", "Protocol-Version": "1.3"}

    monkeypatch.setattr("app.routes.sandboxes.browser_service.browser_version", fake_browser_version)
    monkeypatch.setattr(
        "app.routes.sandboxes.browser_service.get_viewport",
        lambda sandbox: {
            "window_viewport": {"x": 0, "y": 0, "width": sandbox.width, "height": sandbox.height},
            "page_viewport": {"x": 0, "y": 80, "width": sandbox.width, "height": max(sandbox.height - 80, 0)},
            "active_window": {"window_id": "1", "x": 0, "y": 0, "title": "Chromium"},
        },
    )
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/sandbox/sb_keep", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = body(response)
    assert payload["status"] == "RUNNING"
    assert payload["container_id"] == "cid-running"
    assert "runtime_error" not in payload["metadata"]


def test_app_startup_removes_orphaned_and_stale_runtime_containers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_dir = tmp_path / "sandboxes"
    sandbox_dir = base_dir / "sb_keep"
    sandbox_dir.mkdir(parents=True)
    (sandbox_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": "sb_keep",
                "alias": "keep",
                "created_at": "2026-03-11T00:00:00+00:00",
                "updated_at": "2026-03-11T00:05:00+00:00",
                "last_active_at": "2026-03-11T00:05:00+00:00",
                "kind": "xvfb_vnc",
                "status": "RUNNING",
                "width": 1280,
                "height": 720,
                "image": None,
                "runtime": {"host": "10.0.0.8", "cdp_port": 9223, "session_port": 14500, "display": ":100", "browser_debug_port": 9222},
                "metadata": {},
            }
        )
    )
    removed: list[str] = []
    monkeypatch.setenv("VERGE_SANDBOX_BASE_DIR", str(base_dir))
    monkeypatch.setattr(
        "app.main.docker_adapter.list_managed_container_refs",
        lambda: [
            ManagedContainer(container_id="cid-known-stopped", sandbox_id="sb_keep"),
            ManagedContainer(container_id="cid-destroyed", sandbox_id="sb_gone"),
            ManagedContainer(container_id="cid-unlabeled", sandbox_id=None),
        ],
    )
    monkeypatch.setattr("app.main.docker_adapter.container_exists", lambda container_id: False)
    monkeypatch.setattr("app.main.docker_adapter.remove_container", removed.append)
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/sandbox/sb_keep", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert body(response)["status"] == "STOPPED"
    assert removed == ["cid-known-stopped", "cid-destroyed", "cid-unlabeled"]
