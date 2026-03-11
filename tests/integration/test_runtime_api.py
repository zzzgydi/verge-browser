from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.docker_adapter import docker_adapter
from app.services.registry import registry


pytestmark = pytest.mark.integration
AUTH_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def _cdp_call(ws, counter: itertools.count, method: str, params: dict | None = None, *, session_id: str | None = None) -> dict:
    payload: dict[str, object] = {
        "id": next(counter),
        "method": method,
        "params": params or {},
    }
    if session_id is not None:
        payload["sessionId"] = session_id
    ws.send_text(json.dumps(payload))
    while True:
        message = json.loads(ws.receive_text())
        if message.get("id") != payload["id"]:
            continue
        if "error" in message:
            raise AssertionError(f"CDP {method} failed: {message['error']}")
        return message.get("result", {})


@pytest.fixture()
def docker_runtime_ready() -> None:
    if not docker_adapter.is_available():
        pytest.skip("docker daemon unavailable")

    image_check = __import__("subprocess").run(
        ["docker", "image", "inspect", "verge-browser-runtime:latest"],
        check=False,
        capture_output=True,
        text=True,
    )
    if image_check.returncode != 0:
        pytest.skip("verge-browser-runtime:latest image not built")


@pytest.fixture(autouse=True)
def cleanup_managed_runtime_containers() -> None:
    docker_adapter.remove_managed_containers()
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)
    yield
    docker_adapter.remove_managed_containers()
    for sandbox in tuple(registry.all()):
        registry.delete(sandbox.id)


@pytest.fixture()
def clean_sandbox_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base_dir = tmp_path / "sandboxes"
    monkeypatch.setenv("VERGE_SANDBOX_BASE_DIR", str(base_dir))
    return base_dir


def test_runtime_browser_endpoints(docker_runtime_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    client = TestClient(app)
    created = client.post("/sandboxes", json={}, headers=AUTH_HEADERS)
    assert created.status_code == 201, created.text
    sandbox_id = created.json()["id"]

    try:
        browser_info = client.get(f"/sandboxes/{sandbox_id}/browser/info", headers=AUTH_HEADERS)
        assert browser_info.status_code == 200
        assert browser_info.json()["web_socket_debugger_url_present"] is True

        viewport = client.get(f"/sandboxes/{sandbox_id}/browser/viewport", headers=AUTH_HEADERS)
        assert viewport.status_code == 200
        viewport_payload = viewport.json()
        assert viewport_payload["window_viewport"]["width"] > 0
        assert viewport_payload["active_window"]["x"] == 0
        assert viewport_payload["active_window"]["y"] == 0

        window_shot = client.get(f"/sandboxes/{sandbox_id}/browser/screenshot?type=window", headers=AUTH_HEADERS)
        assert window_shot.status_code == 200
        assert len(window_shot.json()["data_base64"]) > 100

        page_shot = client.get(f"/sandboxes/{sandbox_id}/browser/screenshot?type=page", headers=AUTH_HEADERS)
        assert page_shot.status_code == 200
        assert len(page_shot.json()["data_base64"]) > 100

        actions = client.post(
            f"/sandboxes/{sandbox_id}/browser/actions",
            json={"actions": [{"type": "WAIT", "duration_ms": 5}]},
            headers=AUTH_HEADERS,
        )
        assert actions.status_code == 200
        assert actions.json()["ok"] is True

        ticket_resp = client.post(f"/sandboxes/{sandbox_id}/vnc/tickets", headers=AUTH_HEADERS)
        assert ticket_resp.status_code == 200
        ticket_payload = ticket_resp.json()
        assert ticket_payload["mode"] == "one_time"
        assert ticket_payload["ttl_sec"] == 60
        assert ticket_payload["expires_at"] is not None
        ticket = ticket_payload["ticket"]

        vnc_entry = client.get(f"/sandboxes/{sandbox_id}/vnc/?ticket={ticket}", follow_redirects=False)
        assert vnc_entry.status_code == 302
        assert vnc_entry.headers["location"] == f"/sandboxes/{sandbox_id}/vnc/vnc.html?path=/sandboxes/{sandbox_id}/vnc/websockify&resize=scale&autoconnect=true"
        assert "vnc_session" in vnc_entry.cookies
    finally:
        deleted = client.delete(f"/sandboxes/{sandbox_id}", headers=AUTH_HEADERS)
        assert deleted.status_code == 204


def test_runtime_files_endpoints(docker_runtime_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    client = TestClient(app)
    created = client.post("/sandboxes", json={"default_url": "about:blank"}, headers=AUTH_HEADERS)
    assert created.status_code == 201, created.text
    sandbox_id = created.json()["id"]

    try:
        with client.websocket_connect(f"/sandboxes/{sandbox_id}/browser/cdp/browser", headers=AUTH_HEADERS) as ws:
            counter = itertools.count(1)
            _cdp_call(
                ws,
                counter,
                "Browser.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": "/workspace/downloads", "eventsEnabled": True},
            )
            targets = _cdp_call(ws, counter, "Target.getTargets")["targetInfos"]
            page_target = next(target for target in targets if target.get("type") == "page")
            session_id = _cdp_call(
                ws,
                counter,
                "Target.attachToTarget",
                {"targetId": page_target["targetId"], "flatten": True},
            )["sessionId"]
            _cdp_call(ws, counter, "Page.enable", session_id=session_id)
            _cdp_call(ws, counter, "Runtime.enable", session_id=session_id)
            _cdp_call(ws, counter, "Page.navigate", {"url": "about:blank"}, session_id=session_id)
            _cdp_call(
                ws,
                counter,
                "Runtime.evaluate",
                {
                    "expression": """
(() => {
  const blob = new Blob(['hello verge download'], {type: 'text/plain'});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'notes.txt';
  document.body.appendChild(anchor);
  anchor.click();
  return 'download-triggered';
})()
""",
                    "awaitPromise": True,
                },
                session_id=session_id,
            )

        deadline = time.time() + 10
        seen_names: list[str] = []
        while time.time() < deadline:
            list_resp = client.get(f"/sandboxes/{sandbox_id}/files/list", params={"path": "/workspace/downloads"}, headers=AUTH_HEADERS)
            assert list_resp.status_code == 200
            seen_names = [entry["name"] for entry in list_resp.json()]
            if "notes.txt" in seen_names:
                break
            time.sleep(0.25)
        assert "notes.txt" in seen_names

        read_resp = client.get(f"/sandboxes/{sandbox_id}/files/read", params={"path": "/workspace/downloads/notes.txt"}, headers=AUTH_HEADERS)
        assert read_resp.status_code == 200
        assert read_resp.json()["content"] == "hello verge download"

        download_resp = client.get(f"/sandboxes/{sandbox_id}/files/download", params={"path": "/workspace/downloads/notes.txt"}, headers=AUTH_HEADERS)
        assert download_resp.status_code == 200
        assert download_resp.text == "hello verge download"

        restart_resp = client.post(f"/sandboxes/{sandbox_id}/browser/restart", json={"level": "hard"}, headers=AUTH_HEADERS)
        assert restart_resp.status_code == 200
        assert restart_resp.json()["level"] == "hard"
    finally:
        deleted = client.delete(f"/sandboxes/{sandbox_id}", headers=AUTH_HEADERS)
        assert deleted.status_code == 204
