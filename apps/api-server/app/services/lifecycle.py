from __future__ import annotations

import asyncio
import re
import secrets
import shutil

from fastapi import HTTPException, status

from app.config import get_settings
from app.models.sandbox import RuntimeEndpoint, SandboxRecord, SandboxStatus, utcnow
from app.schemas.sandbox import CreateSandboxRequest, UpdateSandboxRequest
from app.services.browser import browser_service
from app.services.docker_adapter import docker_adapter
from app.services.registry import registry

ALIAS_PATTERN = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9_-]{0,62})$")


class SandboxLifecycleService:
    async def create(self, req: CreateSandboxRequest) -> SandboxRecord:
        settings = get_settings()
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
        if docker_adapter.is_available():
            container_id, host = docker_adapter.create_container(
                sandbox_id=sandbox_id,
                workspace_dir=workspace,
                width=req.width,
                height=req.height,
                default_url=req.default_url,
                image=req.image,
            )
            status = SandboxStatus.STARTING if container_id else SandboxStatus.FAILED
        else:
            metadata["runtime_error"] = "docker daemon unavailable"

        sandbox = SandboxRecord(
            id=sandbox_id,
            alias=alias,
            status=status,
            updated_at=utcnow(),
            last_active_at=utcnow(),
            width=req.width,
            height=req.height,
            image=req.image,
            workspace_dir=workspace,
            downloads_dir=downloads,
            uploads_dir=uploads,
            browser_profile_dir=profile,
            container_id=container_id,
            runtime=RuntimeEndpoint(host=host),
            metadata=metadata,
        )
        registry.put(sandbox)
        if container_id:
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
        sandbox = registry.remove(sandbox.id)
        if sandbox is None:
            return False
        if sandbox.container_id:
            docker_adapter.remove_container(sandbox.container_id)
        root = sandbox.workspace_dir.parent
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        return True

    def pause(self, sandbox_id: str) -> bool:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None:
            return False
        if sandbox.container_id:
            docker_adapter.remove_container(sandbox.container_id)
        sandbox.container_id = None
        sandbox.status = SandboxStatus.STOPPED
        sandbox.updated_at = utcnow()
        sandbox.last_active_at = sandbox.updated_at
        sandbox.runtime.host = "127.0.0.1"
        sandbox.metadata.pop("runtime_error", None)
        registry.put(sandbox)
        return True

    async def resume(self, sandbox_id: str) -> bool:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None or sandbox.status != SandboxStatus.STOPPED:
            return False
        if not docker_adapter.is_available():
            sandbox.status = SandboxStatus.FAILED
            sandbox.updated_at = utcnow()
            sandbox.metadata["runtime_error"] = "docker daemon unavailable"
            registry.put(sandbox)
            return False
        container_id, host = docker_adapter.create_container(
            sandbox_id=sandbox.id,
            workspace_dir=sandbox.workspace_dir,
            width=sandbox.width,
            height=sandbox.height,
            default_url=None,
            image=sandbox.image,
        )
        if not container_id:
            sandbox.status = SandboxStatus.FAILED
            sandbox.updated_at = utcnow()
            sandbox.metadata["runtime_error"] = "sandbox container failed to start"
            registry.put(sandbox)
            return False
        sandbox.container_id = container_id
        sandbox.runtime.host = host
        sandbox.status = SandboxStatus.STARTING
        sandbox.updated_at = utcnow()
        sandbox.last_active_at = sandbox.updated_at
        sandbox.metadata.pop("runtime_error", None)
        registry.put(sandbox)
        settings = get_settings()
        await self._wait_until_ready(sandbox_id, timeout_sec=settings.sandbox_start_timeout_sec)
        refreshed = registry.get(sandbox_id)
        return refreshed is not None and refreshed.status == SandboxStatus.RUNNING

    async def restart_browser(self, sandbox_id: str) -> bool:
        sandbox = registry.get(sandbox_id) or registry.get_by_alias(sandbox_id)
        if sandbox is None:
            return False

        sandbox.status = SandboxStatus.STARTING
        sandbox.updated_at = utcnow()
        sandbox.last_active_at = sandbox.updated_at
        sandbox.metadata.pop("runtime_error", None)
        registry.put(sandbox)

        # Check if container still exists, recreate if needed
        if sandbox.container_id and docker_adapter.container_exists(sandbox.container_id):
            ok = docker_adapter.restart_browser(sandbox.container_id)
            if not ok:
                sandbox.status = SandboxStatus.DEGRADED
                sandbox.updated_at = utcnow()
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
                docker_adapter.remove_container(sandbox.container_id)

            container_id, host = docker_adapter.create_container(
                sandbox_id=sandbox.id,
                workspace_dir=sandbox.workspace_dir,
                width=sandbox.width,
                height=sandbox.height,
                default_url=None,
                image=sandbox.image,
            )
            if not container_id:
                sandbox.status = SandboxStatus.FAILED
                sandbox.updated_at = utcnow()
                sandbox.metadata["runtime_error"] = "sandbox container failed to start"
                registry.put(sandbox)
                return False

            sandbox.container_id = container_id
            sandbox.runtime.host = host
            registry.put(sandbox)

        settings = get_settings()
        await self._wait_until_ready(sandbox_id, timeout_sec=settings.sandbox_start_timeout_sec)
        refreshed = registry.get(sandbox_id)
        return refreshed is not None and refreshed.status == SandboxStatus.RUNNING

    async def _wait_until_ready(self, sandbox_id: str, *, timeout_sec: int) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            sandbox = registry.get(sandbox_id)
            if sandbox is None:
                return
            version = await browser_service.browser_version(sandbox)
            try:
                window = browser_service.get_viewport(sandbox)
            except Exception:
                window = {"window_viewport": {"width": 0}}
            if version.get("webSocketDebuggerUrl") and window["window_viewport"]["width"] > 0:
                sandbox.status = SandboxStatus.RUNNING
                sandbox.updated_at = utcnow()
                sandbox.last_active_at = sandbox.updated_at
                registry.put(sandbox)
                return
            await asyncio.sleep(1)
        sandbox = registry.get(sandbox_id)
        if sandbox is not None:
            sandbox.status = SandboxStatus.DEGRADED
            sandbox.metadata["runtime_error"] = "sandbox readiness timed out"
            sandbox.updated_at = utcnow()
            registry.put(sandbox)

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
