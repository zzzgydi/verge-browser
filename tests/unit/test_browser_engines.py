import json
import subprocess

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import _check_container_health, _reconcile_runtime_state, app
from app.models.sandbox import BrowserEngine, SandboxRecord, SandboxStatus
from app.schemas.sandbox import CreateSandboxRequest
from app.services.docker_adapter import ContainerCreateResult, ManagedContainer, docker_adapter
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


@pytest.fixture
def sandbox(tmp_path):
    workspace = tmp_path / "sandboxes/sb_cloak/workspace"
    workspace.mkdir(parents=True)
    item = SandboxRecord(
        id="sb_cloak", browser_engine=BrowserEngine.CLOAKBROWSER, status=SandboxStatus.RUNNING,
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


@pytest.mark.parametrize("payload", [{"kind": "xpra"}, {"enable_gpu": True}, {"image": "arbitrary:latest"}, {"http_proxy": "http://u:p@proxy"}, {"browser_engine": "unknown"}])
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


def test_docker_mounts_cloak_state_outside_workspace(configured, tmp_path, monkeypatch):
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="cid-cloak", stderr="")
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", run)
    monkeypatch.setattr(docker_adapter, "inspect_container_ip", lambda _: "172.18.0.2")
    workspace = tmp_path / "sb_cloak/workspace"
    workspace.mkdir(parents=True)
    result = docker_adapter.create_container(
        sandbox_id="sb_cloak", kind=CreateSandboxRequest().kind, browser_engine=BrowserEngine.CLOAKBROWSER,
        workspace_dir=workspace, width=1280, height=1024, default_url=None, image=None,
    )
    assert result.container_id == "cid-cloak"
    cmd = calls[0]
    assert "BROWSER_ENGINE=cloakbrowser" in cmd
    assert f"type=bind,src={workspace.parent / 'cloak-state'},dst=/root/.cloakbrowser" in cmd
    assert f"type=bind,src={configured.cloak_license_file},dst=/root/.cloakbrowser/license.key,readonly" in cmd
    assert "test-not-a-real-key" not in str(cmd)
    assert "-p" not in cmd
    assert (workspace.parent / "cloak-state").stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
async def test_create_resume_and_recreate_keep_engine(configured, monkeypatch):
    service = SandboxLifecycleService()
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return ContainerCreateResult("cid-cloak", "172.18.0.2")
    async def ready(sandbox_id, **kwargs):
        registry.get(sandbox_id).status = SandboxStatus.RUNNING
    monkeypatch.setattr(docker_adapter, "create_container", create)
    monkeypatch.setattr(service, "_wait_until_ready", ready)
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    monkeypatch.setattr(docker_adapter, "cloak_control", lambda *args: {"stopped": True, "error": None})
    monkeypatch.setattr(docker_adapter, "remove_container", lambda _: True)
    item = await service.create(CreateSandboxRequest(alias="cloak-alias", browser_engine="cloakbrowser"))
    assert service.pause(item.alias)
    assert await service.resume(item.alias)
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: False)
    assert await service.restart_browser(item.alias)
    assert len(calls) == 3
    assert all(call["browser_engine"] == BrowserEngine.CLOAKBROWSER for call in calls)
    assert calls[1]["image"] == configured.cloak_runtime_image


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
