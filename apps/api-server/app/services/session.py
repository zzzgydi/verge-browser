from __future__ import annotations

from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Response, status

from app.models.sandbox import SandboxKind, SandboxRecord, SandboxStatus


class SessionService:
    xpra_ws_path = "/"
    xvfb_ws_path = "/websockify"

    def build_entry_url(self, *, base_url: str, sandbox_id: str, ticket: str) -> str:
        return f"{base_url}/sandbox/{sandbox_id}/session/?{urlencode({'ticket': ticket})}"

    def upstream_http_url(self, sandbox: SandboxRecord, asset_path: str = "", query: str | None = None) -> str:
        normalized_path = asset_path.lstrip("/")
        base = f"http://{sandbox.runtime.host}:{sandbox.runtime.session_port}"
        url = f"{base}/{normalized_path}" if normalized_path else f"{base}/"
        if query:
            url = f"{url}?{query}"
        return url

    def upstream_ws_url(self, sandbox: SandboxRecord, query: str | None = None) -> str:
        path = self.xpra_ws_path if sandbox.kind == SandboxKind.XPRA else self.xvfb_ws_path
        url = f"ws://{sandbox.runtime.host}:{sandbox.runtime.session_port}{path}"
        if query:
            url = f"{url}?{query}"
        return url

    def browser_session_redirect_url(self, sandbox: SandboxRecord) -> str:
        if sandbox.kind == SandboxKind.XPRA:
            return ""
        query = urlencode(
            {
                "path": f"/sandbox/{sandbox.id}/session/websockify",
                "resize": "scale",
                "autoconnect": "true",
            }
        )
        return f"/sandbox/{sandbox.id}/session/vnc.html?{query}"

    async def proxy_http(self, sandbox: SandboxRecord, asset_path: str = "", query: str | None = None) -> Response:
        if sandbox.status in {SandboxStatus.FAILED, SandboxStatus.STOPPED} or sandbox.container_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="session unavailable")
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                upstream = await client.get(self.upstream_http_url(sandbox, asset_path, query))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="session proxy unavailable") from exc
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )


session_service = SessionService()
