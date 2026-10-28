import asyncio
import json
import subprocess

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import _check_container_health, _reconcile_runtime_state, app
from app.models.sandbox import BrowserEngine, SandboxKind, SandboxRecord, SandboxStatus
from app.schemas.sandbox import CreateSandboxRequest
from app.services.docker_adapter import ContainerCreateResult, DockerAdapter, ManagedContainer, docker_adapter
from app.services.engines import cloak_unavailable_reason
from app.services.lifecycle import SandboxLifecycleService, lifecycle_service
from app.services.registry import SandboxRegistry, registry


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("VERGE_SANDBOX_BASE_DIR", str(tmp_path / "sandboxes"))
    monkeypatch.setenv("VERGE_CLOAK_ENABLED", "false")
    monkeypatch.setattr(docker_adapter, "is_available", lambda: True)
    monkeypatch.setattr(docker_adapter, "image_exists", lambda _: True)
    monkeypatch.setattr(docker_adapter, "cloak_image_supported", lambda name: docker_adapter.image_exists(name))
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)
    yield
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)
    get_settings.cache_clear()


@pytest.fixture
def configured(tmp_path):
    settings = get_settings()
    settings.cloak_enabled = True
    settings.cloak_license_file = tmp_path / "private/key"
    settings.cloak_license_file.parent.mkdir()
    settings.cloak_license_file.write_text("test-not-a-real-key")
    settings.cloak_binary_dir = tmp_path / "binaries"
    settings.cloak_binary_dir.mkdir()
    (settings.cloak_binary_dir / "current.json").write_text('{}')
    return settings


@pytest.fixture(params=list(SandboxKind))
def sandbox(tmp_path, request):
    workspace = tmp_path / "sandboxes/sb_cloak/workspace"
    workspace.mkdir(parents=True)
    item = SandboxRecord(
        id="sb_cloak", kind=request.param, browser_engine=BrowserEngine.CLOAKBROWSER, status=SandboxStatus.RUNNING,
        image="pinned-runtime:1", workspace_dir=workspace, downloads_dir=workspace / "downloads",
        uploads_dir=workspace / "uploads", browser_profile_dir=workspace / "browser-profile", container_id="cid-cloak",
    )
    registry.put(item)
    return item


def test_engine_discovery_requires_auth_and_never_returns_key(configured):
    client = TestClient(app)
    assert client.get("/runtime/engines").status_code == 401
    response = client.get("/runtime/engines", headers={"Authorization": "Bearer dev-admin-token"})
    assert response.status_code == 200
    assert response.json()["data"][1]["available"] is True
    assert response.json()["data"][1]["kinds"] == [kind.value for kind in SandboxKind]
    assert "test-not-a-real-key" not in response.text
    assert str(configured.cloak_license_file) not in response.text


def test_engine_discovery_does_not_shadow_sandbox_alias(sandbox):
    sandbox.alias = "engines"
    sandbox.status = SandboxStatus.STOPPED
    sandbox.container_id = None
    registry.put(sandbox)
    response = TestClient(app).get("/sandbox/engines", headers={"Authorization": "Bearer dev-admin-token"})
    assert response.json()["data"]["id"] == sandbox.id


def test_private_cloak_state_is_not_accessible_through_files(sandbox):
    private = sandbox.workspace_dir.parent / "cloak-state"
    private.mkdir()
    (private / "license.key").write_text("test-not-a-real-key")
    response = TestClient(app, raise_server_exceptions=False).get(
        f"/sandbox/{sandbox.id}/files/read", params={"path": "/workspace/../cloak-state/license.key"},
        headers={"Authorization": "Bearer dev-admin-token"},
    )
    assert response.status_code == 500  # The existing file API rejects escapes with ValueError.
    assert "path escapes workspace" in response.text
    assert "test-not-a-real-key" not in response.text


def test_missing_cloak_configuration_does_not_block_chromium(monkeypatch):
    monkeypatch.setattr(docker_adapter, "is_available", lambda: False)
    client = TestClient(app)
    headers = {"Authorization": "Bearer dev-admin-token"}
    assert client.post("/sandbox", json={"browser_engine": "cloakbrowser"}, headers=headers).status_code == 409
    response = client.post("/sandbox", json={}, headers=headers)
    assert response.status_code == 201
    assert response.json()["data"]["browser_engine"] == "chromium"


@pytest.mark.parametrize("payload", [{"enable_gpu": True}, {"image": "arbitrary:latest"}, {"http_proxy": "http://u:p@proxy"}, {"browser_engine": "unknown"}])
def test_unsupported_engine_combinations_fail_before_creation(payload):
    client = TestClient(app)
    response = client.post("/sandbox", json={"browser_engine": "cloakbrowser", **payload}, headers={"Authorization": "Bearer dev-admin-token"})
    assert response.status_code == 422
    assert not tuple(registry.all())


def test_config_readiness_detects_missing_key_binary_and_image(configured, monkeypatch):
    assert cloak_unavailable_reason() is None
    configured.cloak_license_file.write_text("")
    assert "key file" in cloak_unavailable_reason()
    configured.cloak_license_file.write_text("test-not-a-real-key")
    (configured.cloak_binary_dir / "current.json").unlink()
    assert "Install" in cloak_unavailable_reason()
    (configured.cloak_binary_dir / "current.json").write_text('{}')
    monkeypatch.setattr(docker_adapter, "image_exists", lambda _: False)
    assert "image" in cloak_unavailable_reason()


@pytest.mark.parametrize("kind", list(SandboxKind))
def test_docker_mounts_cloak_state_outside_workspace(configured, tmp_path, monkeypatch, kind):
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="cid-cloak", stderr="")
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", run)
    monkeypatch.setattr(docker_adapter, "inspect_container_ip", lambda _: "172.18.0.2")
    workspace = tmp_path / "sb_cloak/workspace"
    workspace.mkdir(parents=True)
    result = docker_adapter.create_container(
        sandbox_id="sb_cloak", kind=kind, browser_engine=BrowserEngine.CLOAKBROWSER,
        workspace_dir=workspace, width=1280, height=1024, default_url=None, image=None,
    )
    assert result.container_id == "cid-cloak"
    cmd = calls[0]
    assert "BROWSER_ENGINE=cloakbrowser" in cmd
    assert cmd[-1] == configured.cloak_runtime_image_for_kind(kind)
    assert "--platform" in cmd and "linux/amd64" in cmd
    assert f"DISPLAY={configured.display_for_kind(kind)}" in cmd
    if kind == SandboxKind.XPRA:
        assert "XPRA_PORT=14500" in cmd
        assert "XPRA_DISPLAY=:100" in cmd
        assert not any(value.startswith("WEBSOCKET_PROXY_PORT=") for value in cmd)
    assert f"type=bind,src={workspace.parent / 'cloak-state'},dst=/root/.cloakbrowser" in cmd
    assert f"type=bind,src={configured.cloak_license_file},dst=/root/.cloakbrowser/license.key,readonly" in cmd
    assert "test-not-a-real-key" not in str(cmd)
    assert "-p" not in cmd
    assert (workspace.parent / "cloak-state").stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(SandboxKind))
async def test_create_resume_and_recreate_keep_engine(configured, monkeypatch, kind):
    service = SandboxLifecycleService()
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return ContainerCreateResult("cid-cloak", "172.18.0.2")
    async def ready(sandbox_id, **kwargs):
        registry.get(sandbox_id).status = SandboxStatus.RUNNING
    monkeypatch.setattr(docker_adapter, "create_container", create)
    monkeypatch.setattr(service, "_wait_until_ready", ready)
    monkeypatch.setattr(service, "_schedule_readiness_probe", lambda *args, **kwargs: None)
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    monkeypatch.setattr(docker_adapter, "cloak_control", lambda *args: {"stopped": True, "error": None})
    monkeypatch.setattr(docker_adapter, "remove_container", lambda _: True)
    item = await service.create(CreateSandboxRequest(alias="cloak-alias", kind=kind, browser_engine="cloakbrowser"))
    image = configured.cloak_runtime_image_for_kind(kind)
    assert item.image == image
    assert item.runtime.display == configured.display_for_kind(kind)
    assert item.runtime.session_port == configured.session_port_for_kind(kind)
    # Existing profiles keep their selected runtime even after defaults change.
    configured.cloak_runtime_image = "new-xvfb:latest"
    configured.cloak_runtime_image_xpra = "new-xpra:latest"
    monkeypatch.setattr(docker_adapter, "image_exists", lambda name: name == image)
    assert service.pause(item.alias)
    assert await service.resume(item.alias)
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: False)
    assert await service.restart_browser(item.alias)
    assert len(calls) == 3
    assert all(call["browser_engine"] == BrowserEngine.CLOAKBROWSER for call in calls)
    assert all(call["kind"] == kind for call in calls)
    assert all(call["image"] == image for call in calls[1:])


@pytest.mark.parametrize("available_kind", list(SandboxKind))
def test_discovery_and_creation_check_only_selected_runtime(configured, monkeypatch, available_kind):
    monkeypatch.setattr(docker_adapter, "cloak_image_supported", DockerAdapter().cloak_image_supported)
    def inspect(cmd, **kwargs):
        assert cmd[:3] == ["docker", "image", "inspect"]
        labels = {
            "io.verge.browser.launcher-version": "1",
            "io.verge.browser.experimental-engines": "cloakbrowser-linux-amd64",
        } if cmd[3] == configured.cloak_runtime_image_for_kind(available_kind) else None
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(labels), stderr="")
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", inspect)
    headers = {"Authorization": "Bearer dev-admin-token"}
    client = TestClient(app)
    engine = client.get("/runtime/engines", headers=headers).json()["data"][1]
    assert engine["available"] is True
    assert engine["kinds"] == [available_kind.value]
    assert cloak_unavailable_reason(available_kind) is None
    missing_kind = next(kind for kind in SandboxKind if kind != available_kind)
    response = client.post("/sandbox", headers=headers, json={"browser_engine": "cloakbrowser", "kind": missing_kind.value})
    assert response.status_code == 409
    assert missing_kind.value in response.json()["message"]
    assert not tuple(registry.all())


def test_discovery_has_no_available_kinds_without_cloak_configuration():
    response = TestClient(app).get("/runtime/engines", headers={"Authorization": "Bearer dev-admin-token"})
    engine = response.json()["data"][1]
    assert engine["available"] is False
    assert engine["kinds"] == []


@pytest.mark.parametrize("kind", list(SandboxKind))
def test_legacy_image_is_rejected_before_creating_cloak_profile(configured, monkeypatch, kind):
    monkeypatch.setattr(docker_adapter, "cloak_image_supported", DockerAdapter().cloak_image_supported)
    def inspect(cmd, **kwargs):
        assert cmd[:3] == ["docker", "image", "inspect"]
        return subprocess.CompletedProcess(cmd, 0, stdout="null", stderr="")
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", inspect)
    headers = {"Authorization": "Bearer dev-admin-token"}
    client = TestClient(app)
    engine = client.get("/runtime/engines", headers=headers).json()["data"][1]
    assert engine["available"] is False and engine["kinds"] == []
    response = client.post("/sandbox", headers=headers, json={"browser_engine": "cloakbrowser", "kind": kind.value})
    assert response.status_code == 409 and "rebuild" in response.json()["message"]
    assert not tuple(registry.all())
    assert not list(configured.sandbox_base_dir.glob("sb_*"))


def test_api_creates_cloak_xpra_with_background_readiness(configured, monkeypatch):
    calls, scheduled = [], []
    def create(**kwargs):
        calls.append(kwargs)
        return ContainerCreateResult("cid-xpra-cloak", "172.18.0.2")
    async def no_version(*args):
        return {}
    def no_viewport(*args):
        raise RuntimeError("starting")
    monkeypatch.setattr(docker_adapter, "create_container", create)
    monkeypatch.setattr(lifecycle_service, "_schedule_readiness_probe", lambda sid, **kwargs: scheduled.append(sid))
    monkeypatch.setattr("app.routes.sandboxes.browser_service.browser_version", no_version)
    monkeypatch.setattr("app.routes.sandboxes.browser_service.get_viewport", no_viewport)
    response = TestClient(app).post(
        "/sandbox", headers={"Authorization": "Bearer dev-admin-token"},
        json={"kind": "xpra", "browser_engine": "cloakbrowser"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "STARTING" and data["kind"] == "xpra"
    assert data["browser_engine"] == "cloakbrowser"
    assert calls[0]["kind"] == SandboxKind.XPRA
    assert scheduled == [data["id"]]
    assert registry.get(data["id"]).image == configured.cloak_runtime_image_xpra


@pytest.mark.parametrize("operation", ["pause", "destroy"])
def test_failed_stop_preserves_container_and_data(sandbox, monkeypatch, operation):
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    monkeypatch.setattr(docker_adapter, "cloak_control", lambda *args: {"error": {"code": "CONTROL_UNAVAILABLE"}})
    def unexpected(*args):
        pytest.fail("must not remove a browser whose stop was unconfirmed")
    monkeypatch.setattr(docker_adapter, "remove_container", unexpected)
    with pytest.raises(HTTPException, match="409"):
        getattr(SandboxLifecycleService(), operation)(sandbox.id)
    assert registry.get(sandbox.id).container_id == "cid-cloak"
    assert sandbox.workspace_dir.exists()


def test_already_denied_browser_can_be_paused(sandbox, monkeypatch):
    events = []
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    def control(*args):
        events.append("close")
        return {"stopped": True, "error": {"code": "SESSION_LIMIT", "message": "seat busy"}}
    def remove(*args):
        events.append("remove")
        return True
    monkeypatch.setattr(docker_adapter, "cloak_control", control)
    monkeypatch.setattr(docker_adapter, "remove_container", remove)
    assert SandboxLifecycleService().pause(sandbox.id)
    assert events == ["close", "remove"]
    assert sandbox.status == SandboxStatus.STOPPED


def test_removal_failure_preserves_record_and_profile(sandbox, monkeypatch):
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: False)
    monkeypatch.setattr(docker_adapter, "remove_container", lambda _: False)
    with pytest.raises(HTTPException, match="409"):
        SandboxLifecycleService().destroy(sandbox.id)
    assert registry.get(sandbox.id) is sandbox
    assert sandbox.workspace_dir.exists()


def test_control_nonzero_exit_without_error_is_not_success(monkeypatch):
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess([], 1, stdout='{"stopped":true,"error":null}'))
    result = docker_adapter.cloak_control("cid", "stop")
    assert result["error"]["code"] == "CONTROL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_license_denial_never_becomes_ready(sandbox, monkeypatch):
    monkeypatch.setattr(docker_adapter, "cloak_control", lambda *args: {"error": {"code": "SESSION_LIMIT", "message": "seat busy"}})
    await SandboxLifecycleService()._wait_until_ready(sandbox.id, timeout_sec=1)
    assert sandbox.status == SandboxStatus.DEGRADED
    assert "SESSION_LIMIT" in sandbox.metadata["runtime_error"]


def test_health_detects_dead_browser_inside_live_container(sandbox, monkeypatch):
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    monkeypatch.setattr(docker_adapter, "cloak_control", lambda *args: {"process_state": "EXITED", "error": None})
    _check_container_health()
    assert sandbox.status == SandboxStatus.DEGRADED


def test_reconciliation_requires_fresh_cloak_readiness(sandbox, monkeypatch):
    monkeypatch.setattr(docker_adapter, "list_managed_container_refs", lambda: [ManagedContainer("cid-cloak", sandbox.id)])
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    monkeypatch.setattr(docker_adapter, "inspect_container_ip", lambda _: "172.18.0.2")
    _reconcile_runtime_state()
    assert sandbox.status == SandboxStatus.STARTING


def test_engine_persistence_and_legacy_default(sandbox):
    sandbox.http_proxy = "http://proxy:80"
    registry.put(sandbox)
    base = sandbox.workspace_dir.parent.parent
    restored = SandboxRegistry()
    kwargs = dict(workspace_subdir="workspace", downloads_subdir="downloads", uploads_subdir="uploads", browser_profile_subdir="browser-profile")
    restored.load_from_disk(base, **kwargs)
    assert restored.get(sandbox.id).browser_engine == BrowserEngine.CLOAKBROWSER
    assert restored.get(sandbox.id).http_proxy == "http://proxy:80"
    meta = sandbox.workspace_dir.parent / "meta.json"
    payload = json.loads(meta.read_text())
    del payload["browser_engine"]
    meta.write_text(json.dumps(payload))
    restored.load_from_disk(base, **kwargs)
    assert restored.get(sandbox.id).browser_engine == BrowserEngine.CHROMIUM


def test_response_preserves_engine_and_gpu(sandbox, monkeypatch):
    sandbox.status = SandboxStatus.STOPPED
    sandbox.container_id = None
    sandbox.enable_gpu = True
    response = TestClient(app).get(f"/sandbox/{sandbox.id}", headers={"Authorization": "Bearer dev-admin-token"})
    data = response.json()["data"]
    assert data["browser_engine"] == "cloakbrowser"
    assert data["enable_gpu"] is True


@pytest.mark.asyncio
async def test_restart_cloak_closes_before_start(sandbox, configured, monkeypatch):
    events = []
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    def control(*args):
        events.append("close")
        return {"stopped": True, "error": None}
    def start(*args):
        events.append("start")
        return True
    async def ready(sandbox_id, **kwargs):
        registry.get(sandbox_id).status = SandboxStatus.RUNNING
    monkeypatch.setattr(docker_adapter, "cloak_control", control)
    monkeypatch.setattr(docker_adapter, "start_cloak_browser", start)
    monkeypatch.setattr(lifecycle_service, "_wait_until_ready", ready)
    assert await lifecycle_service.restart_browser(sandbox.id)
    assert events == ["close", "start"]


@pytest.mark.asyncio
async def test_background_readiness_exception_preserves_runtime_and_persists_error(sandbox, monkeypatch):
    sandbox.status = SandboxStatus.STARTING
    sandbox.browser_profile_dir.mkdir()
    profile_file = sandbox.browser_profile_dir / "test-profile"
    profile_file.write_text("preserved")
    registry.put(sandbox)
    before = sandbox.updated_at
    service = SandboxLifecycleService()
    async def fail(*args, **kwargs):
        raise RuntimeError("synthetic-sensitive-upstream-detail")
    monkeypatch.setattr(service, "_wait_until_ready", fail)
    service._schedule_readiness_probe(sandbox.id, timeout_sec=1)
    await service._readiness_tasks[sandbox.id]
    await asyncio.sleep(0)
    assert sandbox.status == SandboxStatus.DEGRADED
    assert sandbox.updated_at >= before
    assert sandbox.container_id == "cid-cloak" and sandbox.workspace_dir.exists()
    assert profile_file.read_text() == "preserved"
    assert "background readiness failed" in sandbox.metadata["runtime_error"]
    assert "sensitive" not in sandbox.metadata["runtime_error"]
    saved = json.loads((sandbox.workspace_dir.parent / "meta.json").read_text())
    assert saved["status"] == "DEGRADED"
    assert saved["metadata"]["runtime_error"] == sandbox.metadata["runtime_error"]
    assert sandbox.id not in service._readiness_tasks


@pytest.mark.asyncio
async def test_background_readiness_cancellation_does_not_mark_failed(sandbox, monkeypatch):
    sandbox.status = SandboxStatus.STARTING
    registry.put(sandbox)
    service = SandboxLifecycleService()
    started = asyncio.Event()
    async def wait(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(service, "_wait_until_ready", wait)
    service._schedule_readiness_probe(sandbox.id, timeout_sec=1)
    task = service._readiness_tasks[sandbox.id]
    await started.wait()
    service._cancel_readiness_task(sandbox.id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sandbox.status == SandboxStatus.STARTING
    assert "runtime_error" not in sandbox.metadata
    assert sandbox.id not in service._readiness_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("later_state", ["deleted", "stopped", "degraded"])
async def test_background_readiness_exception_does_not_overwrite_later_state(sandbox, monkeypatch, later_state):
    sandbox.status = SandboxStatus.STARTING
    service = SandboxLifecycleService()
    async def fail(*args, **kwargs):
        if later_state == "deleted":
            registry.delete(sandbox.id)
        else:
            sandbox.status = SandboxStatus.STOPPED if later_state == "stopped" else SandboxStatus.DEGRADED
            sandbox.metadata["runtime_error"] = "existing diagnostic"
            registry.put(sandbox)
        raise RuntimeError("late failure")
    monkeypatch.setattr(service, "_wait_until_ready", fail)
    service._schedule_readiness_probe(sandbox.id, timeout_sec=1)
    await service._readiness_tasks[sandbox.id]
    if later_state == "deleted":
        assert registry.get(sandbox.id) is None
    else:
        assert sandbox.metadata["runtime_error"] == "existing diagnostic"
        assert sandbox.status == (SandboxStatus.STOPPED if later_state == "stopped" else SandboxStatus.DEGRADED)
