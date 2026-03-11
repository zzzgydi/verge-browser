from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.deps import get_base_url, get_current_subject, require_sandbox
from app.models.sandbox import SandboxStatus
from app.schemas.sandbox import BrowserInfo, CreateSandboxRequest, RestartBrowserRequest, SandboxResponse, UpdateSandboxRequest, ViewportInfo
from app.services.browser import browser_service
from app.services.lifecycle import lifecycle_service
from app.services.registry import registry

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"], dependencies=[Depends(get_current_subject)])


def _to_response(request: Request, sandbox) -> SandboxResponse:
    base_url = get_base_url(request)
    ws_base_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    viewport = ViewportInfo(width=sandbox.width, height=sandbox.height)
    return SandboxResponse(
        id=sandbox.id,
        alias=sandbox.alias,
        status=sandbox.status,
        created_at=sandbox.created_at,
        updated_at=sandbox.updated_at,
        last_active_at=sandbox.last_active_at,
        width=sandbox.width,
        height=sandbox.height,
        metadata=sandbox.metadata,
        container_id=sandbox.container_id,
        browser=BrowserInfo(
            cdp_url=f"{ws_base_url}/sandboxes/{sandbox.id}/browser/cdp/browser",
            vnc_entry_base_url=f"{base_url}/sandboxes/{sandbox.id}/vnc/",
            vnc_ticket_endpoint=f"{base_url}/sandboxes/{sandbox.id}/vnc/tickets",
            viewport=viewport,
        ),
    )


async def _enrich_response(request: Request, sandbox) -> SandboxResponse:
    response = _to_response(request, sandbox)
    should_probe_browser = sandbox.container_id is not None and sandbox.status in {
        SandboxStatus.STARTING,
        SandboxStatus.RUNNING,
        SandboxStatus.DEGRADED,
    }
    if not should_probe_browser:
        return response
    version = await browser_service.browser_version(sandbox)
    response.browser.browser_version = version.get("Browser")
    response.browser.protocol_version = version.get("Protocol-Version")
    return response


@router.get("", response_model=list[SandboxResponse])
async def list_sandboxes(request: Request, subject: str = Depends(get_current_subject)) -> list[SandboxResponse]:
    del subject
    responses: list[SandboxResponse] = []
    for sandbox in registry.all():
        responses.append(await _enrich_response(request, sandbox))
    responses.sort(key=lambda item: item.created_at, reverse=True)
    return responses


@router.post("", response_model=SandboxResponse, status_code=status.HTTP_201_CREATED)
async def create_sandbox(
    request: Request,
    payload: CreateSandboxRequest,
    subject: str = Depends(get_current_subject),
) -> SandboxResponse:
    del subject
    sandbox = await lifecycle_service.create(payload)
    return await _enrich_response(request, sandbox)


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(request: Request, sandbox=Depends(require_sandbox)) -> SandboxResponse:
    return await _enrich_response(request, sandbox)


@router.patch("/{sandbox_id}", response_model=SandboxResponse)
async def update_sandbox(
    request: Request,
    sandbox_id: str,
    payload: UpdateSandboxRequest,
    subject: str = Depends(get_current_subject),
) -> SandboxResponse:
    del subject
    sandbox = lifecycle_service.update(sandbox_id, payload)
    if sandbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sandbox not found")
    return await _enrich_response(request, sandbox)


@router.delete("/{sandbox_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sandbox(sandbox_id: str) -> Response:
    deleted = lifecycle_service.destroy(sandbox_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sandbox not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{sandbox_id}/pause")
async def pause_sandbox(sandbox_id: str) -> dict[str, bool]:
    ok = lifecycle_service.pause(sandbox_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sandbox not found")
    return {"ok": True}


@router.post("/{sandbox_id}/resume")
async def resume_sandbox(sandbox_id: str) -> dict[str, bool]:
    sandbox = require_sandbox(sandbox_id)
    if sandbox.status != SandboxStatus.STOPPED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="sandbox is not stopped")
    ok = await lifecycle_service.resume(sandbox_id)
    return {"ok": ok}


@router.post("/{sandbox_id}/browser/restart")
async def restart_browser(
    sandbox_id: str,
    payload: RestartBrowserRequest,
    sandbox=Depends(require_sandbox),
) -> dict[str, object]:
    del sandbox, payload
    ok = await lifecycle_service.restart_browser(sandbox_id)
    return {"ok": ok, "level": "hard"}
