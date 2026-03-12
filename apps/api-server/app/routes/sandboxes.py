import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.deps import get_current_subject, require_sandbox
from app.models.sandbox import SandboxStatus
from app.schemas.common import ApiEnvelope, ok
from app.schemas.sandbox import ActiveWindowInfo, BrowserRuntimeInfo, BrowserViewportRect, CreateSandboxRequest, RestartBrowserRequest, SandboxResponse, UpdateSandboxRequest, ViewportInfo
from app.services.browser import browser_service
from app.services.lifecycle import lifecycle_service
from app.services.registry import registry

router = APIRouter(prefix="/sandbox", tags=["sandboxes"], dependencies=[Depends(get_current_subject)])
logger = logging.getLogger(__name__)


def _to_response(request: Request, sandbox, subject: str) -> SandboxResponse:
    del request, subject
    viewport = ViewportInfo(width=sandbox.width, height=sandbox.height)
    return SandboxResponse(
        id=sandbox.id,
        alias=sandbox.alias,
        kind=sandbox.kind,
        status=sandbox.status,
        created_at=sandbox.created_at,
        updated_at=sandbox.updated_at,
        last_active_at=sandbox.last_active_at,
        width=sandbox.width,
        height=sandbox.height,
        metadata=sandbox.metadata,
        container_id=sandbox.container_id,
        browser=BrowserRuntimeInfo(viewport=viewport),
    )


async def _enrich_response(request: Request, sandbox, subject: str) -> SandboxResponse:
    response = _to_response(request, sandbox, subject)
    should_probe_browser = sandbox.container_id is not None and sandbox.status in {
        SandboxStatus.STARTING,
        SandboxStatus.RUNNING,
        SandboxStatus.DEGRADED,
    }
    if not should_probe_browser:
        return response
    try:
        version = await browser_service.browser_version(sandbox)
    except Exception:
        logger.warning("browser version probe failed for sandbox %s", sandbox.id, exc_info=True)
        version = {}
    response.browser.browser_version = version.get("Browser")
    response.browser.protocol_version = version.get("Protocol-Version")
    response.browser.web_socket_debugger_url_present = bool(version.get("webSocketDebuggerUrl"))
    try:
        viewport = browser_service.get_viewport(sandbox)
    except Exception:
        logger.info("viewport probe not ready for sandbox %s", sandbox.id)
        return response
    response.browser.window_viewport = BrowserViewportRect(**viewport["window_viewport"])
    response.browser.page_viewport = BrowserViewportRect(**viewport["page_viewport"])
    response.browser.active_window = ActiveWindowInfo(**viewport["active_window"])
    return response


@router.get("", response_model=ApiEnvelope[list[SandboxResponse]])
async def list_sandboxes(request: Request, subject: str = Depends(get_current_subject)) -> ApiEnvelope[list[SandboxResponse]]:
    responses: list[SandboxResponse] = []
    for sandbox in registry.all():
        responses.append(await _enrich_response(request, sandbox, subject))
    responses.sort(key=lambda item: item.created_at, reverse=True)
    return ok(responses)


@router.post("", response_model=ApiEnvelope[SandboxResponse], status_code=status.HTTP_201_CREATED)
async def create_sandbox(
    request: Request,
    payload: CreateSandboxRequest,
    subject: str = Depends(get_current_subject),
) -> ApiEnvelope[SandboxResponse]:
    sandbox = await lifecycle_service.create(payload)
    return ok(await _enrich_response(request, sandbox, subject), message="sandbox created")


@router.get("/{sandbox_id}", response_model=ApiEnvelope[SandboxResponse])
async def get_sandbox(request: Request, subject: str = Depends(get_current_subject), sandbox=Depends(require_sandbox)) -> ApiEnvelope[SandboxResponse]:
    return ok(await _enrich_response(request, sandbox, subject))


@router.patch("/{sandbox_id}", response_model=ApiEnvelope[SandboxResponse])
async def update_sandbox(
    request: Request,
    sandbox_id: str,
    payload: UpdateSandboxRequest,
    subject: str = Depends(get_current_subject),
) -> ApiEnvelope[SandboxResponse]:
    sandbox = lifecycle_service.update(sandbox_id, payload)
    if sandbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"sandbox '{sandbox_id}' was not found; confirm the sandbox id or alias before retrying")
    return ok(await _enrich_response(request, sandbox, subject), message="sandbox updated")


@router.delete("/{sandbox_id}", response_model=ApiEnvelope[dict[str, bool]])
async def delete_sandbox(sandbox_id: str) -> ApiEnvelope[dict[str, bool]]:
    deleted = lifecycle_service.destroy(sandbox_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"sandbox '{sandbox_id}' was not found; confirm the sandbox id or alias before deleting")
    return ok({"ok": True}, message="sandbox deleted")


@router.post("/{sandbox_id}/pause", response_model=ApiEnvelope[dict[str, bool]])
async def pause_sandbox(sandbox_id: str) -> ApiEnvelope[dict[str, bool]]:
    paused = lifecycle_service.pause(sandbox_id)
    if not paused:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"sandbox '{sandbox_id}' was not found; confirm the sandbox id or alias before pausing")
    return ok({"ok": True}, message="sandbox paused")


@router.post("/{sandbox_id}/resume", response_model=ApiEnvelope[dict[str, bool]])
async def resume_sandbox(sandbox_id: str) -> ApiEnvelope[dict[str, bool]]:
    sandbox = require_sandbox(sandbox_id)
    if sandbox.status not in {SandboxStatus.STOPPED, SandboxStatus.FAILED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"sandbox '{sandbox_id}' is neither stopped nor failed; call pause first or wait until the sandbox reaches STOPPED before resuming")
    resumed = await lifecycle_service.resume(sandbox_id)
    if not resumed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"sandbox '{sandbox_id}' could not be resumed; inspect sandbox.metadata.runtime_error for the concrete runtime failure")
    return ok({"ok": True}, message="sandbox resumed")


@router.post("/{sandbox_id}/browser/restart", response_model=ApiEnvelope[dict[str, object]])
async def restart_browser(
    sandbox_id: str,
    payload: RestartBrowserRequest,
    sandbox=Depends(require_sandbox),
) -> ApiEnvelope[dict[str, object]]:
    del sandbox, payload
    restarted = await lifecycle_service.restart_browser(sandbox_id)
    if not restarted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"browser restart failed for sandbox '{sandbox_id}'; inspect sandbox.metadata.runtime_error and ensure the runtime container is healthy")
    return ok({"ok": True, "level": "hard"}, message="browser restarted")
