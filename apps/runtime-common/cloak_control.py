"""Read Cloak diagnostics or close the browser before stopping its container."""
from __future__ import annotations

import argparse
import http.client
import json
import socket
import sys
import time
import urllib.request
import xmlrpc.client
from pathlib import Path

from cloak_runtime import RuntimeFailure, read_json, write_json

DENIALS = {
    76: ("SESSION_LIMIT", "Session limit reached. Close other sessions or wait for the official service to release crashed sessions."),
    77: ("LICENSE_INVALID", "The license key is missing, invalid or expired."),
    78: ("LICENSE_UNREACHABLE", "The browser could not reach the license service."),
    79: ("LICENSE_CONFIG", "Check ~/.cloakbrowser write permissions and the license route."),
}


class UnixConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(12)
        self.sock.connect("/run/sandbox/supervisor.sock")


class UnixTransport(xmlrpc.client.Transport):
    def make_connection(self, host: str) -> UnixConnection:
        return UnixConnection(host, timeout=12)


def process_info() -> dict:
    with xmlrpc.client.ServerProxy("http://localhost/RPC2", transport=UnixTransport()) as server:
        return server.supervisor.getProcessInfo("chromium")


def diagnostics(run_dir: Path, *, info: dict | None = None) -> dict:
    if info is None:
        info = process_info()
    result = {"process_state": info["statename"], "exit_code": info["exitstatus"], "error": None}
    launch_file = run_dir / "cloak-launch.json"
    if launch_file.exists():
        launch = read_json(launch_file)
        result["build"] = launch["build"]
        denial = Path(launch["denial_file"])
        if denial.parent != run_dir or denial.name != f"cloak-denial-{launch['launch_id']}.json":
            raise RuntimeFailure("INVALID_DIAGNOSTIC", "Unexpected license diagnostic path.")
        if denial.exists():
            code = json.loads(denial.read_text())
            if type(code) is int and code in DENIALS:
                result["error"] = {"code": DENIALS[code][0], "message": DENIALS[code][1]}
    if (run_dir / "cloak-error.json").exists():
        result["error"] = read_json(run_dir / "cloak-error.json")
    failed_exit = (
        info["statename"] in {"FATAL", "BACKOFF"}
        or (info["statename"] == "EXITED" and info["exitstatus"] != 0)
        or (info["statename"] == "STOPPED" and info["exitstatus"] in DENIALS)
    )
    if result["error"] is None and failed_exit:
        code, message = DENIALS.get(info["exitstatus"], ("BROWSER_EXITED", "The browser exited without a license denial signal."))
        result["error"] = {"code": code, "message": message}
    return result


def stop_browser(run_dir: Path) -> dict:
    from websockets.exceptions import ConnectionClosed, WebSocketException
    from websockets.sync.client import connect

    info = process_info()
    if info["statename"] in {"STOPPED", "EXITED", "FATAL"}:
        status = diagnostics(run_dir, info=info)
        return {
            "stopped": True, "graceful": False, "already_exited": True, "seat_release": "unconfirmed",
            "diagnostics": status, "error": status["error"],
        }
    requested = False
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:9222/json/version", timeout=3) as response:
            version = json.load(response)
        # Discovery may advertise another host, but this command only controls
        # the browser in the current container, never an external CDP endpoint.
        from urllib.parse import urlsplit

        path = urlsplit(version["webSocketDebuggerUrl"]).path
        if not path.startswith("/devtools/browser/"):
            raise ValueError("unexpected browser endpoint")
        with connect(f"ws://127.0.0.1:9222{path}", open_timeout=3, close_timeout=1, proxy=None) as ws:
            ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            requested = True
            try:
                ws.recv(timeout=1)
            except (ConnectionClosed, TimeoutError):
                pass
    except (OSError, ValueError, KeyError, TimeoutError, WebSocketException):
        pass  # A bounded Supervisor stop follows if CDP cannot close the browser.
    deadline = time.monotonic() + (7 if requested else 0)
    while time.monotonic() < deadline:
        info = process_info()
        if info["statename"] in {"EXITED", "STOPPED", "FATAL"}:
            status = diagnostics(run_dir, info=info)
            graceful = info["statename"] == "EXITED" and info["exitstatus"] == 0 and status["error"] is None
            result = {
                "stopped": True, "graceful": graceful, "seat_release": "unconfirmed",
                "diagnostics": status, "error": status["error"],
            }
            if not graceful:
                result["warning"] = "The browser stopped, but a clean CDP close was not confirmed; inspect diagnostics."
            write_json(run_dir / "cloak-stop.json", result)
            return result
        time.sleep(0.2)
    with xmlrpc.client.ServerProxy("http://localhost/RPC2", transport=UnixTransport()) as server:
        try:
            server.supervisor.stopProcess("chromium", True)
        except xmlrpc.client.Fault as exc:
            if exc.faultCode != 70:  # NOT_RUNNING after a concurrent normal exit.
                raise
    info = process_info()
    if info["statename"] not in {"STOPPED", "EXITED", "FATAL"}:
        raise RuntimeFailure("STOP_FAILED", "The browser is still running; preserve the container and profile.")
    status = diagnostics(run_dir, info=info)
    result = {
        "stopped": True, "graceful": False, "seat_release": "unconfirmed", "diagnostics": status, "error": status["error"],
        "warning": "Supervisor stop was required; session release may be delayed.",
    }
    write_json(run_dir / "cloak-stop.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "stop"])
    args = parser.parse_args()
    try:
        result = diagnostics(Path("/run/sandbox")) if args.command == "status" else stop_browser(Path("/run/sandbox"))
        print(json.dumps(result, sort_keys=True))
        return 1 if result.get("error") else 0
    except Exception as exc:
        print(json.dumps({"code": "CONTROL_FAILED", "message": f"Browser control failed ({type(exc).__name__}); preserve the container for inspection."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
