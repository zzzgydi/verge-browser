from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from threading import Lock

import websockets
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect

from app.auth.tickets import issue_ticket, verify_ticket
from app.config import get_settings
from app.deps import get_base_url, get_current_subject, require_sandbox
from app.models.sandbox import SandboxKind
from app.schemas.common import ApiEnvelope, ok
from app.schemas.sandbox import CreateSessionTicketRequest, CreateSessionTicketResponse
from app.services.session import session_service

router = APIRouter(prefix="/sandbox/{sandbox_id}/session", tags=["session"])
_sessions: dict[str, dict[str, object]] = {}
_sessions_lock = Lock()
logger = logging.getLogger(__name__)


def _canonical_sandbox_id(sandbox, fallback: str) -> str:
    return str(getattr(sandbox, "id", fallback))


def _prune_sessions(now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc)
    expired = [session_id for session_id, payload in _sessions.items() if current > payload["expires_at"]]
    for session_id in expired:
        _sessions.pop(session_id, None)


def _create_session(sandbox_id: str) -> str:
    session_id = secrets.token_urlsafe(24)
    with _sessions_lock:
        _prune_sessions()
        _sessions[session_id] = {
            "sandbox_id": sandbox_id,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        }
    return session_id


def _validate_session(session_id: str | None, sandbox_id: str) -> None:
    if not session_id:
        raise HTTPException(status_code=401, detail="missing sandbox session")
    with _sessions_lock:
        session = _sessions.get(session_id)
        if session is None or session["sandbox_id"] != sandbox_id:
            _prune_sessions()
            raise HTTPException(status_code=403, detail="invalid sandbox session")
        if datetime.now(timezone.utc) > session["expires_at"]:
            _sessions.pop(session_id, None)
            _prune_sessions()
            raise HTTPException(status_code=401, detail="expired sandbox session")
        _prune_sessions()


@router.post("/apply", response_model=ApiEnvelope[CreateSessionTicketResponse], dependencies=[Depends(get_current_subject)])
async def create_session_ticket(
    request_context: Request,
    sandbox_id: str,
    request: CreateSessionTicketRequest | None = None,
    subject: str = Depends(get_current_subject),
    sandbox=Depends(require_sandbox),
) -> ApiEnvelope[CreateSessionTicketResponse]:
    settings = get_settings()
    ticket_request = request or CreateSessionTicketRequest()
    canonical_id = _canonical_sandbox_id(sandbox, sandbox_id)
    try:
        ticket = issue_ticket(
            sandbox_id=canonical_id,
            subject=subject,
            ticket_type="session",
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
    return ok(
        CreateSessionTicketResponse(
            ticket=ticket,
            session_url=session_service.build_entry_url(
                base_url=get_base_url(request_context),
                sandbox_id=canonical_id,
                ticket=ticket,
            ),
            mode=ticket_request.mode,
            ttl_sec=None if ticket_request.mode == "permanent" else (ticket_request.ttl_sec or settings.ticket_ttl_sec),
            expires_at=expires_at,
        )
    )


@router.get("/")
async def session_entry(
    request: Request,
    sandbox_id: str,
    ticket: str = Query(...),
    sandbox=Depends(require_sandbox),
) -> Response:
    del request
    canonical_id = _canonical_sandbox_id(sandbox, sandbox_id)
    verify_ticket(ticket, sandbox_id=canonical_id, ticket_type="session", scope="connect", consume=True)
    session_id = _create_session(canonical_id)
    if sandbox.kind == SandboxKind.XPRA:
        response = await session_service.proxy_http(sandbox)
    else:
        from fastapi.responses import RedirectResponse

        response = RedirectResponse(url=session_service.browser_session_redirect_url(sandbox), status_code=302)
    response.set_cookie(
        "sandbox_session",
        session_id,
        httponly=True,
        max_age=600,
        samesite="lax",
        path=f"/sandbox/{canonical_id}/session",
    )
    return response


@router.get("/{asset_path:path}")
async def session_asset_proxy(
    request: Request,
    sandbox_id: str,
    asset_path: str,
    sandbox=Depends(require_sandbox),
    sandbox_session: str | None = Cookie(default=None),
) -> Response:
    _validate_session(sandbox_session, _canonical_sandbox_id(sandbox, sandbox_id))
    return await session_service.proxy_http(sandbox, asset_path, request.url.query)


async def _session_ws_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    sandbox = require_sandbox(sandbox_id)
    canonical_id = _canonical_sandbox_id(sandbox, sandbox_id)
    if sandbox.kind != SandboxKind.XPRA:
        await websocket.close(code=4404, reason="session websocket unavailable for sandbox kind")
        return
    try:
        _validate_session(websocket.cookies.get("sandbox_session"), canonical_id)
    except HTTPException:
        await websocket.close(code=4401, reason="invalid sandbox session")
        return

    requested_subprotocols = [
        item.strip()
        for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if item.strip()
    ]
    client_subprotocol = "binary" if "binary" in requested_subprotocols else None
    upstream_url = session_service.upstream_ws_url(sandbox, str(websocket.query_params))
    try:
        upstream = await websockets.connect(
            upstream_url,
            subprotocols=["binary"],
            max_size=None,
            max_queue=None,
            ping_interval=20,
            ping_timeout=20,
        )
    except Exception:
        logger.exception("session websocket upstream connect failed for sandbox %s", canonical_id)
        await websocket.close(code=1011, reason="session proxy unavailable")
        return

    await websocket.accept(subprotocol=client_subprotocol)
    try:
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
        done, pending = await asyncio.wait({client_task, upstream_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        for task in done:
            task.result()
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("session websocket proxy failed for sandbox %s", canonical_id)
        await websocket.close(code=1011, reason="session proxy error")
    finally:
        await upstream.close()


@router.websocket("/")
async def session_ws_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    await _session_ws_proxy(websocket, sandbox_id)


@router.websocket("/ws")
async def session_ws_legacy_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    await _session_ws_proxy(websocket, sandbox_id)


@router.websocket("/websockify")
async def session_websockify_proxy(websocket: WebSocket, sandbox_id: str) -> None:
    sandbox = require_sandbox(sandbox_id)
    canonical_id = _canonical_sandbox_id(sandbox, sandbox_id)
    if sandbox.kind != SandboxKind.XVFB_VNC:
        await websocket.close(code=4404, reason="websockify unavailable for sandbox kind")
        return
    try:
        _validate_session(websocket.cookies.get("sandbox_session"), canonical_id)
    except HTTPException:
        await websocket.close(code=4401, reason="invalid sandbox session")
        return

    await websocket.accept()
    upstream_url = session_service.upstream_ws_url(sandbox, str(websocket.query_params))
    try:
        upstream = await websockets.connect(
            upstream_url,
            max_size=None,
            max_queue=None,
            ping_interval=20,
            ping_timeout=20,
        )
    except Exception:
        logger.exception("session websockify upstream connect failed for sandbox %s", canonical_id)
        await websocket.close(code=1011, reason="session proxy unavailable")
        return

    try:
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
        done, pending = await asyncio.wait({client_task, upstream_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        for task in done:
            task.result()
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("session websockify proxy failed for sandbox %s", canonical_id)
        await websocket.close(code=1011, reason="session proxy error")
    finally:
        await upstream.close()
