import asyncio
import secrets
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from threading import Lock

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
import websockets

from app.auth.tickets import issue_ticket, verify_ticket
from app.config import get_settings
from app.deps import get_base_url, get_current_subject, require_sandbox
from app.models.sandbox import SandboxStatus
from app.schemas.common import ApiEnvelope, ok
from app.schemas.sandbox import CreateVncTicketRequest, CreateVncTicketResponse

router = APIRouter(prefix="/sandbox/{sandbox_id}/vnc", tags=["vnc"])
_vnc_sessions: dict[str, dict[str, object]] = {}
_vnc_sessions_lock = Lock()


def _canonical_sandbox_id(sandbox, fallback: str) -> str:
    return str(getattr(sandbox, "id", fallback))


def _prune_vnc_sessions(now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc)
    expired = [
        session_id
        for session_id, session in _vnc_sessions.items()
        if current > session["expires_at"]
    ]
    for session_id in expired:
        _vnc_sessions.pop(session_id, None)


def _create_vnc_session(sandbox_id: str) -> str:
    session_id = secrets.token_urlsafe(24)
    with _vnc_sessions_lock:
        _prune_vnc_sessions()
        _vnc_sessions[session_id] = {
            "sandbox_id": sandbox_id,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        }
    return session_id


def _validate_vnc_session(session_id: str | None, sandbox_id: str) -> None:
    if not session_id:
        raise HTTPException(status_code=401, detail="missing vnc session")
    with _vnc_sessions_lock:
        session = _vnc_sessions.get(session_id)
        if session is None or session["sandbox_id"] != sandbox_id:
            _prune_vnc_sessions()
            raise HTTPException(status_code=403, detail="invalid vnc session")
        if datetime.now(timezone.utc) > session["expires_at"]:
            _vnc_sessions.pop(session_id, None)
            _prune_vnc_sessions()
            raise HTTPException(status_code=401, detail="expired vnc session")
        _prune_vnc_sessions()


def _ensure_vnc_proxy_ready(sandbox) -> None:
    runtime_error = sandbox.metadata.get("runtime_error")
    if sandbox.status == SandboxStatus.FAILED:
        detail = f"vnc unavailable: {runtime_error}" if runtime_error else "vnc unavailable: sandbox failed"
        raise HTTPException(status_code=409, detail=detail)
    if sandbox.status == SandboxStatus.STOPPED or sandbox.container_id is None:
        raise HTTPException(status_code=409, detail="vnc unavailable: sandbox is not running")


def _build_vnc_entry_url(base_url: str, sandbox_id: str, ticket: str) -> str:
    return f"{base_url}/sandbox/{sandbox_id}/vnc/?ticket={ticket}"


@router.post("/apply", response_model=ApiEnvelope[CreateVncTicketResponse])
async def create_vnc_ticket(
    request_context: Request,
    sandbox_id: str,
    request: CreateVncTicketRequest | None = None,
    subject: str = Depends(get_current_subject),
    sandbox=Depends(require_sandbox),
) -> ApiEnvelope[CreateVncTicketResponse]:
    settings = get_settings()
    ticket_request = request or CreateVncTicketRequest()
    canonical_id = _canonical_sandbox_id(sandbox, sandbox_id)
    try:
        ticket = issue_ticket(
            sandbox_id=canonical_id,
            subject=subject,
            ticket_type="vnc",
            scope="connect",
            ttl_sec=ticket_request.ttl_sec,
            mode=ticket_request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    expires_at = None
    if ticket_request.mode != "permanent":
        ttl_sec = ticket_request.ttl_sec or settings.ticket_ttl_sec
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)
    response = CreateVncTicketResponse(
        ticket=ticket,
        vnc_url=_build_vnc_entry_url(get_base_url(request_context), canonical_id, ticket),
        mode=ticket_request.mode,
        ttl_sec=None if ticket_request.mode == "permanent" else (ticket_request.ttl_sec or settings.ticket_ttl_sec),
        expires_at=expires_at,
    )
    return ok(response)


@router.get("/", response_class=HTMLResponse)
async def vnc_entry(sandbox_id: str, ticket: str = Query(...), sandbox=Depends(require_sandbox)) -> Response:
    canonical_id = _canonical_sandbox_id(sandbox, sandbox_id)
    verify_ticket(ticket, sandbox_id=canonical_id, ticket_type="vnc", scope="connect", consume=True)
    session_id = _create_vnc_session(canonical_id)
    query = f"path=/sandbox/{canonical_id}/vnc/websockify&resize=scale&autoconnect=true"
    response = RedirectResponse(url=f"/sandbox/{canonical_id}/vnc/vnc.html?{query}", status_code=302)
    response.set_cookie("vnc_session", session_id, httponly=True, max_age=600, samesite="lax")
    return response


@router.get("/{asset_path:path}")
async def vnc_asset_proxy(
    sandbox_id: str,
    asset_path: str,
    sandbox=Depends(require_sandbox),
    vnc_session: str | None = Cookie(default=None),
) -> Response:
    _validate_vnc_session(vnc_session, _canonical_sandbox_id(sandbox, sandbox_id))
    _ensure_vnc_proxy_ready(sandbox)
    return await _proxy_vnc_asset(sandbox, asset_path or "vnc.html")


async def _proxy_vnc_asset(sandbox, asset_path: str, query: str | None = None) -> Response:
    url = f"http://{sandbox.runtime.host}:{sandbox.runtime.vnc_port}/{asset_path}"
    if query:
        url = f"{url}?{query}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.get(url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="vnc asset proxy unavailable") from exc
    return Response(content=upstream.content, media_type=upstream.headers.get("content-type"))


@router.websocket("/websockify")
async def vnc_websockify_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    sandbox = require_sandbox(sandbox_id)
    canonical_id = _canonical_sandbox_id(sandbox, sandbox_id)
    session_id = websocket.cookies.get("vnc_session")
    try:
        _validate_vnc_session(session_id, canonical_id)
    except HTTPException:
        await websocket.close(code=4401, reason="invalid vnc session")
        return
    try:
        _ensure_vnc_proxy_ready(sandbox)
    except HTTPException as exc:
        await websocket.close(code=1011, reason=str(exc.detail))
        return
    await websocket.accept()
    upstream_url = f"ws://{sandbox.runtime.host}:{sandbox.runtime.vnc_port}/websockify"
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
        await websocket.close(code=1011, reason="vnc proxy error")
