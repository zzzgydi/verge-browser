from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app.auth.tickets import TicketStore, issue_ticket, verify_ticket


def test_ticket_verify_and_consume() -> None:
    ticket = issue_ticket(sandbox_id="sb_1", subject="u1", ticket_type="session", scope="connect", ttl_sec=30)
    payload = verify_ticket(ticket, sandbox_id="sb_1", ticket_type="session", scope="connect", consume=True)
    assert payload["sandbox_id"] == "sb_1"
    with pytest.raises(HTTPException):
        verify_ticket(ticket, sandbox_id="sb_1", ticket_type="session", scope="connect", consume=True)


def test_reusable_ticket_can_be_verified_multiple_times() -> None:
    ticket = issue_ticket(
        sandbox_id="sb_1",
        subject="u1",
        ticket_type="session",
        scope="connect",
        ttl_sec=30,
        mode="reusable",
    )

    first = verify_ticket(ticket, sandbox_id="sb_1", ticket_type="session", scope="connect", consume=True)
    second = verify_ticket(ticket, sandbox_id="sb_1", ticket_type="session", scope="connect", consume=True)

    assert first["mode"] == "reusable"
    assert second["mode"] == "reusable"


def test_permanent_ticket_does_not_expire() -> None:
    ticket = issue_ticket(
        sandbox_id="sb_1",
        subject="u1",
        ticket_type="session",
        scope="connect",
        mode="permanent",
    )

    payload = verify_ticket(ticket, sandbox_id="sb_1", ticket_type="session", scope="connect", consume=True)

    assert payload["mode"] == "permanent"
    assert payload["exp"] is None


def test_permanent_ticket_ignores_ttl() -> None:
    ticket = issue_ticket(
        sandbox_id="sb_1",
        subject="u1",
        ticket_type="session",
        scope="connect",
        ttl_sec=30,
        mode="permanent",
    )

    payload = verify_ticket(ticket, sandbox_id="sb_1", ticket_type="session", scope="connect", consume=True)

    assert payload["mode"] == "permanent"
    assert payload["exp"] is None


def test_ticket_store_rejects_concurrent_duplicate_consume() -> None:
    store = TicketStore()

    def consume() -> str:
        try:
            store.consume("same-jti", 4102444800)
            return "ok"
        except HTTPException:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume(), range(2)))

    assert results.count("ok") == 1
    assert results.count("duplicate") == 1


def test_ticket_store_prunes_expired_entries() -> None:
    store = TicketStore()
    store.consume("expired", 1)
    store.consume("fresh", 4102444800)
    assert "expired" not in store._consumed
    assert "fresh" in store._consumed
