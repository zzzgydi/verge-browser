from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.deps import get_base_url, get_current_subject, require_sandbox
from app.schemas.sandbox import BrowserInfo, CreateSandboxRequest, RestartBrowserRequest, SandboxResponse, ViewportInfo
from app.services.browser import browser_service
from app.services.lifecycle import lifecycle_service

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])


def _to_response(request: Request, sandbox) -> SandboxResponse:
    base_url = get_base_url(request)
    ws_base_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    return SandboxResponse(
        id=sandbox.id,
        status=sandbox.status,
        created_at=sandbox.created_at,
        container_id=sandbox.container_id,
        browser=BrowserInfo(
            cdp_url=f"{ws_base_url}/sandboxes/{sandbox.id}/browser/cdp/browser",
            vnc_entry_base_url=f"{base_url}/sandboxes/{sandbox.id}/vnc/",
            vnc_ticket_endpoint=f"{base_url}/sandboxes/{sandbox.id}/vnc/tickets",
            viewport=ViewportInfo(width=1280, height=1024),
        ),
    )


@router.post("", response_model=SandboxResponse, status_code=status.HTTP_201_CREATED)
async def create_sandbox(
    request: Request,
    payload: CreateSandboxRequest,
    subject: str = Depends(get_current_subject),
) -> SandboxResponse:
    del subject
    sandbox = await lifecycle_service.create(payload)
    version = await browser_service.browser_version(sandbox)
    response = _to_response(request, sandbox)
    response.browser.browser_version = version.get("Browser")
    response.browser.protocol_version = version.get("Protocol-Version")
    return response


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(request: Request, sandbox=Depends(require_sandbox)) -> SandboxResponse:
    version = await browser_service.browser_version(sandbox)
    response = _to_response(request, sandbox)
    response.browser.browser_version = version.get("Browser")
    response.browser.protocol_version = version.get("Protocol-Version")
    return response


@router.delete("/{sandbox_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sandbox(sandbox_id: str) -> Response:
    deleted = lifecycle_service.destroy(sandbox_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sandbox not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{sandbox_id}/browser/restart")
async def restart_browser(
    sandbox_id: str,
    payload: RestartBrowserRequest,
    sandbox=Depends(require_sandbox),
) -> dict[str, object]:
    del sandbox, payload
    ok = lifecycle_service.restart_browser(sandbox_id)
    return {"ok": ok, "level": "hard"}
