from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from threading import Lock

from app.models.sandbox import SandboxKind, RuntimeEndpoint, SandboxRecord, SandboxStatus


def _kind_from_payload(payload: dict, runtime_payload: dict) -> SandboxKind:
    kind = payload.get("kind")
    if kind in {SandboxKind.XPRA.value, SandboxKind.XPRA}:
        return SandboxKind.XPRA
    if kind in {SandboxKind.XVFB_VNC.value, SandboxKind.XVFB_VNC}:
        return SandboxKind.XVFB_VNC
    if runtime_payload.get("session_port") == 14500 or runtime_payload.get("display") == ":100":
        return SandboxKind.XPRA
    return SandboxKind.XVFB_VNC


class SandboxRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SandboxRecord] = {}
        self._lock = Lock()

    def put(self, sandbox: SandboxRecord) -> SandboxRecord:
        with self._lock:
            self._items[sandbox.id] = sandbox
        self._write_meta(sandbox)
        return sandbox

    def get(self, sandbox_id: str) -> SandboxRecord | None:
        with self._lock:
            return self._items.get(sandbox_id)

    def get_by_alias(self, alias: str) -> SandboxRecord | None:
        with self._lock:
            for sandbox in self._items.values():
                if sandbox.alias == alias:
                    return sandbox
        return None

    def delete(self, sandbox_id: str) -> SandboxRecord | None:
        with self._lock:
            return self._items.pop(sandbox_id, None)

    def remove(self, sandbox_id: str) -> SandboxRecord | None:
        return self.delete(sandbox_id)

    def all(self) -> Iterable[SandboxRecord]:
        with self._lock:
            return tuple(self._items.values())

    def load_from_disk(self, base_dir: Path, *, workspace_subdir: str, downloads_subdir: str, uploads_subdir: str, browser_profile_subdir: str) -> None:
        loaded: dict[str, SandboxRecord] = {}
        if base_dir.exists():
            for sandbox_dir in base_dir.iterdir():
                if not sandbox_dir.is_dir():
                    continue
                meta_file = sandbox_dir / "meta.json"
                if not meta_file.exists():
                    continue
                try:
                    payload = json.loads(meta_file.read_text())
                    workspace_dir = sandbox_dir / workspace_subdir
                    runtime_payload = payload.get("runtime") or {}
                    kind = _kind_from_payload(payload, runtime_payload)
                    sandbox = SandboxRecord(
                        id=payload["id"],
                        alias=payload.get("alias"),
                        kind=kind,
                        status=SandboxStatus.STOPPED,
                        created_at=payload["created_at"],
                        updated_at=payload["updated_at"],
                        last_active_at=payload.get("last_active_at", payload["updated_at"]),
                        width=payload.get("width", 1280),
                        height=payload.get("height", 1024),
                        image=payload.get("image"),
                        workspace_dir=workspace_dir,
                        downloads_dir=workspace_dir / downloads_subdir,
                        uploads_dir=workspace_dir / uploads_subdir,
                        browser_profile_dir=workspace_dir / browser_profile_subdir,
                        container_id=None,
                        runtime=RuntimeEndpoint(
                            host="127.0.0.1",
                            cdp_port=runtime_payload.get("cdp_port", 9223),
                            session_port=runtime_payload.get("session_port", runtime_payload.get("vnc_port", 14500)),
                            display=runtime_payload.get("display", ":100"),
                            browser_debug_port=runtime_payload.get("browser_debug_port", runtime_payload.get("browser_port", 9222)),
                        ),
                        metadata=payload.get("metadata", {}),
                    )
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                loaded[sandbox.id] = sandbox
        with self._lock:
            self._items = loaded

    def _write_meta(self, sandbox: SandboxRecord) -> None:
        root = sandbox.workspace_dir.parent
        root.mkdir(parents=True, exist_ok=True)
        meta_file = root / "meta.json"
        tmp_file = root / ".meta.json.tmp"
        payload = {
            "id": sandbox.id,
            "alias": sandbox.alias,
            "kind": sandbox.kind,
            "created_at": sandbox.created_at.isoformat(),
            "updated_at": sandbox.updated_at.isoformat(),
            "last_active_at": sandbox.last_active_at.isoformat(),
            "status": sandbox.status,
            "width": sandbox.width,
            "height": sandbox.height,
            "image": sandbox.image,
            "runtime": sandbox.runtime.model_dump(mode="json"),
            "metadata": sandbox.metadata,
        }
        tmp_file.write_text(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
        tmp_file.replace(meta_file)


registry = SandboxRegistry()
