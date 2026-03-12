from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import HTTPException

from app.auth.tickets import issue_ticket
from app.config import get_settings
from app.schemas.sandbox import CreateCdpTicketRequest, CreateCdpTicketResponse


def canonical_sandbox_id(sandbox, fallback: str) -> str:
    return str(getattr(sandbox, "id", fallback))


def issue_cdp_ticket_response(
    *,
    base_url: str,
    sandbox_id: str,
    subject: str,
    request: CreateCdpTicketRequest | None = None,
) -> CreateCdpTicketResponse:
    settings = get_settings()
    ticket_request = request or CreateCdpTicketRequest()
    try:
        ticket = issue_ticket(
            sandbox_id=sandbox_id,
            subject=subject,
            ticket_type="cdp",
            scope="connect",
            ttl_sec=ticket_request.ttl_sec,
            mode=ticket_request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    expires_at = None
    if ticket_request.mode != "permanent":
        ttl_sec = ticket_request.ttl_sec or settings.ticket_ttl_sec
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)
    return CreateCdpTicketResponse(
        ticket=ticket,
        cdp_url=build_cdp_proxy_url(base_url, sandbox_id, ticket),
        mode=ticket_request.mode,
        ttl_sec=None if ticket_request.mode == "permanent" else (ticket_request.ttl_sec or settings.ticket_ttl_sec),
        expires_at=expires_at,
    )


def build_cdp_proxy_url(base_url: str, sandbox_id: str, ticket: str) -> str:
    return f"{base_url}/sandbox/{sandbox_id}/cdp/browser?{urlencode({'ticket': ticket})}"
