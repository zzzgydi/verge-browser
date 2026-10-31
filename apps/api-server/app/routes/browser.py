import asyncio
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
import websockets

from app.auth.tickets import verify_ticket
from app.deps import get_base_url, get_current_subject, require_sandbox
from app.models.sandbox import BrowserEngine, SandboxStatus
from app.schemas.command import BrowserCommand
from app.services.docker_adapter import docker_adapter
from app.schemas.browser import BrowserActionsRequest, BrowserActionsResponse, ScreenshotEnvelope, ScreenshotRequest
from app.schemas.common import ApiEnvelope, ok
from app.schemas.sandbox import CreateCdpTicketRequest, CreateCdpTicketResponse
from app.services.cdp_access import canonical_sandbox_id, issue_cdp_ticket_response
from app.services.browser import browser_service

router = APIRouter(prefix="/sandbox/{sandbox_id}", tags=["browser"])


@router.post("/browser/command")
async def browser_command(payload: BrowserCommand, subject: str = Depends(get_current_subject), sandbox=Depends(require_sandbox)):
    if sandbox.browser_engine != BrowserEngine.CAMOUFOX:
        raise HTTPException(status_code=409, detail="Use agent-browser with this sandbox's ticketed CDP URL")
    if sandbox.status != SandboxStatus.RUNNING or not sandbox.container_id:
        raise HTTPException(status_code=409, detail="Sandbox is not running")
    try:
        data = await asyncio.to_thread(docker_adapter.camoufox_control, sandbox.container_id, payload.worker_command())
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ok(data)


@router.post("/browser/screenshot", response_model=ApiEnvelope[ScreenshotEnvelope])
async def screenshot(
    payload: ScreenshotRequest,
    subject: str = Depends(get_current_subject),
    sandbox=Depends(require_sandbox),
) -> ApiEnvelope[ScreenshotEnvelope]:
    del subject
    return ok(
        await browser_service.screenshot(
            sandbox,
            payload.type,
            payload.format,
            target_id=payload.target_id,
            quality=payload.quality,
        )
    )


@router.post("/browser/actions", response_model=ApiEnvelope[BrowserActionsResponse])
async def browser_actions(
    payload: BrowserActionsRequest,
    subject: str = Depends(get_current_subject),
    sandbox=Depends(require_sandbox),
) -> ApiEnvelope[BrowserActionsResponse]:
    del subject
    return ok(await browser_service.execute_actions(sandbox, payload))


@router.post("/cdp/apply", response_model=ApiEnvelope[CreateCdpTicketResponse])
async def cdp_apply(
    request: Request,
    sandbox_id: str,
    payload: CreateCdpTicketRequest | None = None,
    subject: str = Depends(get_current_subject),
    sandbox=Depends(require_sandbox),
) -> ApiEnvelope[CreateCdpTicketResponse]:
    if sandbox.browser_engine == BrowserEngine.CAMOUFOX:
        raise HTTPException(status_code=409, detail="Camoufox has no CDP; use verge-browser browser commands")
    base_url = get_base_url(request).replace("http://", "ws://").replace("https://", "wss://")
    canonical_id = canonical_sandbox_id(sandbox, sandbox_id)
    ticket = issue_cdp_ticket_response(base_url=base_url, sandbox_id=canonical_id, subject=subject, request=payload)
    return ok(ticket)


@router.websocket("/cdp/browser")
async def cdp_browser_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    sandbox = require_sandbox(sandbox_id)
    if sandbox.browser_engine == BrowserEngine.CAMOUFOX:
        await websocket.close(code=4409, reason="Camoufox does not support CDP")
        return
    canonical_id = canonical_sandbox_id(sandbox, sandbox_id)
    ticket = websocket.query_params.get("ticket")
    try:
        verify_ticket(ticket or "", sandbox_id=canonical_id, ticket_type="cdp", scope="connect", consume=True)
    except HTTPException:
        await websocket.close(code=4401, reason="invalid cdp ticket")
        return
    await websocket.accept()
    version = await browser_service.upstream_browser_version(sandbox)
    upstream_url = version.get("webSocketDebuggerUrl")
    if not upstream_url:
        await websocket.close(code=1011, reason="browser unavailable")
        return

    try:
        # Full accessibility trees and CDP screenshots can exceed websockets' 1 MiB default.
        async with websockets.connect(
            upstream_url, ping_interval=20, ping_timeout=20, max_queue=100, max_size=16 * 1024 * 1024,
        ) as upstream:
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

            client_task = asyncio.create_task(client_to_upstream())
            upstream_task = asyncio.create_task(upstream_to_client())
            done, pending = await asyncio.wait(
                {client_task, upstream_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011, reason="browser proxy error")
