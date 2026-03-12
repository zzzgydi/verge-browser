import asyncio
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
import websockets

from app.auth.tickets import verify_ticket
from app.deps import get_base_url, get_current_subject, require_sandbox
from app.schemas.browser import BrowserActionsRequest, BrowserActionsResponse, ScreenshotEnvelope, ScreenshotRequest
from app.schemas.common import ApiEnvelope, ok
from app.schemas.sandbox import CreateCdpTicketRequest, CreateCdpTicketResponse
from app.services.cdp_access import canonical_sandbox_id, issue_cdp_ticket_response
from app.services.browser import browser_service

router = APIRouter(prefix="/sandbox/{sandbox_id}", tags=["browser"])


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
    base_url = get_base_url(request).replace("http://", "ws://").replace("https://", "wss://")
    canonical_id = canonical_sandbox_id(sandbox, sandbox_id)
    ticket = issue_cdp_ticket_response(base_url=base_url, sandbox_id=canonical_id, subject=subject, request=payload)
    return ok(ticket)


@router.websocket("/cdp/browser")
async def cdp_browser_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    sandbox = require_sandbox(sandbox_id)
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
