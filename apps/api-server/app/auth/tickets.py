from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from threading import Lock
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.config import get_settings

TicketMode = str


class TicketStore:
    def __init__(self) -> None:
        self._consumed: dict[str, int] = {}
        self._lock = Lock()

    def consume(self, jti: str, exp: int) -> None:
        now = int(datetime.now(timezone.utc).timestamp())
        with self._lock:
            self._prune_locked(now)
            existing_exp = self._consumed.get(jti)
            if existing_exp is not None and existing_exp >= now:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ticket already used")
            self._consumed[jti] = exp

    def _prune_locked(self, now: int) -> None:
        expired = [jti for jti, exp in self._consumed.items() if exp < now]
        for jti in expired:
            self._consumed.pop(jti, None)


ticket_store = TicketStore()


def _sign(data: bytes) -> str:
    settings = get_settings()
    return hmac.new(settings.ticket_secret.encode(), data, hashlib.sha256).hexdigest()


def issue_ticket(
    *,
    sandbox_id: str,
    subject: str,
    ticket_type: str,
    scope: str,
    ttl_sec: int | None = None,
    mode: TicketMode = "one_time",
) -> str:
    settings = get_settings()
    if mode not in {"one_time", "reusable", "permanent"}:
        raise ValueError(f"unsupported ticket mode: {mode}")

    expires_at: datetime | None = None
    if mode != "permanent":
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_sec or settings.ticket_ttl_sec)
    payload = {
        "sandbox_id": sandbox_id,
        "sub": subject,
        "type": ticket_type,
        "scope": scope,
        "mode": mode,
        "exp": int(expires_at.timestamp()) if expires_at else None,
        "jti": secrets.token_hex(16),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{raw.hex()}.{_sign(raw)}"


def verify_ticket(token: str, *, sandbox_id: str, ticket_type: str, scope: str, consume: bool = False) -> dict[str, Any]:
    try:
        raw_hex, signature = token.split(".", 1)
        raw = bytes.fromhex(raw_hex)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ticket") from exc

    expected = _sign(raw)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ticket signature")

    payload = json.loads(raw.decode())
    if payload["sandbox_id"] != sandbox_id or payload["type"] != ticket_type or payload["scope"] != scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ticket scope mismatch")
    exp = payload.get("exp")
    if exp is not None and datetime.now(timezone.utc).timestamp() > exp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ticket expired")
    if consume and payload.get("mode", "one_time") == "one_time":
        ticket_store.consume(payload["jti"], exp if exp is not None else 4102444800)
    return payload
