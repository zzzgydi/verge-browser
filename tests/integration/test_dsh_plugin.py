"""Real bridge smoke against disposable Verge runtimes; no model credentials needed."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time

import httpx
import pytest
import uvicorn

from app.config import get_settings
from app.main import app
from app.services.docker_adapter import docker_adapter

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("engine", ["chromium", "camoufox"])
def test_dsh_bridge_real_browser(engine, tmp_path, monkeypatch):
    if os.environ.get("VERGE_DSH_RUNTIME_TEST") != "1":
        pytest.skip("set VERGE_DSH_RUNTIME_TEST=1 after building the plugin and runtime images")
    settings = get_settings()
    monkeypatch.setattr(docker_adapter, "managed_label_key", "verge.dsh.smoke")
    monkeypatch.setattr(settings, "sandbox_base_dir", tmp_path / "sandboxes")
    if engine == "camoufox":
        binary = os.environ.get("VERGE_CAMOUFOX_BINARY_DIR")
        if not binary:
            pytest.skip("set VERGE_CAMOUFOX_BINARY_DIR")
        monkeypatch.setattr(settings, "camoufox_enabled", True)
        monkeypatch.setattr(settings, "camoufox_binary_dir", Path(binary))
    host_template = os.environ.get("VERGE_TEST_RUNTIME_HOST_TEMPLATE")
    if host_template:
        def runtime_host(container_id):
            name = subprocess.check_output(["docker", "inspect", "--format", "{{.Name}}", container_id], text=True).strip().lstrip("/")
            return socket.gethostbyname(host_template.format(name=name))
        monkeypatch.setattr(docker_adapter, "inspect_container_ip", runtime_host)
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT / "tests/fixtures"))
    fixture = ThreadingHTTPServer(("0.0.0.0", 0), handler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    token = settings.admin_auth_token
    sid = None
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=100, trust_env=False) as api:
        try:
            response = api.post("/sandbox", json={"browser_engine": engine})
            assert response.is_success, response.text
            sandbox = response.json()["data"]
            sid = sandbox["id"]
            assert sandbox["status"] == "RUNNING", sandbox
            config = {"baseUrl": base, "token": token, "sandbox": sid, "requestTimeoutMs": 30000, "toolCallTimeoutMs": 60000}
            result = subprocess.run(["node", "tests/runtime-smoke.mjs"], cwd=ROOT / "packages/dsh-plugin", env={
                **os.environ, "VERGE_DSH_CONFIG": json.dumps(config), "VERGE_SMOKE_ENGINE": engine,
                "VERGE_SMOKE_URL": f"http://host.docker.internal:{fixture.server_port}/camoufox-smoke.html",
            }, capture_output=True, text=True, timeout=180)
            assert result.returncode == 0, result.stdout + result.stderr
            # Disposing both the MCP and CDP clients must preserve the external runtime.
            after = api.get(f"/sandbox/{sid}").json()["data"]
            assert after["status"] == "RUNNING"
            assert after["container_id"] == sandbox["container_id"]
            assert api.get(f"/sandbox/{sid}/files/read", params={"path": "/workspace/dsh-smoke.txt"}).json()["data"]["content"] == "DSH file"
            assert api.post(f"/sandbox/{sid}/browser/screenshot", json={"type": "window", "format": "png"}).is_success
        finally:
            if sid:
                response = api.delete(f"/sandbox/{sid}")
                assert response.is_success, response.text
            server.should_exit = True
            thread.join(5)
            fixture.shutdown()
            fixture.server_close()
