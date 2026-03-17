from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import subprocess
import time
from collections import defaultdict
from threading import Lock

from app.models.sandbox import SandboxKind, SandboxRecord, SandboxStatus
from app.services.browser import browser_service
from app.services.docker_adapter import docker_adapter

logger = logging.getLogger(__name__)

MAX_CLIPBOARD_TEXT_BYTES = 64 * 1024
RATE_LIMIT_WINDOW_SEC = 0.1


class ClipboardError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ClipboardService:
    def __init__(self) -> None:
        self._rate_limit_lock = Lock()
        self._last_request_at: dict[tuple[str, str], float] = defaultdict(float)

    async def read_text(self, sandbox: SandboxRecord) -> str:
        self._ensure_available(sandbox)
        self._check_rate_limit(sandbox.id, "read")
        proc = await asyncio.to_thread(docker_adapter.exec_shell, sandbox.container_id, self._read_command(sandbox))
        payload = self._parse_exec_payload(proc)
        output = payload["stdout"]
        if not output:
            raise ClipboardError(409, "clipboard_empty", "clipboard is empty")
        if len(output.encode("utf-8")) > MAX_CLIPBOARD_TEXT_BYTES:
            raise ClipboardError(413, "payload_too_large", "clipboard payload exceeds 64 KiB")
        logger.info("clipboard read ok for sandbox %s length=%s sha256=%s", sandbox.id, len(output), self._digest(output))
        return output

    async def write_text(self, sandbox: SandboxRecord, text: str) -> None:
        self._ensure_available(sandbox)
        self._check_rate_limit(sandbox.id, "write")
        self._validate_text(text)
        proc = await asyncio.to_thread(docker_adapter.exec_shell, sandbox.container_id, self._write_command(sandbox, text))
        self._parse_exec_payload(proc)
        logger.info("clipboard write ok for sandbox %s length=%s sha256=%s", sandbox.id, len(text), self._digest(text))

    def _ensure_available(self, sandbox: SandboxRecord) -> None:
        if sandbox.kind != SandboxKind.XVFB_VNC:
            raise ClipboardError(404, "clipboard_unavailable", "clipboard is only available for xvfb_vnc sandboxes")
        if sandbox.status in {SandboxStatus.FAILED, SandboxStatus.STOPPED} or not sandbox.container_id:
            raise ClipboardError(409, "display_unavailable", "sandbox is not ready for clipboard access")

    def _check_rate_limit(self, sandbox_id: str, action: str) -> None:
        now = time.monotonic()
        key = (sandbox_id, action)
        with self._rate_limit_lock:
            previous = self._last_request_at[key]
            if now - previous < RATE_LIMIT_WINDOW_SEC:
                raise ClipboardError(429, "rate_limited", "clipboard requests are too frequent")
            self._last_request_at[key] = now

    def _validate_text(self, text: str) -> None:
        if not text:
            raise ClipboardError(400, "clipboard_empty", "clipboard text must not be empty")
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_CLIPBOARD_TEXT_BYTES:
            raise ClipboardError(413, "payload_too_large", "clipboard payload exceeds 64 KiB")
        if "\x00" in text:
            raise ClipboardError(400, "clipboard_unsupported", "clipboard text contains unsupported control characters")

    def _parse_exec_payload(self, proc: subprocess.CompletedProcess[str]) -> dict[str, str]:
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = stderr or stdout or "clipboard command failed"
            code = "clipboard_exec_failed"
            status_code = 502
            if "DISPLAY_UNAVAILABLE" in detail:
                code = "display_unavailable"
                status_code = 409
            elif "CLIPBOARD_EMPTY" in detail:
                code = "clipboard_empty"
                status_code = 409
            elif "CLIPBOARD_UNSUPPORTED" in detail:
                code = "clipboard_unsupported"
                status_code = 400
            logger.warning("clipboard exec failed code=%s detail=%s", code, detail)
            raise ClipboardError(status_code, code, detail)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ClipboardError(502, "clipboard_exec_failed", "clipboard command returned invalid JSON") from exc
        if payload.get("status") != "ok":
            code = payload.get("code", "clipboard_exec_failed")
            message = payload.get("message", "clipboard command failed")
            status_code = 502
            if code == "display_unavailable":
                status_code = 409
            elif code == "clipboard_empty":
                status_code = 409
            elif code == "clipboard_unsupported":
                status_code = 400
            raise ClipboardError(status_code, code, message)
        return payload

    def _read_command(self, sandbox: SandboxRecord) -> str:
        display = browser_service._display_env(sandbox)
        return f"""export DISPLAY="{display}"
python3 - <<'PY'
import json
import subprocess
import sys

proc = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True)
stderr = proc.stderr.decode("utf-8", errors="replace").strip()
if proc.returncode != 0:
    lowered = stderr.lower()
    if "can't open display" in lowered or "unable to open display" in lowered:
        print("DISPLAY_UNAVAILABLE", file=sys.stderr)
        raise SystemExit(1)
    if "target string not available" in lowered or "clipboard" in lowered and "empty" in lowered:
        print("CLIPBOARD_EMPTY", file=sys.stderr)
        raise SystemExit(1)
    print(stderr or "CLIPBOARD_EXEC_FAILED", file=sys.stderr)
    raise SystemExit(1)
try:
    text = proc.stdout.decode("utf-8")
except UnicodeDecodeError:
    print("CLIPBOARD_UNSUPPORTED", file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({{"status": "ok", "stdout": text}}, ensure_ascii=False))
PY"""

    def _write_command(self, sandbox: SandboxRecord, text: str) -> str:
        display = browser_service._display_env(sandbox)
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        return f"""export DISPLAY="{display}"
python3 - <<'PY'
import base64
import json
import subprocess
import sys

payload = base64.b64decode("{encoded}").decode("utf-8")
proc = subprocess.run(["xclip", "-selection", "clipboard"], input=payload, text=True, capture_output=True)
stderr = proc.stderr.strip()
if proc.returncode != 0:
    lowered = stderr.lower()
    if "can't open display" in lowered or "unable to open display" in lowered:
        print("DISPLAY_UNAVAILABLE", file=sys.stderr)
        raise SystemExit(1)
    print(stderr or "CLIPBOARD_EXEC_FAILED", file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({{"status": "ok"}}, ensure_ascii=False))
PY"""

    def _digest(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


clipboard_service = ClipboardService()
