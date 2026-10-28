from __future__ import annotations

import asyncio
import logging
import re
import secrets
import shutil

from fastapi import HTTPException, status

from app.config import get_settings
from app.models.sandbox import BrowserEngine, SandboxKind, RuntimeEndpoint, SandboxRecord, SandboxStatus, runtime_endpoint_for_kind, utcnow
from app.schemas.sandbox import CreateSandboxRequest, UpdateSandboxRequest
from app.services.browser import browser_service
from app.services.docker_adapter import docker_adapter
from app.services.engines import cloak_unavailable_reason
from app.services.registry import registry
import httpx

ALIAS_PATTERN = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9_-]{0,62})$")
logger = logging.getLogger(__name__)


class SandboxLifecycleService:
    display_error_key = "display_error"
    session_error_key = "session_error"

    def __init__(self) -> None:
        self._readiness_tasks: dict[str, asyncio.Task[None]] = {}

    async def create(self, req: CreateSandboxRequest) -> SandboxRecord:
        settings = get_settings()
        if req.browser_engine == BrowserEngine.CLOAKBROWSER:
            reason = cloak_unavailable_reason()
            if reason:
                raise HTTPException(status_code=409, detail=reason)
        sandbox_id = f"sb_{secrets.token_hex(6)}"
        alias = self._normalize_alias(req.alias, sandbox_id=None)
        root = (settings.sandbox_base_dir / sandbox_id).resolve()
        workspace = root / settings.workspace_subdir
        downloads = workspace / settings.downloads_subdir
        uploads = workspace / settings.uploads_subdir
        profile = workspace / settings.browser_profile_subdir
        for path in (downloads, uploads, profile):
            path.mkdir(parents=True, exist_ok=True)

        metadata = dict(req.metadata)
        container_id = None
        host = "127.0.0.1"
        status = SandboxStatus.FAILED
        image_name = req.image or (settings.cloak_runtime_image if req.browser_engine == BrowserEngine.CLOAKBROWSER else settings.runtime_image_for_kind(req.kind))
        runtime = runtime_endpoint_for_kind(req.kind)
        if docker_adapter.is_available():
            if not docker_adapter.image_exists(image_name):
                metadata["runtime_error"] = f"runtime image '{image_name}' is not built locally"
            else:
                create_result = docker_adapter.create_container(
                    sandbox_id=sandbox_id,
                    kind=req.kind,
                    browser_engine=req.browser_engine,
                    workspace_dir=workspace,
                    width=req.width,
                    height=req.height,
                    default_url=req.default_url,
                    image=req.image,
                    enable_gpu=req.enable_gpu,
                    http_proxy=req.http_proxy,
                    https_proxy=req.https_proxy,
                    no_proxy=req.no_proxy,
                )
                container_id = create_result.container_id
                host = create_result.host
                if container_id is None:
                    metadata["runtime_error"] = create_result.error or "sandbox container failed to start"
                status = SandboxStatus.STARTING if container_id else SandboxStatus.FAILED
        else:
            metadata["runtime_error"] = "docker daemon unavailable"

        sandbox = SandboxRecord(
            id=sandbox_id,
            alias=alias,
            kind=req.kind,
            browser_engine=req.browser_engine,
            status=status,
            updated_at=utcnow(),
            last_active_at=utcnow(),
            width=req.width,
            height=req.height,
            enable_gpu=req.enable_gpu,
            image=image_name if req.browser_engine == BrowserEngine.CLOAKBROWSER else req.image,
            http_proxy=req.http_proxy,
            https_proxy=req.https_proxy,
            no_proxy=req.no_proxy,
            workspace_dir=workspace,
            downloads_dir=downloads,
            uploads_dir=uploads,
            browser_profile_dir=profile,
            container_id=container_id,
            runtime=RuntimeEndpoint(
                host=host,
                cdp_port=runtime.cdp_port,
                session_port=runtime.session_port,
                display=runtime.display,
                browser_debug_port=runtime.browser_debug_port,
            ),
            metadata=metadata,
        )
        registry.put(sandbox)
        if container_id:
            if req.kind == SandboxKind.XPRA:
                self._schedule_readiness_probe(sandbox_id, timeout_sec=settings.sandbox_start_timeout_sec)
            else:
                await self._wait_until_ready(sandbox_id, timeout_sec=settings.sandbox_start_timeout_sec)
        return registry.get(sandbox_id) or sandbox

    def update(self, sandbox_id: str, req: UpdateSandboxRequest) -> SandboxRecord | None:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None:
            return None
        if req.alias is not None:
            sandbox.alias = self._normalize_alias(req.alias, sandbox_id=sandbox.id)
        if req.metadata is not None:
            sandbox.metadata = dict(req.metadata)
        sandbox.updated_at = utcnow()
        sandbox.last_active_at = sandbox.updated_at
        registry.put(sandbox)
        return sandbox

    def destroy(self, sandbox_id: str) -> bool:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None:
            return False
        self._cancel_readiness_task(sandbox.id)
        self._remove_runtime(sandbox)
        sandbox = registry.remove(sandbox.id)
        if sandbox is None:
            return False
        root = sandbox.workspace_dir.parent
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        return True

    def pause(self, sandbox_id: str) -> bool:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None:
            return False
        self._cancel_readiness_task(sandbox.id)
        self._remove_runtime(sandbox)
        sandbox.container_id = None
        sandbox.status = SandboxStatus.STOPPED
        sandbox.updated_at = utcnow()
        sandbox.last_active_at = sandbox.updated_at
        runtime = runtime_endpoint_for_kind(sandbox.kind)
        sandbox.runtime.host = "127.0.0.1"
        sandbox.runtime.session_port = runtime.session_port
        sandbox.runtime.display = runtime.display
        sandbox.runtime.cdp_port = runtime.cdp_port
        sandbox.runtime.browser_debug_port = runtime.browser_debug_port
        sandbox.metadata.pop("runtime_error", None)
        sandbox.metadata.pop(self.display_error_key, None)
        sandbox.metadata.pop(self.session_error_key, None)
        sandbox.metadata.pop("xpra_error", None)
        registry.put(sandbox)
        return True

    async def resume(self, sandbox_id: str) -> bool:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None or sandbox.status not in {SandboxStatus.STOPPED, SandboxStatus.FAILED}:
            return False
        if sandbox.browser_engine == BrowserEngine.CLOAKBROWSER:
            reason = cloak_unavailable_reason()
            if reason:
                raise HTTPException(status_code=409, detail=reason)
            if sandbox.container_id:
                self._remove_runtime(sandbox)
                sandbox.container_id = None
        if not docker_adapter.is_available():
            sandbox.status = SandboxStatus.FAILED
            sandbox.updated_at = utcnow()
            sandbox.metadata["runtime_error"] = "docker daemon unavailable"
            registry.put(sandbox)
            return False
        settings = get_settings()
        image_name = sandbox.image or (settings.cloak_runtime_image if sandbox.browser_engine == BrowserEngine.CLOAKBROWSER else settings.runtime_image_for_kind(sandbox.kind))
        if not docker_adapter.image_exists(image_name):
            sandbox.status = SandboxStatus.FAILED
            sandbox.updated_at = utcnow()
            sandbox.metadata["runtime_error"] = f"runtime image '{image_name}' is not built locally"
            registry.put(sandbox)
            return False
        create_result = docker_adapter.create_container(
            sandbox_id=sandbox.id,
            kind=sandbox.kind,
            browser_engine=sandbox.browser_engine,
            workspace_dir=sandbox.workspace_dir,
            width=sandbox.width,
            height=sandbox.height,
            default_url=None,
            image=sandbox.image,
            enable_gpu=sandbox.enable_gpu,
            http_proxy=sandbox.http_proxy,
            https_proxy=sandbox.https_proxy,
            no_proxy=sandbox.no_proxy,
        )
        container_id = create_result.container_id
        host = create_result.host
        if not container_id:
            sandbox.status = SandboxStatus.FAILED
            sandbox.updated_at = utcnow()
            sandbox.metadata["runtime_error"] = create_result.error or "sandbox container failed to start"
            registry.put(sandbox)
            return False
        sandbox.container_id = container_id
        sandbox.runtime.host = host
        sandbox.status = SandboxStatus.STARTING
        sandbox.updated_at = utcnow()
        sandbox.last_active_at = sandbox.updated_at
        sandbox.metadata.pop("runtime_error", None)
        sandbox.metadata.pop(self.display_error_key, None)
        sandbox.metadata.pop(self.session_error_key, None)
        sandbox.metadata.pop("xpra_error", None)
        registry.put(sandbox)
        settings = get_settings()
        await self._wait_until_ready(sandbox.id, timeout_sec=settings.sandbox_start_timeout_sec)
        refreshed = registry.get(sandbox.id)
        return refreshed is not None and refreshed.status == SandboxStatus.RUNNING

    async def restart_browser(self, sandbox_id: str) -> bool:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None:
            return False

        if sandbox.browser_engine == BrowserEngine.CLOAKBROWSER:
            reason = cloak_unavailable_reason()
            if reason:
                raise HTTPException(status_code=409, detail=reason)

        sandbox.status = SandboxStatus.STARTING
        sandbox.updated_at = utcnow()
        sandbox.last_active_at = sandbox.updated_at
        sandbox.metadata.pop("runtime_error", None)
        registry.put(sandbox)

        # Check if container still exists, recreate if needed
        if sandbox.container_id and docker_adapter.container_exists(sandbox.container_id):
            if sandbox.browser_engine == BrowserEngine.CLOAKBROWSER:
                self._stop_cloak(sandbox)
                ok = docker_adapter.start_cloak_browser(sandbox.container_id)
            else:
                ok = docker_adapter.restart_browser(sandbox.container_id)
            if not ok:
                sandbox.status = SandboxStatus.DEGRADED
                sandbox.updated_at = utcnow()
                sandbox.metadata["runtime_error"] = "Browser restart failed; inspect the runtime controller and retry."
                registry.put(sandbox)
                return False
        else:
            # Container is gone, create a new one
            if not docker_adapter.is_available():
                sandbox.status = SandboxStatus.FAILED
                sandbox.updated_at = utcnow()
                sandbox.metadata["runtime_error"] = "docker daemon unavailable"
                registry.put(sandbox)
                return False

            if sandbox.container_id:
                self._remove_runtime(sandbox)
                sandbox.container_id = None

            create_result = docker_adapter.create_container(
                sandbox_id=sandbox.id,
                kind=sandbox.kind,
                browser_engine=sandbox.browser_engine,
                workspace_dir=sandbox.workspace_dir,
                width=sandbox.width,
                height=sandbox.height,
                default_url=None,
                image=sandbox.image,
                enable_gpu=sandbox.enable_gpu,
                http_proxy=sandbox.http_proxy,
                https_proxy=sandbox.https_proxy,
                no_proxy=sandbox.no_proxy,
            )
            container_id = create_result.container_id
            host = create_result.host
            if not container_id:
                sandbox.status = SandboxStatus.FAILED
                sandbox.updated_at = utcnow()
                sandbox.metadata["runtime_error"] = create_result.error or "sandbox container failed to start"
                registry.put(sandbox)
                return False

            sandbox.container_id = container_id
            sandbox.runtime.host = host
            registry.put(sandbox)

        settings = get_settings()
        await self._wait_until_ready(sandbox.id, timeout_sec=settings.sandbox_start_timeout_sec)
        refreshed = registry.get(sandbox.id)
        return refreshed is not None and refreshed.status == SandboxStatus.RUNNING

    async def _wait_until_ready(self, sandbox_id: str, *, timeout_sec: int) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            sandbox = registry.get(sandbox_id)
            if sandbox is None:
                return
            if sandbox.browser_engine == BrowserEngine.CLOAKBROWSER and self.check_cloak_health(sandbox, starting=True):
                return
            version = await browser_service.browser_version(sandbox)
            try:
                window = browser_service.get_viewport(sandbox)
            except Exception:
                window = {"window_viewport": {"width": 0}}
            if version.get("webSocketDebuggerUrl") and window["window_viewport"]["width"] > 0:
                if await self._session_ready(sandbox) and self._display_ready(sandbox):
                    if sandbox.browser_engine == BrowserEngine.CLOAKBROWSER:
                        diagnostic = docker_adapter.cloak_control(sandbox.container_id, "status")
                        if diagnostic.get("error") or diagnostic.get("process_state") != "RUNNING":
                            await asyncio.sleep(1)
                            continue
                    sandbox.status = SandboxStatus.RUNNING
                    sandbox.updated_at = utcnow()
                    sandbox.last_active_at = sandbox.updated_at
                    sandbox.metadata.pop("runtime_error", None)
                    sandbox.metadata.pop(self.display_error_key, None)
                    sandbox.metadata.pop(self.session_error_key, None)
                    sandbox.metadata.pop("xpra_error", None)
                    sandbox.metadata.pop("display", None)
                    registry.put(sandbox)
                    return
            await asyncio.sleep(1)
        sandbox = registry.get(sandbox_id)
        if sandbox is not None:
            sandbox.status = SandboxStatus.DEGRADED
            sandbox.metadata["runtime_error"] = "sandbox readiness timed out"
            sandbox.metadata["display"] = sandbox.runtime.display
            sandbox.metadata.pop(self.display_error_key, None)
            sandbox.metadata.pop(self.session_error_key, None)
            sandbox.metadata.pop("xpra_error", None)
            if not self._display_ready(sandbox):
                sandbox.metadata[self.display_error_key] = "display unavailable"
            elif not await self._session_ready(sandbox):
                sandbox.metadata[self.session_error_key] = "session service unavailable"
            sandbox.updated_at = utcnow()
            registry.put(sandbox)

    def _stop_cloak(self, sandbox: SandboxRecord) -> None:
        result = docker_adapter.cloak_control(sandbox.container_id, "stop")
        if not result.get("stopped"):
            sandbox.status = SandboxStatus.DEGRADED
            sandbox.metadata["runtime_error"] = "Cloak could not be stopped; container and profile preserved."
            registry.put(sandbox)
            raise HTTPException(status_code=409, detail=sandbox.metadata["runtime_error"])

    def _remove_runtime(self, sandbox: SandboxRecord) -> None:
        if not sandbox.container_id:
            return
        if sandbox.browser_engine == BrowserEngine.CLOAKBROWSER:
            if docker_adapter.container_exists(sandbox.container_id):
                self._stop_cloak(sandbox)
            if not docker_adapter.remove_container(sandbox.container_id):
                raise HTTPException(status_code=409, detail="Container removal failed; profile preserved. Inspect Docker and retry.")
        else:
            docker_adapter.remove_container(sandbox.container_id)

    def check_cloak_health(self, sandbox: SandboxRecord, *, starting: bool = False) -> bool:
        if not sandbox.container_id:
            return False
        diagnostic = docker_adapter.cloak_control(sandbox.container_id, "status")
        error = diagnostic.get("error")
        if starting and error and error.get("code") == "CONTROL_UNAVAILABLE":
            return False  # Supervisor may not have opened its socket yet.
        if not error and diagnostic.get("process_state") in ({"RUNNING", "STARTING", "STOPPED"} if starting else {"RUNNING"}):
            return False
        sandbox.status = SandboxStatus.DEGRADED
        sandbox.updated_at = utcnow()
        sandbox.metadata["runtime_error"] = (
            f"{error['code']}: {error['message']}" if error else "Cloak browser is not running; restart or pause the sandbox."
        )
        registry.put(sandbox)
        return True

    def _schedule_readiness_probe(self, sandbox_id: str, *, timeout_sec: int) -> None:
        existing = self._readiness_tasks.get(sandbox_id)
        if existing is not None and not existing.done():
            return

        async def runner() -> None:
            try:
                await self._wait_until_ready(sandbox_id, timeout_sec=timeout_sec)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("background sandbox readiness failed for %s", sandbox_id)

        task = asyncio.create_task(runner())
        self._readiness_tasks[sandbox_id] = task

        def cleanup(done_task: asyncio.Task[None]) -> None:
            current = self._readiness_tasks.get(sandbox_id)
            if current is done_task:
                self._readiness_tasks.pop(sandbox_id, None)

        task.add_done_callback(cleanup)

    def _cancel_readiness_task(self, sandbox_id: str) -> None:
        task = self._readiness_tasks.pop(sandbox_id, None)
        if task is not None and not task.done():
            task.cancel()

    def _display_ready(self, sandbox: SandboxRecord) -> bool:
        if not sandbox.container_id:
            return False
        if sandbox.kind == SandboxKind.XPRA:
            proc = docker_adapter.exec_shell(
                sandbox.container_id,
                f'export DISPLAY="{sandbox.runtime.display}"; xdpyinfo -display "{sandbox.runtime.display}" >/dev/null 2>&1 && xpra info --display="{sandbox.runtime.display}" >/dev/null 2>&1',
            )
            return proc.returncode == 0
        proc = docker_adapter.exec_shell(
            sandbox.container_id,
            f'export DISPLAY="{sandbox.runtime.display}"; xdpyinfo -display "{sandbox.runtime.display}" >/dev/null 2>&1',
        )
        return proc.returncode == 0

    async def _session_ready(self, sandbox: SandboxRecord) -> bool:
        path = "/" if sandbox.kind == SandboxKind.XPRA else "/vnc.html"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"http://{sandbox.runtime.host}:{sandbox.runtime.session_port}{path}")
                return response.status_code < 500
        except Exception:
            return False

    def _normalize_alias(self, alias: str | None, *, sandbox_id: str | None) -> str | None:
        if alias is None:
            return None
        value = alias.strip()
        if not value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="alias must not be empty")
        if not ALIAS_PATTERN.fullmatch(value):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="alias must match ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")
        existing_id = registry.get(value)
        if existing_id is not None and existing_id.id != sandbox_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="alias already exists")
        existing = registry.get_by_alias(value)
        if existing is not None and existing.id != sandbox_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="alias already exists")
        return value


lifecycle_service = SandboxLifecycleService()
