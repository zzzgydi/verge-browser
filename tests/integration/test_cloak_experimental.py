"""Opt-in PoC using only its own resources, never the managed-container cleanup fixture."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.sandbox import RuntimeEndpoint, SandboxRecord, SandboxStatus
from app.services.browser import CdpClient
from app.services.registry import registry

pytestmark = pytest.mark.integration
PYTHON = "/opt/sandbox/cloak-venv/bin/python"
CONTROL = "/opt/sandbox/cloak/cloak_control.py"
SUPERVISOR_CONFIG = "/etc/supervisor/conf.d/supervisord.conf"


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=40)
    # Do not include command arguments or arbitrary daemon output in test reports.
    assert result.returncode == 0, f"Docker {args[0]} failed; inspect the dedicated test container."
    return result.stdout.strip()


def wait_ready(name: str, cdp_port: int) -> dict:
    with httpx.Client(trust_env=False, timeout=2) as http:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                response = http.get(f"http://127.0.0.1:{cdp_port}/json/version")
                response.raise_for_status()
                if response.json().get("webSocketDebuggerUrl"):
                    status = json.loads(docker("exec", name, PYTHON, CONTROL, "status"))
                    if status["process_state"] == "RUNNING" and not status["error"]:
                        return response.json()
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(1)
    pytest.fail("Cloak did not become ready; preserve the test container and inspect cloak_control.py status.")


async def page_storage(cdp_port: int, *, write: bool) -> dict:
    async with httpx.AsyncClient(trust_env=False) as http:
        version = (await http.get(f"http://127.0.0.1:{cdp_port}/json/version")).json()
    path = urlsplit(version["webSocketDebuggerUrl"]).path
    async with CdpClient(f"ws://127.0.0.1:{cdp_port}{path}") as cdp:
        target = await cdp.call("Target.createTarget", {"url": "http://127.0.0.1:18080/probe.html"})
        session = await cdp.call("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})
        session_id = session["sessionId"]
        for _ in range(50):
            ready = await cdp.call("Runtime.evaluate", {"expression": "document.readyState === 'complete' && location.pathname === '/probe.html'"}, session_id=session_id)
            if ready["result"].get("value") is True:
                break
            await asyncio.sleep(0.1)
        else:
            raise AssertionError("Local probe page did not load")
        expression = """(async () => {
          const db = await new Promise((resolve, reject) => {
            const request = indexedDB.open('verge-cloak-test', 1);
            request.onupgradeneeded = () => request.result.createObjectStore('state');
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          if (WRITE) {
            localStorage.setItem('verge', 'persistent');
            document.cookie = 'verge=persistent; Max-Age=3600; SameSite=Lax; Path=/';
            await new Promise((resolve, reject) => {
              const tx = db.transaction('state', 'readwrite');
              tx.objectStore('state').put('persistent', 'verge');
              tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
            });
          }
          const indexed = await new Promise((resolve, reject) => {
            const request = db.transaction('state').objectStore('state').get('verge');
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          db.close();
          return {local: localStorage.getItem('verge'), cookie: document.cookie, indexed};
        })()""".replace("WRITE", "true" if write else "false")
        result = await cdp.call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True}, session_id=session_id)
        assert "exceptionDetails" not in result
        return result["result"]["value"]


def test_cloak_gui_cdp_profile_and_container_recreation(tmp_path: Path) -> None:
    if os.environ.get("VERGE_TEST_CLOAK") != "1":
        pytest.skip("Set VERGE_TEST_CLOAK=1 only after installing a legal Cloak build for this experiment.")
    key = Path(os.environ.get("VERGE_CLOAK_LICENSE_FILE", ""))
    assert key.is_absolute() and key.is_file(), "Set VERGE_CLOAK_LICENSE_FILE to an existing absolute path."
    image = os.environ.get("VERGE_CLOAK_TEST_IMAGE", "verge-browser-runtime-xvfb:cloak-experimental")
    binaries = os.environ.get("VERGE_CLOAK_BINARY_VOLUME", "verge-browser-cloak-binaries")
    docker("volume", "inspect", binaries)
    name = f"verge-cloak-test-{uuid.uuid4().hex[:12]}"
    workspace = tmp_path / "workspace"
    workspace_volume, state_volume = f"{name}-workspace", f"{name}-state"
    docker("volume", "create", workspace_volume)
    docker("volume", "create", state_volume)
    succeeded = False
    record = None

    def start() -> tuple[int, int]:
        docker(
            "run", "-d", "--name", name, "--platform", "linux/amd64", "--shm-size", "1g",
            "-e", "BROWSER_ENGINE=cloakbrowser", "-e", "DEFAULT_URL=about:blank",
            "-p", "127.0.0.1::9223", "-p", "127.0.0.1::6080",
            "--mount", f"type=volume,src={binaries},dst=/opt/verge/cloak,readonly",
            "--mount", f"type=volume,src={workspace_volume},dst=/workspace",
            "--mount", f"type=volume,src={state_volume},dst=/root/.cloakbrowser",
            "--mount", f"type=bind,src={key},dst=/root/.cloakbrowser/license.key,readonly",
            image,
        )
        cdp_port = int(docker("port", name, "9223/tcp").rsplit(":", 1)[1])
        gui_port = int(docker("port", name, "6080/tcp").rsplit(":", 1)[1])
        docker("exec", name, "python3", "-c", "from pathlib import Path; Path('/workspace/probe.html').write_text('<!doctype html><title>Verge Cloak test</title><h1>Local test only</h1>')")
        docker("exec", "-d", name, "python3", "-m", "http.server", "18080", "--bind", "127.0.0.1", "--directory", "/workspace")
        wait_ready(name, cdp_port)
        return cdp_port, gui_port

    def close() -> None:
        result = json.loads(docker("exec", name, PYTHON, CONTROL, "stop"))
        assert result["stopped"] and result["graceful"], "Browser.close did not complete normally; inspect the preserved container."

    try:
        cdp_port, gui_port = start()
        identity = docker("exec", name, "cat", "/root/.cloakbrowser/verge-profile.json")
        assert asyncio.run(page_storage(cdp_port, write=True))["indexed"] == "persistent"
        record = SandboxRecord(
            id=name, status=SandboxStatus.RUNNING, container_id=name,
            workspace_dir=workspace, downloads_dir=workspace / "downloads", uploads_dir=workspace / "uploads",
            browser_profile_dir=workspace / "browser-profile",
            runtime=RuntimeEndpoint(host="127.0.0.1", cdp_port=cdp_port, session_port=gui_port),
        )
        registry.put(record)
        # No lifespan: do not reconcile or clean up any user's managed containers.
        client = TestClient(app)
        headers = {"Authorization": "Bearer dev-admin-token"}
        response = client.post(f"/sandbox/{name}/browser/screenshot", json={"type": "window"}, headers=headers)
        assert response.status_code == 200, "Verge window discovery/screenshot failed"
        assert len(response.json()["data"]["data_base64"]) > 100
        response = client.post(f"/sandbox/{name}/browser/screenshot", json={"type": "page"}, headers=headers)
        assert response.status_code == 200, "Verge CDP screenshot failed"
        response = client.post(f"/sandbox/{name}/browser/actions", json={"actions": [{"type": "WAIT", "duration_ms": 1}]}, headers=headers)
        assert response.status_code == 200
        response = client.post(f"/sandbox/{name}/cdp/apply", headers=headers)
        assert response.status_code == 200
        target = urlsplit(response.json()["data"]["cdp_url"])
        with client.websocket_connect(f"{target.path}?{target.query}") as ws:
            ws.send_json({"id": 1, "method": "Browser.getVersion"})
            result = ws.receive_json()
            assert result.get("id") == 1 and result["result"]["product"]
        assert httpx.get(f"http://127.0.0.1:{gui_port}/vnc.html", trust_env=False).status_code == 200
        close()
        docker("exec", name, "supervisorctl", "-c", SUPERVISOR_CONFIG, "start", "chromium")
        wait_ready(name, cdp_port)
        expected = {"local": "persistent", "cookie": "verge=persistent", "indexed": "persistent"}
        assert asyncio.run(page_storage(cdp_port, write=False)) == expected
        close()
        docker("stop", "--time", "10", name)
        docker("rm", name)
        cdp_port, _ = start()
        assert asyncio.run(page_storage(cdp_port, write=False)) == expected
        assert docker("exec", name, "cat", "/root/.cloakbrowser/verge-profile.json") == identity
        close()
        succeeded = True
    finally:
        if record is not None:
            registry.delete(record.id)
        if succeeded:
            docker("stop", "--time", "10", name)
            docker("rm", name)
            docker("volume", "rm", workspace_volume, state_volume)
        else:
            print(f"Preserved isolated container {name} and its -workspace/-state volumes for inspection; no managed sandboxes were removed.")
