from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import websockets
from fastapi import HTTPException, status

from app.models.sandbox import SandboxRecord, SandboxStatus
from app.schemas.browser import BrowserAction, BrowserActionType, BrowserActionsRequest, BrowserActionsResponse, ScreenshotEnvelope, ScreenshotMetadata, ScreenshotType
from app.services.docker_adapter import docker_adapter

logger = logging.getLogger(__name__)


class CdpClient:
    def __init__(self, ws_url: str, *, timeout_sec: float = 5.0) -> None:
        self.ws_url = ws_url
        self.timeout_sec = timeout_sec
        self._counter = 0
        self._ws = None

    async def __aenter__(self) -> "CdpClient":
        self._ws = await websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20, max_queue=100)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def call(self, method: str, params: dict[str, Any] | None = None, *, session_id: str | None = None) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("cdp client is not connected")
        self._counter += 1
        payload: dict[str, Any] = {"id": self._counter, "method": method, "params": params or {}}
        if session_id is not None:
            payload["sessionId"] = session_id
        await self._ws.send(json.dumps(payload))
        while True:
            try:
                response = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=self.timeout_sec))
            except TimeoutError as exc:
                raise RuntimeError(f"cdp call timed out: {method}") from exc
            if response.get("id") != self._counter:
                continue
            if "error" in response:
                raise RuntimeError(response["error"].get("message", "cdp error"))
            return response.get("result", {})


class BrowserService:
    def _should_log_http_probe_failure_with_traceback(self, sandbox: SandboxRecord) -> bool:
        return sandbox.status not in {SandboxStatus.STARTING}

    def _display_env(self, sandbox: SandboxRecord) -> str:
        return sandbox.runtime.display or ":100"

    def _with_display(self, sandbox: SandboxRecord, command: str) -> str:
        return f'export DISPLAY="{self._display_env(sandbox)}"; {command}'

    async def browser_version(self, sandbox: SandboxRecord) -> dict:
        return await self._browser_version_payload(sandbox, normalize_ws_url=True)

    async def upstream_browser_version(self, sandbox: SandboxRecord) -> dict:
        return await self._browser_version_payload(sandbox, normalize_ws_url=False)

    async def _browser_version_payload(self, sandbox: SandboxRecord, *, normalize_ws_url: bool) -> dict:
        url = f"http://{sandbox.runtime.host}:{sandbox.runtime.cdp_port}/json/version"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                response.raise_for_status()
            payload = response.json()
        except Exception:
            if self._should_log_http_probe_failure_with_traceback(sandbox):
                logger.warning("browser version probe via HTTP failed for sandbox %s; falling back to exec", sandbox.id, exc_info=True)
            else:
                logger.info("browser version probe via HTTP not ready for sandbox %s; falling back to exec", sandbox.id)
            payload = self._browser_version_via_exec(sandbox)
        if normalize_ws_url and payload.get("webSocketDebuggerUrl"):
            payload["webSocketDebuggerUrl"] = self._normalize_cdp_ws_url(sandbox, payload["webSocketDebuggerUrl"])
        return payload

    def get_viewport(self, sandbox: SandboxRecord) -> dict[str, Any]:
        window = self._discover_window(sandbox)
        page_viewport = {
            "x": 0,
            "y": min(80, window["height"]),
            "width": window["width"],
            "height": max(window["height"] - min(80, window["height"]), 0),
        }
        return {
            "window_viewport": {
                "x": 0,
                "y": 0,
                "width": window["width"],
                "height": window["height"],
            },
            "page_viewport": page_viewport,
            "active_window": {
                "window_id": window["window_id"],
                "x": window["x"],
                "y": window["y"],
                "title": window.get("title", "Chromium"),
            },
        }

    async def screenshot(
        self,
        sandbox: SandboxRecord,
        screenshot_type: ScreenshotType,
        image_format: str,
        target_id: str | None = None,
        quality: int | None = None,
    ) -> ScreenshotEnvelope:
        viewport = self.get_viewport(sandbox)
        if screenshot_type == ScreenshotType.window:
            image_bytes = await asyncio.to_thread(self._window_screenshot, sandbox)
        else:
            image_bytes = await self._page_screenshot(sandbox, target_id=target_id, image_format=image_format, quality=quality)
        return ScreenshotEnvelope(
            type=screenshot_type,
            format=image_format,  # type: ignore[arg-type]
            media_type=f"image/{image_format}",
            metadata=ScreenshotMetadata(
                width=viewport["window_viewport"]["width"],
                height=viewport["window_viewport"]["height"],
                page_viewport=viewport["page_viewport"],
                window_viewport=viewport["window_viewport"],
                window_id=viewport["active_window"]["window_id"],
            ),
            data_base64=base64.b64encode(image_bytes).decode(),
        )

    async def execute_actions(self, sandbox: SandboxRecord, request: BrowserActionsRequest) -> BrowserActionsResponse:
        errors: list[str] = []
        executed = 0
        viewport = self.get_viewport(sandbox)
        for action in request.actions:
            try:
                await self._run_action(sandbox, action, viewport)
                executed += 1
            except Exception as exc:
                errors.append(str(exc))
                if not request.continue_on_error:
                    break
        return BrowserActionsResponse(ok=not errors, executed=executed, screenshot_after=request.screenshot_after, errors=errors)

    async def _run_action(self, sandbox: SandboxRecord, action: BrowserAction, viewport: dict[str, Any]) -> None:
        if action.type == BrowserActionType.WAIT:
            await asyncio.sleep((action.duration_ms or 0) / 1000)
            return
        if not sandbox.container_id:
            raise RuntimeError("sandbox container unavailable")

        script = self._xdotool_script(action, viewport)
        result = await asyncio.to_thread(docker_adapter.exec_shell, sandbox.container_id, script)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "action execution failed")

    async def _page_screenshot(self, sandbox: SandboxRecord, *, target_id: str | None, image_format: str, quality: int | None) -> bytes:
        version = await self.upstream_browser_version(sandbox)
        ws_url = version.get("webSocketDebuggerUrl")
        if not ws_url:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="page screenshot unavailable")
        async with CdpClient(ws_url) as cdp:
            target = await self._resolve_page_target(cdp, target_id)
            session = await cdp.call("Target.attachToTarget", {"targetId": target, "flatten": True})
            session_id = session["sessionId"]
            await cdp.call("Page.enable", session_id=session_id)
            capture_params: dict[str, Any] = {"format": "jpeg" if image_format == "jpeg" else "png"}
            if image_format == "jpeg" and quality is not None:
                capture_params["quality"] = quality
            result = await cdp.call("Page.captureScreenshot", capture_params, session_id=session_id)
            await cdp.call("Target.detachFromTarget", {"sessionId": session_id})
            return base64.b64decode(result["data"])

    async def _resolve_page_target(self, cdp: CdpClient, target_id: str | None) -> str:
        result = await cdp.call("Target.getTargets")
        targets = [target for target in result.get("targetInfos", []) if target.get("type") == "page"]
        if target_id:
            for target in targets:
                if target["targetId"] == target_id:
                    return target_id
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="target not found")
        preferred = next((target for target in targets if target.get("url") not in {"", "about:blank"}), None)
        if preferred:
            return preferred["targetId"]
        if targets:
            return targets[0]["targetId"]
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no page target available")

    def _window_screenshot(self, sandbox: SandboxRecord) -> bytes:
        window = self._discover_window(sandbox)
        if not sandbox.container_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="sandbox container unavailable")
        crop = f'{window["width"]}x{window["height"]}+{window["x"]}+{window["y"]}'
        proc = docker_adapter.exec_shell(
            sandbox.container_id,
            self._with_display(sandbox, f'import -window root -crop "{crop}" png:-'),
            text=False,
        )
        if proc.returncode != 0:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="window screenshot failed")
        return proc.stdout

    def _browser_version_via_exec(self, sandbox: SandboxRecord) -> dict:
        if not sandbox.container_id:
            return {}
        proc = docker_adapter.exec_shell(
            sandbox.container_id,
            self._with_display(
                sandbox,
                "python3 - <<'PY'\nimport urllib.request\nprint(urllib.request.urlopen('http://127.0.0.1:9222/json/version', timeout=2).read().decode())\nPY",
            ),
        )
        if proc.returncode != 0:
            return {}
        return json.loads(proc.stdout)

    def _normalize_cdp_ws_url(self, sandbox: SandboxRecord, upstream_url: str) -> str:
        parsed = urlparse(upstream_url)
        host = sandbox.runtime.host or parsed.hostname or "127.0.0.1"
        port = sandbox.runtime.cdp_port or parsed.port or 9222
        return urlunparse((parsed.scheme, f"{host}:{port}", parsed.path, "", "", ""))

    def _discover_window(self, sandbox: SandboxRecord) -> dict[str, Any]:
        if not sandbox.container_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="sandbox container unavailable")
        script = self._with_display(sandbox, r"""
wid="$(wmctrl -lx 2>/dev/null | awk 'BEGIN{IGNORECASE=1} $3 ~ /chromium|google-chrome/ {print $1; exit}' | sed 's/^0x//')"
if [ -n "$wid" ]; then
  wid="$((16#$wid))"
fi
if [ -z "$wid" ]; then
  wid="$(xdotool search --onlyvisible --class 'Chromium' 2>/dev/null | head -n1)"
fi
if [ -z "$wid" ]; then
  wid="$(xdotool search --onlyvisible --class 'chromium' 2>/dev/null | head -n1)"
fi
if [ -z "$wid" ]; then
  wid="$(xdotool search --onlyvisible --name 'Chromium' 2>/dev/null | head -n1)"
fi
if [ -z "$wid" ]; then
  wid="$(xdotool search --onlyvisible --name 'Google Chrome' 2>/dev/null | head -n1)"
fi
if [ -z "$wid" ]; then
  echo '{"error":"window not found"}'
  exit 1
fi
eval "$(xdotool getwindowgeometry --shell "$wid")"
title="$(xprop -id "$wid" WM_NAME 2>/dev/null | sed -E 's/.*= \"(.*)\"/\1/' || true)"
printf '{"window_id":"%s","x":%s,"y":%s,"width":%s,"height":%s,"title":%s}\n' \
  "$wid" "${X:-0}" "${Y:-0}" "${WIDTH:-0}" "${HEIGHT:-0}" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$title")"
""")
        proc = docker_adapter.exec_shell(sandbox.container_id, script)
        if proc.returncode != 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="browser window unavailable")
        data = json.loads(proc.stdout.strip())
        if data.get("error"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=data["error"])
        return data

    def _xdotool_script(self, action: BrowserAction, viewport: dict[str, Any]) -> str:
        def coords() -> tuple[int, int] | None:
            if action.x is None or action.y is None:
                return None
            return viewport["active_window"]["x"] + action.x, viewport["active_window"]["y"] + action.y

        absolute = coords()
        button_map = {"left": "1", "middle": "2", "right": "3"}
        if action.type == BrowserActionType.MOVE_TO and absolute:
            return f'xdotool mousemove --sync {absolute[0]} {absolute[1]}'
        if action.type in {BrowserActionType.CLICK, BrowserActionType.DOUBLE_CLICK, BrowserActionType.RIGHT_CLICK}:
            prefix = ""
            if absolute:
                prefix = f'xdotool mousemove --sync {absolute[0]} {absolute[1]} && '
            button = "3" if action.type == BrowserActionType.RIGHT_CLICK else button_map[action.button.value]
            repeat = "2" if action.type == BrowserActionType.DOUBLE_CLICK else "1"
            return f"{prefix}xdotool click --repeat {repeat} {button}"
        if action.type == BrowserActionType.MOUSE_DOWN:
            return f'xdotool mousedown {button_map[action.button.value]}'
        if action.type == BrowserActionType.MOUSE_UP:
            return f'xdotool mouseup {button_map[action.button.value]}'
        if action.type == BrowserActionType.DRAG_TO and absolute:
            return f'xdotool mousemove --sync {absolute[0]} {absolute[1]}'
        if action.type == BrowserActionType.SCROLL:
            direction = "4" if (action.delta_y or 0) > 0 else "5"
            repeat = max(abs(action.delta_y or 1), 1)
            return f'xdotool click --repeat {repeat} {direction}'
        if action.type == BrowserActionType.TYPE_TEXT:
            text = json.dumps(action.text or "")
            return f"python3 - <<'PY'\nimport json, subprocess\nsubprocess.run(['xdotool','type','--delay','20',json.loads({text!r})], check=True)\nPY"
        if action.type == BrowserActionType.KEY_PRESS:
            return f"xdotool key {json.dumps(action.key or '')}"
        if action.type == BrowserActionType.HOTKEY:
            combo = "+".join(action.keys)
            return f"xdotool key {json.dumps(combo)}"
        raise RuntimeError(f"unsupported action type: {action.type}")


browser_service = BrowserService()
