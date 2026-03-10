import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import websockets

from app.auth.tickets import issue_ticket, verify_ticket
from app.deps import get_current_subject, require_sandbox

router = APIRouter(prefix="/sandboxes/{sandbox_id}/vnc", tags=["vnc"])
_vnc_sessions: dict[str, dict[str, object]] = {}


def _create_vnc_session(sandbox_id: str) -> str:
    session_id = secrets.token_urlsafe(24)
    _vnc_sessions[session_id] = {
        "sandbox_id": sandbox_id,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return session_id


def _validate_vnc_session(session_id: str | None, sandbox_id: str) -> None:
    if not session_id:
        raise HTTPException(status_code=401, detail="missing vnc session")
    session = _vnc_sessions.get(session_id)
    if session is None or session["sandbox_id"] != sandbox_id:
        raise HTTPException(status_code=403, detail="invalid vnc session")
    if datetime.now(timezone.utc) > session["expires_at"]:
        _vnc_sessions.pop(session_id, None)
        raise HTTPException(status_code=401, detail="expired vnc session")


@router.post("/tickets")
async def create_vnc_ticket(sandbox_id: str, subject: str = Depends(get_current_subject)) -> dict[str, str]:
    ticket = issue_ticket(sandbox_id=sandbox_id, subject=subject, ticket_type="vnc", scope="connect")
    return {"ticket": ticket}


@router.get("/", response_class=HTMLResponse)
async def vnc_entry(sandbox_id: str, ticket: str = Query(...), sandbox=Depends(require_sandbox)) -> HTMLResponse:
    verify_ticket(ticket, sandbox_id=sandbox_id, ticket_type="vnc", scope="connect", consume=True)
    session_id = _create_vnc_session(sandbox_id)
    response = await _proxy_vnc_asset(sandbox, "vnc.html", query=f"path=sandboxes/{sandbox_id}/vnc/websockify")
    response.set_cookie("vnc_session", session_id, httponly=True, max_age=600, samesite="lax")
    return response


@router.get("/{asset_path:path}")
async def vnc_asset_proxy(
    sandbox_id: str,
    asset_path: str,
    sandbox=Depends(require_sandbox),
    vnc_session: str | None = Cookie(default=None),
) -> Response:
    _validate_vnc_session(vnc_session, sandbox_id)
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
    session_id = websocket.cookies.get("vnc_session")
    try:
        _validate_vnc_session(session_id, sandbox_id)
    except HTTPException:
        await websocket.close(code=4401, reason="invalid vnc session")
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

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011, reason="vnc proxy error")
