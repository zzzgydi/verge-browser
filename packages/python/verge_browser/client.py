from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx

from verge_browser.errors import (
    VergeAuthError,
    VergeConfigError,
    VergeConflictError,
    VergeNotFoundError,
    VergeServerError,
    VergeValidationError,
)


class VergeClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("VERGE_BROWSER_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.token = token or os.getenv("VERGE_BROWSER_TOKEN")
        if not self.token:
            raise VergeConfigError("missing token; set VERGE_BROWSER_TOKEN or pass token=")
        self._client = http_client or httpx.Client(base_url=self.base_url, timeout=timeout, headers=self._headers())
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def list_sandboxes(self) -> list[dict[str, Any]]:
        return self._request("GET", "/sandbox")

    def create_sandbox(
        self,
        *,
        alias: str | None = None,
        kind: str = "xvfb_vnc",
        width: int = 1280,
        height: int = 1024,
        default_url: str | None = None,
        image: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": kind, "width": width, "height": height, "metadata": metadata or {}}
        if alias is not None:
            payload["alias"] = alias
        if default_url is not None:
            payload["default_url"] = default_url
        if image is not None:
            payload["image"] = image
        return self._request("POST", "/sandbox", json=payload)

    def get_sandbox(self, id_or_alias: str) -> dict[str, Any]:
        return self._request("GET", f"/sandbox/{quote(id_or_alias, safe='')}")

    def update_sandbox(
        self,
        id_or_alias: str,
        *,
        alias: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if alias is not None:
            payload["alias"] = alias
        if metadata is not None:
            payload["metadata"] = metadata
        return self._request("PATCH", f"/sandbox/{quote(id_or_alias, safe='')}", json=payload)

    def delete_sandbox(self, id_or_alias: str) -> dict[str, Any]:
        self._request("DELETE", f"/sandbox/{quote(id_or_alias, safe='')}")
        return {"ok": True}

    def pause_sandbox(self, id_or_alias: str) -> dict[str, Any]:
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/pause")

    def resume_sandbox(self, id_or_alias: str) -> dict[str, Any]:
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/resume")

    def restart_browser(self, id_or_alias: str) -> dict[str, Any]:
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/browser/restart", json={"level": "hard"})

    def get_browser_info(self, id_or_alias: str) -> dict[str, Any]:
        return self.get_sandbox(id_or_alias)["browser"]

    def get_browser_viewport(self, id_or_alias: str) -> dict[str, Any]:
        browser = self.get_browser_info(id_or_alias)
        width = browser.get("viewport", {}).get("width", 1280)
        height = browser.get("viewport", {}).get("height", 1024)
        return {
            "window_viewport": browser.get("window_viewport") or {"x": 0, "y": 0, "width": width, "height": height},
            "page_viewport": browser.get("page_viewport") or {"x": 0, "y": 0, "width": width, "height": height},
            "active_window": browser.get("active_window"),
        }

    def get_browser_screenshot(
        self,
        id_or_alias: str,
        *,
        type: str = "page",
        format: str = "jpeg",
        target_id: str | None = None,
        quality: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": type, "format": format}
        if target_id is not None:
            payload["target_id"] = target_id
        if quality is not None:
            payload["quality"] = quality
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/browser/screenshot", json=payload)

    def execute_browser_actions(self, id_or_alias: str, actions: list[dict[str, Any]], *, continue_on_error: bool = False, screenshot_after: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "actions": actions,
            "continue_on_error": continue_on_error,
            "screenshot_after": screenshot_after,
        }
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/browser/actions", json=payload)

    def list_files(self, id_or_alias: str, path: str = "/workspace") -> list[dict[str, Any]]:
        return self._request("GET", f"/sandbox/{quote(id_or_alias, safe='')}/files/list", params={"path": path})

    def read_file(self, id_or_alias: str, path: str) -> dict[str, Any]:
        return self._request("GET", f"/sandbox/{quote(id_or_alias, safe='')}/files/read", params={"path": path})

    def write_file(self, id_or_alias: str, path: str, content: str, *, overwrite: bool = False) -> dict[str, Any]:
        payload = {"path": path, "content": content, "overwrite": overwrite}
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/files/write", json=payload)

    def upload_file(self, id_or_alias: str, path: str, data: bytes | str, *, filename: str | None = None) -> dict[str, Any]:
        from io import BytesIO
        files = {"upload": (filename or path.split("/")[-1], BytesIO(data if isinstance(data, bytes) else data.encode()))}
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/files/upload", files=files)

    def download_file(self, id_or_alias: str, path: str) -> dict[str, Any]:
        # Use raw request to get binary data, but handle errors consistently
        response = self._client.get(
            f"/sandbox/{quote(id_or_alias, safe='')}/files/download",
            params={"path": path},
            headers=self._headers(),
        )
        self._check_response(response)
        return {"path": path, "data": response.content, "content_type": response.headers.get("content-type")}

    def _handle_error(self, response) -> None:
        """Handle HTTP error response and raise appropriate Verge*Error."""
        detail: str
        try:
            payload = response.json()
            detail = str(payload.get("message") or response.text)
        except Exception:
            detail = response.text

        if response.status_code == 401:
            raise VergeAuthError(detail or "authentication failed")
        if response.status_code == 404:
            raise VergeNotFoundError(detail or "resource not found")
        if response.status_code == 409:
            raise VergeConflictError(detail or "request conflict")
        if response.status_code == 422:
            raise VergeValidationError(detail or "validation failed")
        raise VergeServerError(f"{response.status_code}: {detail or 'request failed'}")

    def _check_response(self, response) -> None:
        """Check response status and raise appropriate error if not successful."""
        if not response.is_success:
            self._handle_error(response)

    def delete_file(self, id_or_alias: str, path: str) -> dict[str, Any]:
        return self._request("DELETE", f"/sandbox/{quote(id_or_alias, safe='')}/files", params={"path": path})

    def get_cdp_info(self, id_or_alias: str, *, mode: str = "reusable", ttl_sec: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": mode}
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/cdp/apply", json=payload)

    def create_session_ticket(
        self,
        id_or_alias: str,
        *,
        mode: str = "one_time",
        ttl_sec: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": mode}
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/session/apply", json=payload)

    def get_session_url(
        self,
        id_or_alias: str,
        *,
        mode: str = "one_time",
        ttl_sec: int | None = None,
    ) -> dict[str, Any]:
        sandbox = self.get_sandbox(id_or_alias)
        ticket = self.create_session_ticket(str(sandbox["id"]), mode=mode, ttl_sec=ttl_sec)
        return {
            "sandbox_id": sandbox["id"],
            "alias": sandbox.get("alias"),
            "ticket": ticket["ticket"],
            "url": ticket["session_url"],
            "expires_at": ticket.get("expires_at"),
            "mode": ticket["mode"],
            "ttl_sec": ticket.get("ttl_sec"),
        }

    def resolve_sandbox_id(self, id_or_alias: str) -> str:
        return str(self.get_sandbox(id_or_alias)["id"])

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("Authorization", f"Bearer {self.token}")
        response = self._client.request(method, path, headers=headers, **kwargs)
        self._check_response(response)
        if not response.content:
            return None
        payload = response.json()
        if not isinstance(payload, dict) or {"code", "message", "data"} - payload.keys():
            raise VergeServerError(f"invalid response envelope from {method} {path}")
        return payload["data"]
