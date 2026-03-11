from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.docker_adapter import docker_adapter


pytestmark = pytest.mark.integration


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


@pytest.fixture()
def clean_sandbox_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base_dir = tmp_path / "sandboxes"
    monkeypatch.setenv("VERGE_SANDBOX_BASE_DIR", str(base_dir))
    return base_dir


def test_runtime_browser_endpoints(docker_runtime_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    client = TestClient(app)
    created = client.post("/sandboxes", json={})
    assert created.status_code == 201, created.text
    sandbox_id = created.json()["id"]

    try:
        browser_info = client.get(f"/sandboxes/{sandbox_id}/browser/info")
        assert browser_info.status_code == 200
        assert browser_info.json()["web_socket_debugger_url_present"] is True

        viewport = client.get(f"/sandboxes/{sandbox_id}/browser/viewport")
        assert viewport.status_code == 200
        viewport_payload = viewport.json()
        assert viewport_payload["window_viewport"]["width"] > 0
        assert viewport_payload["active_window"]["x"] == 0
        assert viewport_payload["active_window"]["y"] == 0

        window_shot = client.get(f"/sandboxes/{sandbox_id}/browser/screenshot?type=window")
        assert window_shot.status_code == 200
        assert len(window_shot.json()["data_base64"]) > 100

        page_shot = client.get(f"/sandboxes/{sandbox_id}/browser/screenshot?type=page")
        assert page_shot.status_code == 200
        assert len(page_shot.json()["data_base64"]) > 100

        actions = client.post(
            f"/sandboxes/{sandbox_id}/browser/actions",
            json={"actions": [{"type": "WAIT", "duration_ms": 5}]},
        )
        assert actions.status_code == 200
        assert actions.json()["ok"] is True

        ticket_resp = client.post(f"/sandboxes/{sandbox_id}/vnc/tickets")
        assert ticket_resp.status_code == 200
        ticket = ticket_resp.json()["ticket"]

        vnc_entry = client.get(f"/sandboxes/{sandbox_id}/vnc/?ticket={ticket}")
        assert vnc_entry.status_code == 200
        assert "vnc_session" in vnc_entry.cookies
    finally:
        deleted = client.delete(f"/sandboxes/{sandbox_id}")
        assert deleted.status_code == 204


def test_runtime_shell_and_files_endpoints(docker_runtime_ready: None, clean_sandbox_base: Path) -> None:
    del clean_sandbox_base
    client = TestClient(app)
    created = client.post("/sandboxes", json={})
    assert created.status_code == 201, created.text
    sandbox_id = created.json()["id"]

    try:
        write_resp = client.post(
            f"/sandboxes/{sandbox_id}/files/write",
            json={"path": "/workspace/notes.txt", "content": "hello verge", "overwrite": True},
        )
        assert write_resp.status_code == 200

        read_resp = client.get(f"/sandboxes/{sandbox_id}/files/read", params={"path": "/workspace/notes.txt"})
        assert read_resp.status_code == 200
        assert read_resp.json()["content"] == "hello verge"

        list_resp = client.get(f"/sandboxes/{sandbox_id}/files/list", params={"path": "/workspace"})
        assert list_resp.status_code == 200
        assert any(entry["name"] == "notes.txt" for entry in list_resp.json())

        download_resp = client.get(f"/sandboxes/{sandbox_id}/files/download", params={"path": "/workspace/notes.txt"})
        assert download_resp.status_code == 200
        assert download_resp.text == "hello verge"

        shell_resp = client.post(
            f"/sandboxes/{sandbox_id}/shell/exec",
            json={"argv": ["bash", "-lc", "pwd && cat notes.txt"], "cwd": "/workspace"},
        )
        assert shell_resp.status_code == 200
        assert "hello verge" in shell_resp.json()["stdout"]

        restart_resp = client.post(f"/sandboxes/{sandbox_id}/browser/restart", json={"level": "hard"})
        assert restart_resp.status_code == 200
        assert restart_resp.json()["level"] == "hard"
    finally:
        deleted = client.delete(f"/sandboxes/{sandbox_id}")
        assert deleted.status_code == 204
