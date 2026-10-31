"""Opt-in real-engine smoke: VERGE_CAMOUFOX_BINARY_DIR must hold a verified Linux build."""

import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
import struct
from urllib.parse import urlparse

import httpx
from PIL import Image
import pytest
import uvicorn
from websockets.sync.client import connect

from app.config import get_settings
from app.main import app
from app.services.docker_adapter import docker_adapter
from app.services.registry import registry

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


class FixtureHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/download":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="smoke.txt"')
            self.end_headers()
            self.wfile.write(b"verge download smoke")
        else:
            self.path = "/camoufox-smoke.html"
            super().do_GET()

    def log_message(self, *args):
        pass


def test_camoufox_real_cli_gui_and_persistence(tmp_path, monkeypatch):
    binary = os.environ.get("VERGE_CAMOUFOX_BINARY_DIR")
    if not binary or not docker_adapter.image_exists("verge-browser-runtime-camoufox:local"):
        pytest.skip("set VERGE_CAMOUFOX_BINARY_DIR and build the optional image")
    settings = get_settings()
    monkeypatch.setattr(docker_adapter, "managed_label_key", "verge.camoufox.smoke")
    host_template = os.environ.get("VERGE_TEST_RUNTIME_HOST_TEMPLATE")
    if host_template:

        def runtime_host(container_id):
            # Docker inspect names work with local DNS providers such as OrbStack.
            name = subprocess.check_output(["docker", "inspect", "--format", "{{.Name}}", container_id], text=True).strip().lstrip("/")
            return host_template.format(name=name)

        monkeypatch.setattr(docker_adapter, "inspect_container_ip", runtime_host)
    monkeypatch.setattr(settings, "camoufox_enabled", True)
    monkeypatch.setattr(settings, "camoufox_binary_dir", Path(binary))
    monkeypatch.setattr(settings, "sandbox_base_dir", tmp_path / "sandboxes")
    handler = partial(FixtureHandler, directory=str(ROOT / "tests/fixtures"))
    fixture = ThreadingHTTPServer(("0.0.0.0", 0), handler)
    threading.Thread(target=fixture.serve_forever, daemon=True).start()
    url = f"http://host.docker.internal:{fixture.server_port}/"
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
    env = {
        **os.environ,
        "VERGE_BROWSER_URL": f"http://127.0.0.1:{port}",
        "VERGE_BROWSER_TOKEN": settings.admin_auth_token,
        "PYTHONPATH": str(ROOT / "packages/python"),
    }
    client = httpx.Client(base_url=env["VERGE_BROWSER_URL"], headers={"Authorization": f"Bearer {settings.admin_auth_token}"}, timeout=100)
    evidence = Path(os.environ.get("VERGE_SMOKE_ARTIFACT_DIR", str(tmp_path / "evidence")))
    evidence.mkdir(parents=True, exist_ok=True)
    sid = None

    def api(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.is_success, response.text
        return response.json()["data"]

    def cli(*args, node=False, failure=False):
        executable = ["node", str(ROOT / "packages/node/dist/src/cli.js")] if node else [sys.executable, "-m", "verge_browser_cli"]
        result = subprocess.run([*executable, *args, "--json"], env=env, text=True, capture_output=True, timeout=100)
        if failure:
            assert result.returncode != 0, result.stdout
            return result.stderr
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def ref(label):
        snapshot = cli("browser", "snapshot", sid, "-i")["snapshot"]
        match = re.search(r'[^\n]*"' + re.escape(label) + r'"[^\n]*\[ref=(@?e\d+)\]', snapshot)
        assert match, snapshot
        return match.group(1)

    def text(selector):
        return cli("browser", "text", sid, selector)["text"]

    try:
        created = api("POST", "/sandbox", json={"browser_engine": "camoufox", "default_url": url})
        sid = created["id"]
        assert created["status"] == "RUNNING", created
        assert not created["browser"]["web_socket_debugger_url_present"]
        assert "Firefox/156" in created["browser"]["browser_version"]
        assert cli("sandbox", "get", sid)["browser_engine"] == "camoufox"
        assert "no CDP" in cli("sandbox", "cdp", sid, failure=True)
        assert client.post(f"/sandbox/{sid}/browser/command", json={"action": "close"}).status_code == 422
        cli("browser", "fill", sid, ref("Name"), "Ada")
        cli("browser", "click", sid, ref("Save state"), node=True)
        assert text("#result") == "saved:Ada trusted:true"
        assert "not retried" in cli("browser", "click", sid, "@e9999", failure=True)

        # Native popup and named-tab adoption stay in the visible persistent context.
        cli("browser", "click", sid, ref("Open second tab"))
        tabs = cli("browser", "tabs", sid)["tabs"]
        assert len(tabs) == 2, tabs
        cli("browser", "switch", sid, "1")
        assert "popup=1" in cli("browser", "url", sid)["url"]
        cli("browser", "switch", sid, "0")
        cli("browser", "open", sid, url, "--tab", "research")
        assert len(cli("browser", "tabs", sid)["tabs"]) == 3
        cli("browser", "switch", sid, "0")

        # Real X11 input and clipboard must update the same DOM read through the CLI.
        cli("browser", "click", sid, ref("Name"))
        ticket = api("POST", f"/sandbox/{sid}/session/apply")
        parsed = urlparse(ticket["session_url"])
        session = client.get(parsed.path + "?" + parsed.query, follow_redirects=True)
        assert session.is_success
        assert "Verge Browser Session" in client.get(f"/sandbox/{sid}/session/vnc.html").text
        # Verify the authenticated WebSocket actually carries an RFB/VNC session.
        with connect(
            f"ws://127.0.0.1:{port}/sandbox/{sid}/session/websockify",
            additional_headers={"Cookie": "sandbox_session=" + client.cookies.get("sandbox_session")},
        ) as ws:
            pending = bytearray()

            def receive_exact(size):
                while len(pending) < size:
                    pending.extend(ws.recv(timeout=5))
                data = bytes(pending[:size])
                del pending[:size]
                return data

            assert receive_exact(12).startswith(b"RFB 003.")
            ws.send(b"RFB 003.008\n")
            security = receive_exact(receive_exact(1)[0])
            assert 1 in security
            ws.send(b"\x01")
            assert receive_exact(4) == b"\x00" * 4
            ws.send(b"\x01")
            initial = receive_exact(24)
            width, height = struct.unpack(">HH", initial[:4])
            assert width > 0 and height > 0
            receive_exact(struct.unpack(">I", initial[20:24])[0])
        clip = client.post(f"/sandbox/{sid}/clipboard", json={"text": "GUI-smoke"})
        assert clip.is_success, clip.text
        api(
            "POST",
            f"/sandbox/{sid}/browser/actions",
            json={"actions": [{"type": "HOTKEY", "keys": ["ctrl", "a"]}, {"type": "HOTKEY", "keys": ["ctrl", "v"]}]},
        )
        assert text("#typed") == "typed:GUI-smoke"
        viewport = api("GET", f"/sandbox/{sid}")["browser"]["page_viewport"]
        api(
            "POST",
            f"/sandbox/{sid}/browser/actions",
            json={
                "actions": [
                    {
                        "type": "CLICK",
                        "x": viewport["x"] + 100,
                        "y": viewport["y"] + viewport["height"] - 42,
                    }
                ]
            },
        )
        assert text("#result") == "gui-click trusted:true"
        idle_seconds = int(os.environ.get("VERGE_TEST_CAMOUFOX_IDLE_SEC", "0"))
        if idle_seconds:
            container = registry.get(sid).container_id
            pid_before = docker_adapter.exec(container, ["pgrep", "-x", "camoufox-bin"]).stdout
            started = time.monotonic()
            time.sleep(idle_seconds)  # No worker requests, heartbeats or browser input.
            elapsed = time.monotonic() - started
            assert docker_adapter.exec(container, ["pgrep", "-x", "camoufox-bin"]).stdout == pid_before
            api("POST", f"/sandbox/{sid}/browser/actions", json={"actions": [{
                "type": "CLICK", "x": viewport["x"] + 100, "y": viewport["y"] + viewport["height"] - 42,
            }]})
            assert text("#result") == "gui-click trusted:true"
            (evidence / "idle.json").write_text(json.dumps({"idle_seconds": elapsed, "same_browser_pid": True, "gui_after_idle": True}))

        upload = tmp_path / "upload.txt"
        upload.write_text("verge upload smoke")
        cli("files", "upload", sid, str(upload))
        cli("browser", "upload", sid, "#file", "/workspace/uploads/upload.txt")
        assert text("#upload") == "verge upload smoke"
        cli("browser", "click", sid, ref("Download file"))
        for _ in range(50):
            files = cli("files", "list", sid, "/workspace/downloads")
            if any(item["name"] == "smoke.txt" for item in files):
                break
            time.sleep(0.1)
        cli("files", "download", sid, "/workspace/downloads/smoke.txt", "--output", str(tmp_path / "download.txt"))
        assert (tmp_path / "download.txt").read_text() == "verge download smoke"
        for kind in ("window", "page"):
            shot = cli("browser", "screenshot", sid, "--type", kind, "--format", "png", "--output", str(evidence / f"{kind}.png"))
            image = Image.open(io.BytesIO(base64.b64decode(shot["data_base64"]))).convert("RGB")
            assert image.size == (shot["metadata"]["width"], shot["metadata"]["height"])
            colors = {rgb: count for count, rgb in image.getcolors(image.width * image.height)}
            assert colors.get((30, 100, 220), 0) > image.width * image.height * 0.1
        item = registry.get(sid)
        identity = (item.browser_profile_dir / "camoufox-cli.json").read_bytes()
        old_container = item.container_id
        api("POST", f"/sandbox/{sid}/pause")
        assert not docker_adapter.container_exists(old_container)
        api("POST", f"/sandbox/{sid}/resume")
        cli("browser", "open", sid, url)
        cli("browser", "click", sid, ref("Read state"))
        assert text("#result") == "local:Ada cookie:verge=Ada idb:Ada"
        assert (item.browser_profile_dir / "camoufox-cli.json").read_bytes() == identity
        assert docker_adapter.exec(item.container_id, ["bash", "/opt/sandbox/scripts/healthcheck.sh"]).returncode == 0
        api("POST", f"/sandbox/{sid}/browser/restart", json={"level": "hard"})
        cli("browser", "open", sid, url)
        cli("browser", "click", sid, ref("Read state"))
        assert text("#result") == "local:Ada cookie:verge=Ada idb:Ada"
        assert (item.browser_profile_dir / "camoufox-cli.json").read_bytes() == identity
        # A crashed engine is reported, never silently relaunched; recovery is explicit.
        docker_adapter.exec(item.container_id, ["pkill", "-TERM", "-x", "camoufox-bin"])
        for _ in range(50):
            if docker_adapter.camoufox_exited(item.container_id):
                break
            time.sleep(0.1)
        assert api("GET", f"/sandbox/{sid}")["status"] == "DEGRADED"
        assert client.post(f"/sandbox/{sid}/browser/command", json={"action": "snapshot"}).status_code == 409
        api("POST", f"/sandbox/{sid}/browser/restart", json={"level": "hard"})
        cli("browser", "open", sid, url)
        cli("browser", "click", sid, ref("Read state"))
        assert text("#result") == "local:Ada cookie:verge=Ada idb:Ada"
        assert (item.browser_profile_dir / "camoufox-cli.json").read_bytes() == identity
        (evidence / "result.json").write_text(
            json.dumps(
                {
                    "engine": "camoufox",
                    "version": created["browser"]["browser_version"],
                    "checks": [
                        "python-cli",
                        "node-cli",
                        "trusted-click",
                        "refs",
                        "tabs",
                        "gui-clipboard",
                        "novnc-rfb",
                        "upload",
                        "download",
                        "screenshots",
                        "pause-resume",
                        "restart",
                        "identity",
                        "cookies",
                        "localStorage",
                        "IndexedDB",
                        "cdp-rejected",
                        "crash-recovery",
                    ],
                },
                indent=2,
            )
        )
    finally:
        if sid:
            item = registry.get(sid)
            if item and item.container_id:
                logs = docker_adapter.exec_shell(item.container_id, "cat /var/log/sandbox/chromium.err.log")
                (evidence / "worker.log").write_text(logs.stdout + logs.stderr)
            response = client.delete(f"/sandbox/{sid}")
            # Preserve the failed runtime for diagnosis if graceful deletion fails.
            assert response.is_success, response.text
        client.close()
        server.should_exit = True
        thread.join(10)
        fixture.shutdown()


def test_chromium_agent_browser_skill_route(tmp_path, monkeypatch):
    executable = os.environ.get("VERGE_TEST_AGENT_BROWSER")
    if not executable or not docker_adapter.image_exists("verge-browser-runtime-xvfb:latest"):
        pytest.skip("set VERGE_TEST_AGENT_BROWSER to a local agent-browser executable")
    monkeypatch.setattr(docker_adapter, "managed_label_key", "verge.cdp.smoke")
    monkeypatch.setattr(get_settings(), "sandbox_base_dir", tmp_path / "sandboxes")
    fixture = ThreadingHTTPServer(("0.0.0.0", 0), partial(FixtureHandler, directory=str(ROOT / "tests/fixtures")))
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
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}", headers={"Authorization": f"Bearer {get_settings().admin_auth_token}"}, timeout=100
    )
    env = {
        **os.environ,
        "AGENT_BROWSER_SESSION": f"verge-smoke-{port}",
        "VERGE_BROWSER_URL": f"http://127.0.0.1:{port}",
        "VERGE_BROWSER_TOKEN": get_settings().admin_auth_token,
        "PYTHONPATH": str(ROOT / "packages/python"),
    }
    sid = None
    cdp_url = None

    def agent(*args):
        result = subprocess.run([executable, "--cdp", cdp_url, *args, "--json"], env=env, text=True, capture_output=True, timeout=60)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["success"], payload
        return payload["data"]

    try:
        response = client.post(
            "/sandbox", json={"browser_engine": "chromium", "default_url": f"http://host.docker.internal:{fixture.server_port}/"}
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        sid = data["id"]
        assert data["browser_engine"] == "chromium"
        assert data["status"] == "RUNNING", data
        ticket = subprocess.run(
            [sys.executable, "-m", "verge_browser_cli", "sandbox", "cdp", sid, "--ttl-sec", "300", "--json"],
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert ticket.returncode == 0, ticket.stderr
        cdp_url = json.loads(ticket.stdout)["cdp_url"]
        snap = agent("snapshot", "-i")
        refs = snap["refs"]
        name_ref = next(ref for ref, info in refs.items() if info["name"] == "Name")
        agent("fill", "@" + name_ref.lstrip("@"), "Chromium-smoke")
        refs = agent("snapshot", "-i")["refs"]
        save_ref = next(ref for ref, info in refs.items() if info["name"] == "Save state")
        agent("click", "@" + save_ref.lstrip("@"))
        result = agent("get", "text", "#result")
        assert "saved:Chromium-smoke trusted:true" in json.dumps(result), result
        wrong = client.post(f"/sandbox/{sid}/browser/command", json={"action": "snapshot"})
        assert wrong.status_code == 409 and "agent-browser" in wrong.text
        if directory := os.environ.get("VERGE_SMOKE_ARTIFACT_DIR"):
            Path(directory).mkdir(parents=True, exist_ok=True)
            Path(directory, "chromium-agent-browser.json").write_text(
                json.dumps({"engine": "chromium", "result": result, "route": "ticketed CDP"}, indent=2)
            )
    finally:
        if cdp_url:
            subprocess.run([executable, "--cdp", cdp_url, "close"], env=env, text=True, capture_output=True, timeout=30)
        if sid:
            assert client.delete(f"/sandbox/{sid}").is_success
        client.close()
        server.should_exit = True
        thread.join(10)
        fixture.shutdown()
