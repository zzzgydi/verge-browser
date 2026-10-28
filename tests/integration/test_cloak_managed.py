"""Opt-in checks against a running Verge API; never clean up unrelated sandboxes."""
from __future__ import annotations

import json
import os
import time
import uuid

import httpx
import pytest
from websockets.sync.client import connect

pytestmark = pytest.mark.integration


def test_managed_cloak_lifecycle_and_ticketed_access() -> None:
    if os.environ.get("VERGE_TEST_CLOAK_MANAGED") != "1":
        pytest.skip("Set VERGE_TEST_CLOAK_MANAGED=1 only for a configured Verge API with a free Cloak seat.")
    base_url = os.environ["VERGE_BROWSER_URL"].rstrip("/")
    token = os.environ["VERGE_BROWSER_TOKEN"]
    kind = os.environ.get("VERGE_TEST_CLOAK_KIND", "xvfb_vnc")
    assert kind in {"xvfb_vnc", "xpra"}, "VERGE_TEST_CLOAK_KIND must be xvfb_vnc or xpra"
    # Use an inert Xpra asset, not its HTML5 client (which could connect to itself).
    local_page = "http://127.0.0.1:14500/js/lib/jquery-ui.js" if kind == "xpra" else "http://127.0.0.1:6080/vnc.html"
    alias = f"cloak-check-{uuid.uuid4().hex[:12]}"
    succeeded = False

    with httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=120, trust_env=False) as api:
        def request(method: str, path: str, **kwargs):
            response = api.request(method, path, **kwargs)
            assert response.is_success, f"{method} {path} returned {response.status_code}; inspect the test sandbox."
            return response.json()["data"]

        def persistent_storage(*, write: bool) -> str:
            ticket = request("POST", f"/sandbox/{alias}/cdp/apply")
            with connect(ticket["cdp_url"], open_timeout=10, close_timeout=2, proxy=None) as ws:
                sequence = 0

                def cdp(method: str, params=None, session_id=None):
                    nonlocal sequence
                    sequence += 1
                    message = {"id": sequence, "method": method, "params": params or {}}
                    if session_id:
                        message["sessionId"] = session_id
                    ws.send(json.dumps(message))
                    while True:
                        result = json.loads(ws.recv(timeout=10))
                        if result.get("id") == sequence:
                            assert "error" not in result, f"CDP {method} failed"
                            return result["result"]

                assert cdp("Browser.getVersion")["product"]
                # The runtime's own HTTP page gives storage a stable origin,
                # without relying on an external site or another test server.
                target = cdp("Target.createTarget", {"url": local_page})
                session = cdp("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})["sessionId"]
                for _ in range(50):
                    result = cdp("Runtime.evaluate", {"expression": f"location.href === {json.dumps(local_page)} && document.readyState === 'complete'"}, session)
                    if result["result"].get("value") is True:
                        break
                    time.sleep(0.1)
                else:
                    pytest.fail("Runtime-local probe page did not load")
                expression = "localStorage.setItem('verge-managed-check', 'persistent'); localStorage.getItem('verge-managed-check')" if write else "localStorage.getItem('verge-managed-check')"
                result = cdp("Runtime.evaluate", {"expression": expression, "returnByValue": True}, session)
                assert "exceptionDetails" not in result
                cdp("Target.closeTarget", {"targetId": target["targetId"]})
                return result["result"].get("value")

        try:
            created = request("POST", "/sandbox", json={"alias": alias, "kind": kind, "browser_engine": "cloakbrowser", "default_url": "about:blank"})
            # Xpra creation returns STARTING while readiness runs in the background.
            deadline = time.monotonic() + 120
            while created["status"] == "STARTING" and time.monotonic() < deadline:
                time.sleep(1)
                created = request("GET", f"/sandbox/{alias}")
            assert created["browser_engine"] == "cloakbrowser" and created["kind"] == kind and created["status"] == "RUNNING"
            for screenshot_type in ("window", "page"):
                screenshot = request("POST", f"/sandbox/{alias}/browser/screenshot", json={"type": screenshot_type})
                assert len(screenshot["data_base64"]) > 100
            ticket = request("POST", f"/sandbox/{alias}/session/apply")
            page = api.get(ticket["session_url"], follow_redirects=True)
            assert page.status_code == 200
            if kind == "xpra":
                asset = api.get(f"/sandbox/{created['id']}/session/js/lib/jquery-ui.js")
                assert asset.status_code == 200 and "jQuery UI" in asset.text
            else:
                assert "Verge Browser Session" in page.text
            cookie = api.cookies.get("sandbox_session")
            assert cookie
            ws_base = base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
            ws_path = "ws" if kind == "xpra" else "websockify"
            with connect(
                f"{ws_base}/sandbox/{created['id']}/session/{ws_path}",
                additional_headers={"Cookie": f"sandbox_session={cookie}"},
                subprotocols=["binary"] if kind == "xpra" else None,
                open_timeout=10, close_timeout=2, proxy=None,
            ) as ws:
                if kind == "xpra":
                    # Transport check only; visible HTML5 interaction is a manual acceptance step.
                    assert ws.subprotocol == "binary" and ws.ping().wait(10)
                else:
                    assert ws.recv(timeout=10).startswith(b"RFB ")
            assert persistent_storage(write=True) == "persistent"
            seed = request("GET", f"/sandbox/{alias}/files/read", params={"path": "/workspace/browser-profile/.cloakbrowser-seed"})["content"]
            request("POST", f"/sandbox/{alias}/pause")
            assert request("GET", f"/sandbox/{alias}")["status"] == "STOPPED"
            request("POST", f"/sandbox/{alias}/resume")
            assert persistent_storage(write=False) == "persistent"
            request("POST", f"/sandbox/{alias}/browser/restart", json={})
            assert persistent_storage(write=False) == "persistent"
            assert request("GET", f"/sandbox/{alias}/files/read", params={"path": "/workspace/browser-profile/.cloakbrowser-seed"})["content"] == seed
            request("DELETE", f"/sandbox/{alias}")
            succeeded = True
        finally:
            if not succeeded:
                print(f"Preserved test sandbox alias {alias} if created; inspect it before retrying. No other sandboxes were removed.")
