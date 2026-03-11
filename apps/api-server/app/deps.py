from fastapi import Header, HTTPException, Request, WebSocket, status

from app.config import get_settings
from app.services.registry import registry


def get_current_subject(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authorization header")
    if token != get_settings().admin_auth_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return "admin"


def require_sandbox(sandbox_id: str):
    sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
    if sandbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sandbox not found")
    return sandbox


async def get_ws_subject(websocket: WebSocket) -> str:
    auth = websocket.headers.get("authorization")
    if not auth:
        await websocket.close(code=4401, reason="missing authorization header")
        raise RuntimeError("missing websocket auth")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        await websocket.close(code=4401, reason="invalid authorization header")
        raise RuntimeError("invalid websocket auth")
    if token != get_settings().admin_auth_token:
        await websocket.close(code=4401, reason="invalid token")
        raise RuntimeError("invalid websocket auth")
    return "admin"


def get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")
