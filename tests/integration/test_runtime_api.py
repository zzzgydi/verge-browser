from __future__ import annotations

import itertools
import base64
import io
import json
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.config import get_settings
from app.services.docker_adapter import docker_adapter
from app.services.browser import browser_service
from app.services.registry import registry


pytestmark = pytest.mark.integration
AUTH_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def body(response):
    return response.json()["data"]


def _testclient_ws_target(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path if not parsed.query else f"{parsed.path}?{parsed.query}"


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


def _require_runtime_image(image_name: str) -> None:
    if not docker_adapter.is_available():
        pytest.skip("docker daemon unavailable")

    image_check = __import__("subprocess").run(
        ["docker", "image", "inspect", image_name],
        check=False,
        capture_output=True,
        text=True,
    )
    if image_check.returncode != 0:
        pytest.skip(f"{image_name} image not built")


@pytest.fixture()
def docker_runtime_ready() -> None:
    _require_runtime_image("verge-browser-runtime-xvfb:latest")


@pytest.fixture()
def docker_runtime_xpra_ready() -> None:
    _require_runtime_image("verge-browser-runtime-xpra:latest")


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
    monkeypatch.setattr(get_settings(), "sandbox_base_dir", base_dir)
    return base_dir


def test_runtime_browser_endpoints(docker_runtime_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    client = TestClient(app)
    created = client.post("/sandbox", json={}, headers=AUTH_HEADERS)
    assert created.status_code == 201, created.text
    sandbox_id = body(created)["id"]

    try:
        browser_info = client.get(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS)
        assert browser_info.status_code == 200
        browser_payload = body(browser_info)["browser"]
        assert browser_payload["web_socket_debugger_url_present"] is True
        viewport_payload = {
            "window_viewport": browser_payload["window_viewport"],
            "page_viewport": browser_payload["page_viewport"],
            "active_window": browser_payload["active_window"],
        }
        assert viewport_payload["window_viewport"]["width"] > 0
        assert viewport_payload["active_window"]["x"] == 0
        assert viewport_payload["active_window"]["y"] == 0
        assert body(browser_info)["kind"] == "xvfb_vnc"

        window_shot = client.post(f"/sandbox/{sandbox_id}/browser/screenshot", json={"type": "window"}, headers=AUTH_HEADERS)
        assert window_shot.status_code == 200
        assert len(body(window_shot)["data_base64"]) > 100

        page_shot = client.post(f"/sandbox/{sandbox_id}/browser/screenshot", json={"type": "page"}, headers=AUTH_HEADERS)
        assert page_shot.status_code == 200
        assert len(body(page_shot)["data_base64"]) > 100

        actions = client.post(
            f"/sandbox/{sandbox_id}/browser/actions",
            json={"actions": [{"type": "WAIT", "duration_ms": 5}]},
            headers=AUTH_HEADERS,
        )
        assert actions.status_code == 200
        assert body(actions)["ok"] is True

        ticket_resp = client.post(f"/sandbox/{sandbox_id}/session/apply", headers=AUTH_HEADERS)
        assert ticket_resp.status_code == 200
        ticket_payload = body(ticket_resp)
        assert ticket_payload["mode"] == "one_time"
        assert ticket_payload["ttl_sec"] == 60
        assert ticket_payload["expires_at"] is not None
        ticket = ticket_payload["ticket"]

        session_entry = client.get(f"/sandbox/{sandbox_id}/session/?ticket={ticket}")
        assert session_entry.status_code == 200
        assert client.cookies.get("sandbox_session")
        session_asset = client.get(
            f"/sandbox/{sandbox_id}/session/vnc.html",
            cookies=client.cookies,
        )
        assert session_asset.status_code == 200
        assert "Verge Browser Session" in session_asset.text

        clipboard_write = client.post(
            f"/sandbox/{sandbox_id}/clipboard",
            json={"text": "hello clipboard"},
            cookies=client.cookies,
        )
        assert clipboard_write.status_code == 200
        assert clipboard_write.json() == {"status": "ok"}

        clipboard_read = client.get(f"/sandbox/{sandbox_id}/clipboard", cookies=client.cookies)
        assert clipboard_read.status_code == 200
        assert clipboard_read.json() == {"status": "ok", "text": "hello clipboard"}

        cdp_ticket = body(client.post(f"/sandbox/{sandbox_id}/cdp/apply", headers=AUTH_HEADERS))
        with client.websocket_connect(_testclient_ws_target(cdp_ticket["cdp_url"])) as ws:
            counter = itertools.count(1)
            target = _cdp_call(ws, counter, "Target.createTarget", {"url": "about:blank"})
            target_id = target["targetId"]
            session_id = _cdp_call(ws, counter, "Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
            _cdp_call(ws, counter, "Runtime.evaluate", {
                "expression": "document.body.innerHTML = '<textarea id=clipboard-test></textarea>'; document.querySelector('textarea').focus()",
            }, session_id=session_id)
            _cdp_call(ws, counter, "Page.bringToFront", session_id=session_id)
            pasted = client.post(
                f"/sandbox/{sandbox_id}/browser/actions",
                json={"actions": [{"type": "HOTKEY", "keys": ["ctrl", "v"]}]},
                headers=AUTH_HEADERS,
            )
            assert pasted.status_code == 200
            for _ in range(30):
                value = _cdp_call(ws, counter, "Runtime.evaluate", {
                    "expression": "document.querySelector('textarea').value", "returnByValue": True,
                }, session_id=session_id)
                if value["result"].get("value") == "hello clipboard":
                    break
                time.sleep(0.1)
            else:
                pytest.fail("X11 clipboard text was not pasted into Chromium")
            _cdp_call(ws, counter, "Target.closeTarget", {"targetId": target_id})
    finally:
        deleted = client.delete(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS)
        assert deleted.status_code == 200


def test_runtime_files_endpoints(docker_runtime_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    client = TestClient(app)
    created = client.post("/sandbox", json={"default_url": "about:blank"}, headers=AUTH_HEADERS)
    assert created.status_code == 201, created.text
    sandbox_id = body(created)["id"]

    try:
        write_resp = client.post(
            f"/sandbox/{sandbox_id}/files/write",
            json={"path": "/workspace/downloads/notes.txt", "content": "hello verge download", "overwrite": True},
            headers=AUTH_HEADERS,
        )
        assert write_resp.status_code == 200

        list_resp = client.get(f"/sandbox/{sandbox_id}/files/list", params={"path": "/workspace/downloads"}, headers=AUTH_HEADERS)
        assert list_resp.status_code == 200
        seen_names = [entry["name"] for entry in body(list_resp)]
        assert "notes.txt" in seen_names

        read_resp = client.get(f"/sandbox/{sandbox_id}/files/read", params={"path": "/workspace/downloads/notes.txt"}, headers=AUTH_HEADERS)
        assert read_resp.status_code == 200
        assert body(read_resp)["content"] == "hello verge download"

        download_resp = client.get(f"/sandbox/{sandbox_id}/files/download", params={"path": "/workspace/downloads/notes.txt"}, headers=AUTH_HEADERS)
        assert download_resp.status_code == 200
        assert download_resp.text == "hello verge download"

    finally:
        deleted = client.delete(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS)
        assert deleted.status_code == 200


def test_cdp_websocket_rejects_invalid_ticket(docker_runtime_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    client = TestClient(app)
    created = client.post("/sandbox", json={"default_url": "about:blank"}, headers=AUTH_HEADERS)
    assert created.status_code == 201, created.text
    sandbox_id = body(created)["id"]

    try:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/sandbox/{sandbox_id}/cdp/browser?ticket=bad-ticket"):
                pass
    finally:
        deleted = client.delete(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS)
        assert deleted.status_code == 200


def test_xpra_session_assets_open(docker_runtime_xpra_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    # Keep the event loop alive for Xpra's asynchronous readiness probe.
    with TestClient(app) as client:
        created = client.post("/sandbox", json={"kind": "xpra", "default_url": "about:blank"}, headers=AUTH_HEADERS)
        assert created.status_code == 201, created.text
        sandbox_id = body(created)["id"]

        try:
            for _ in range(60):
                details = client.get(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS)
                assert details.status_code == 200, details.text
                if body(details)["status"] == "RUNNING":
                    break
                time.sleep(0.5)
            else:
                pytest.fail("Xpra did not become ready")
            ticket_resp = client.post(f"/sandbox/{sandbox_id}/session/apply", headers=AUTH_HEADERS)
            assert ticket_resp.status_code == 200
            ticket = body(ticket_resp)["ticket"]

            session_entry = client.get(f"/sandbox/{sandbox_id}/session/?ticket={ticket}")
            assert session_entry.status_code == 200
            assert client.cookies.get("sandbox_session")

            session_asset = client.get(
                f"/sandbox/{sandbox_id}/session/js/lib/jquery-ui.js",
                cookies=client.cookies,
            )
            assert session_asset.status_code == 200
            assert "jQuery UI" in session_asset.text
        finally:
            deleted = client.delete(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS)
            assert deleted.status_code == 200


@pytest.mark.parametrize("kind", ["xpra", "xvfb_vnc"])
def test_window_screenshot_contains_browser_pixels_without_session(kind: str, clean_sandbox_base: Path) -> None:
    _require_runtime_image(f"verge-browser-runtime-{'xpra' if kind == 'xpra' else 'xvfb'}:latest")
    html = '<body style="margin:0;background:rgb(220,40,60)"><h1>Screenshot test</h1>' \
           '<div style="height:220px;background:rgb(30,100,220)">Blue panel</div></body>'
    client = TestClient(app)
    created = client.post("/sandbox", json={
        "kind": kind, "default_url": "data:text/html," + quote(html),
    }, headers=AUTH_HEADERS)
    assert created.status_code == 201, created.text
    sandbox_id = body(created)["id"]
    sandbox = registry.get(sandbox_id)
    assert sandbox is not None
    try:
        # Xpra creation returns STARTING before Chromium has an X11 window.
        for _ in range(60):
            details = client.get(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS)
            assert details.status_code == 200, details.text
            browser = body(details)["browser"]
            if (browser.get("active_window") or {}).get("window_id") and browser["web_socket_debugger_url_present"]:
                break
            time.sleep(0.5)
        else:
            pytest.fail("Browser did not expose its window and CDP endpoint")
        window = browser_service._discover_window(sandbox)
        if kind == "xpra":
            state = docker_adapter.exec_shell(sandbox.container_id,
                browser_service._with_display(sandbox, f'xwininfo -id {window["window_id"]}'))
            assert "Map State: IsUnviewable" in state.stdout

        # No HTML5/VNC client is connected. Verify pixels, not just a nonempty PNG.
        for _ in range(2):
            response = client.post(f"/sandbox/{sandbox_id}/browser/screenshot",
                json={"type": "window", "format": "png"}, headers=AUTH_HEADERS)
            assert response.status_code == 200, response.text
            shot = body(response)
            image = Image.open(io.BytesIO(base64.b64decode(shot["data_base64"]))).convert("RGB")
            assert shot["media_type"] == "image/png"
            assert image.size == (shot["metadata"]["width"], shot["metadata"]["height"])
            colors = dict((rgb, count) for count, rgb in image.getcolors(image.width * image.height))
            assert colors.get((220, 40, 60), 0) > image.width * image.height * 0.1
            assert colors.get((30, 100, 220), 0) > image.width * image.height * 0.1
        if kind == "xpra":
            root_capture = docker_adapter.exec_shell(sandbox.container_id,
                browser_service._with_display(sandbox,
                    f'import -window root -crop "{window["width"]}x{window["height"]}+0+0" png:-'), text=False)
            assert root_capture.returncode == 0
            desktop = Image.open(io.BytesIO(root_capture.stdout)).convert("RGB")
            # The former implementation returns a valid but empty desktop image.
            colors = dict((rgb, count) for count, rgb in desktop.getcolors(desktop.width * desktop.height))
            assert colors.get((220, 40, 60), 0) == 0
    finally:
        assert client.delete(f"/sandbox/{sandbox_id}", headers=AUTH_HEADERS).status_code == 200
