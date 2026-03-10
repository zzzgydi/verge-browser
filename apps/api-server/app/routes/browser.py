import asyncio

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
import websockets

from app.deps import get_base_url, get_ws_subject, require_sandbox
from app.schemas.browser import BrowserActionsRequest, BrowserActionsResponse, ScreenshotEnvelope, ScreenshotType
from app.services.browser import browser_service

router = APIRouter(prefix="/sandboxes/{sandbox_id}", tags=["browser"])


@router.get("/browser/info")
async def browser_info(sandbox=Depends(require_sandbox)) -> dict[str, object]:
    version = await browser_service.browser_version(sandbox)
    viewport = browser_service.get_viewport(sandbox)
    return {
        "browser_version": version.get("Browser"),
        "protocol_version": version.get("Protocol-Version"),
        "web_socket_debugger_url_present": bool(version.get("webSocketDebuggerUrl")),
        "viewport": viewport["window_viewport"],
    }


@router.get("/browser/viewport")
async def browser_viewport(sandbox=Depends(require_sandbox)) -> dict[str, object]:
    return browser_service.get_viewport(sandbox)


@router.get("/browser/screenshot", response_model=ScreenshotEnvelope)
async def screenshot(
    type: ScreenshotType = Query(default=ScreenshotType.window),
    format: str = Query(default="png", pattern="^(png|jpeg|webp)$"),
    target_id: str | None = Query(default=None),
    sandbox=Depends(require_sandbox),
) -> ScreenshotEnvelope:
    return await browser_service.screenshot(sandbox, type, format, target_id=target_id)


@router.post("/browser/actions", response_model=BrowserActionsResponse)
async def browser_actions(payload: BrowserActionsRequest, sandbox=Depends(require_sandbox)) -> BrowserActionsResponse:
    return await browser_service.execute_actions(sandbox, payload)


@router.get("/browser/cdp/info")
async def cdp_info(request: Request, sandbox_id: str, sandbox=Depends(require_sandbox)) -> dict[str, object]:
    version = await browser_service.browser_version(sandbox)
    base_url = get_base_url(request).replace("http://", "ws://").replace("https://", "wss://")
    return {
        "cdp_url": f"{base_url}/sandboxes/{sandbox_id}/browser/cdp/browser",
        "browser_version": version.get("Browser"),
        "protocol_version": version.get("Protocol-Version"),
    }


@router.websocket("/browser/cdp/browser")
async def cdp_browser_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    sandbox = require_sandbox(sandbox_id)
    await get_ws_subject(websocket)
    await websocket.accept()
    version = await browser_service.browser_version(sandbox)
    upstream_url = version.get("webSocketDebuggerUrl")
    if not upstream_url:
        await websocket.close(code=1011, reason="browser unavailable")
        return

    try:
        async with websockets.connect(upstream_url, ping_interval=20, ping_timeout=20, max_queue=100) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if "text" in message:
                        await upstream.send(message["text"])
                    elif "bytes" in message:
                        await upstream.send(message["bytes"])
                    else:
                        break

            async def upstream_to_client() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011, reason="browser proxy error")
