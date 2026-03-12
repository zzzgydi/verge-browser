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
        width: int = 1280,
        height: int = 1024,
        default_url: str | None = None,
        image: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"width": width, "height": height, "metadata": metadata or {}}
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

    def get_cdp_info(self, id_or_alias: str, *, mode: str = "reusable", ttl_sec: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": mode}
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/cdp/apply", json=payload)

    def create_vnc_ticket(
        self,
        id_or_alias: str,
        *,
        mode: str = "one_time",
        ttl_sec: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": mode}
        if ttl_sec is not None:
            payload["ttl_sec"] = ttl_sec
        return self._request("POST", f"/sandbox/{quote(id_or_alias, safe='')}/vnc/apply", json=payload)

    def get_vnc_url(
        self,
        id_or_alias: str,
        *,
        mode: str = "one_time",
        ttl_sec: int | None = None,
    ) -> dict[str, Any]:
        sandbox = self.get_sandbox(id_or_alias)
        ticket = self.create_vnc_ticket(str(sandbox["id"]), mode=mode, ttl_sec=ttl_sec)
        return {
            "sandbox_id": sandbox["id"],
            "alias": sandbox.get("alias"),
            "ticket": ticket["ticket"],
            "url": ticket["vnc_url"],
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
        if response.is_success:
            if not response.content:
                return None
            payload = response.json()
            if not isinstance(payload, dict) or {"code", "message", "data"} - payload.keys():
                raise VergeServerError(f"invalid response envelope from {method} {path}")
            return payload["data"]

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
