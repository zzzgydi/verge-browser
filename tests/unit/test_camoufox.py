import json
import subprocess

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.config import get_settings
from app.main import app
from app.models.sandbox import BrowserEngine, SandboxKind, SandboxRecord, SandboxStatus
from app.schemas.command import BrowserCommand
from app.schemas.sandbox import CreateSandboxRequest
from app.services.docker_adapter import DockerAdapter, docker_adapter
from app.services.engines import browser_engines
from app.services.lifecycle import lifecycle_service
from app.services.registry import registry

AUTH = {"Authorization": "Bearer dev-admin-token"}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "sandbox_base_dir", tmp_path)
    item = SandboxRecord(
        id="sb_camoufox_test",
        kind=SandboxKind.XVFB_VNC,
        browser_engine=BrowserEngine.CAMOUFOX,
        status=SandboxStatus.RUNNING,
        workspace_dir=tmp_path / "workspace",
        downloads_dir=tmp_path / "workspace/downloads",
        uploads_dir=tmp_path / "workspace/uploads",
        browser_profile_dir=tmp_path / "workspace/browser-profile",
        container_id="test-camoufox",
    )
    registry.put(item)
    yield item
    registry.delete(item.id)


@pytest.mark.parametrize(
    "params",
    [
        {"kind": "xpra"},
        {"enable_gpu": True},
        {"image": "other"},
        {"http_proxy": "http://proxy"},
    ],
)
def test_camoufox_rejects_unsupported_configuration(params):
    with pytest.raises(ValidationError):
        CreateSandboxRequest(browser_engine="camoufox", **params)


@pytest.mark.parametrize(
    "params",
    [
        {"action": "close"},
        {"action": "eval"},
        {"action": "open", "url": "file:///etc/passwd"},
        {"action": "open", "url": "about:blank-other"},
        {"action": "click"},
        {"action": "switch", "index": -1},
        {"action": "snapshot", "unexpected": True},
    ],
)
def test_commands_reject_invalid_input(params):
    with pytest.raises(ValidationError):
        BrowserCommand(**params)


def test_fill_allows_empty_text():
    assert BrowserCommand(action="fill", ref="@e1", text="").worker_command()["params"]["text"] == ""


def test_command_auth_engine_and_tab_routing(sandbox, monkeypatch):
    calls = []
    monkeypatch.setattr(docker_adapter, "camoufox_control", lambda cid, cmd: calls.append((cid, cmd)) or {"snapshot": "test"})
    client = TestClient(app)
    path = f"/sandbox/{sandbox.id}/browser/command"
    assert client.post(path, json={"action": "snapshot"}).status_code == 401
    response = client.post(path, json={"action": "snapshot", "tab": "research", "interactive": True}, headers=AUTH)
    assert response.status_code == 200
    assert calls == [(sandbox.container_id, {"action": "snapshot", "tab": "research", "params": {"interactive": True}})]
    sandbox.browser_engine = BrowserEngine.CHROMIUM
    assert client.post(path, json={"action": "snapshot"}, headers=AUTH).status_code == 409
    sandbox.browser_engine = BrowserEngine.CAMOUFOX
    sandbox.status = SandboxStatus.DEGRADED
    assert client.post(path, json={"action": "snapshot"}, headers=AUTH).status_code == 409
    assert len(calls) == 1


def test_camoufox_refuses_cdp(sandbox):
    client = TestClient(app)
    assert client.post(f"/sandbox/{sandbox.id}/cdp/apply", headers=AUTH).status_code == 409
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(f"/sandbox/{sandbox.id}/cdp/browser?ticket=invalid"):
            pass
    assert error.value.code == 4409


@pytest.mark.parametrize("returncode,payload", [(0, {"success": False, "error": "stale ref"}), (1, {"success": True, "data": {}})])
def test_control_never_retries_failures(monkeypatch, returncode, payload):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, returncode, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="not retried"):
        DockerAdapter().camoufox_control("container", {"action": "click", "params": {"ref": "@e1"}})
    assert len(calls) == 1
    assert calls[0][0][:3] == ["docker", "exec", "-i"]


def test_stop_failure_preserves_runtime_and_profile(sandbox, monkeypatch):
    monkeypatch.setattr(docker_adapter, "container_exists", lambda _: True)
    monkeypatch.setattr(docker_adapter, "camoufox_exited", lambda _: False)

    def fail(*args):
        raise RuntimeError("stop timeout")

    monkeypatch.setattr(docker_adapter, "camoufox_control", fail)
    client = TestClient(app)
    assert client.post(f"/sandbox/{sandbox.id}/pause", headers=AUTH).status_code == 409
    assert registry.get(sandbox.id).container_id == "test-camoufox"
    assert sandbox.status == SandboxStatus.DEGRADED


def test_dead_worker_can_be_recovered(sandbox, monkeypatch):
    monkeypatch.setattr(docker_adapter, "camoufox_exited", lambda _: True)
    monkeypatch.setattr(docker_adapter, "camoufox_control", lambda *args: pytest.fail("must not contact exited worker"))
    lifecycle_service._stop_camoufox(sandbox)


def test_disabled_engine_has_no_supported_kinds(monkeypatch):
    monkeypatch.setattr(get_settings(), "camoufox_enabled", False)
    camoufox = next(engine for engine in browser_engines() if engine.browser_engine == BrowserEngine.CAMOUFOX)
    assert not camoufox.available
    assert camoufox.kinds == []
    assert camoufox.automation == "commands"


@pytest.mark.parametrize(
    "labels,supported",
    [
        ({"io.verge.browser.engines": "camoufox", "io.verge.browser.launcher-version": "1"}, True),
        ({"io.verge.browser.engines": "chromium", "io.verge.browser.launcher-version": "1"}, False),
        ({"io.verge.browser.engines": "camoufox", "io.verge.browser.launcher-version": "0"}, False),
        (None, False),
    ],
)
def test_runtime_image_requires_managed_launcher(monkeypatch, labels, supported):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kw: subprocess.CompletedProcess(args, 0, json.dumps(labels), ""))
    assert DockerAdapter().camoufox_image_supported("image") == supported
