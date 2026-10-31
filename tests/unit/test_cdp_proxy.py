import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import websockets

from app.routes import browser


@pytest.mark.parametrize("binary", [False, True])
async def test_cdp_proxy_forwards_large_messages(monkeypatch, binary):
    payload = b"x" * (2 * 1024 * 1024) if binary else "x" * (2 * 1024 * 1024)
    received = asyncio.Event()

    async def upstream(connection):
        assert await connection.recv() == "request"
        await connection.send(payload)
        await asyncio.wait_for(received.wait(), timeout=5)

    async with websockets.serve(upstream, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        sandbox = SimpleNamespace(browser_engine="chromium", id="sb_test")
        monkeypatch.setattr(browser, "require_sandbox", Mock(return_value=sandbox))
        verify = Mock()
        monkeypatch.setattr(browser, "verify_ticket", verify)
        monkeypatch.setattr(
            browser.browser_service, "upstream_browser_version",
            AsyncMock(return_value={"webSocketDebuggerUrl": f"ws://127.0.0.1:{port}"}),
        )

        first_request = True

        async def receive():
            nonlocal first_request
            if first_request:
                first_request = False
                return {"text": "request"}
            await asyncio.Event().wait()

        async def send(message):
            assert message == payload
            received.set()

        client = SimpleNamespace(
            query_params={"ticket": "test-ticket"}, accept=AsyncMock(), close=AsyncMock(),
            receive=receive, send_text=AsyncMock(side_effect=send), send_bytes=AsyncMock(side_effect=send),
        )
        await asyncio.wait_for(browser.cdp_browser_proxy(client, "demo"), timeout=10)

    assert received.is_set()
    verify.assert_called_once_with("test-ticket", sandbox_id="sb_test", ticket_type="cdp", scope="connect", consume=True)
    client.close.assert_not_awaited()
    (client.send_bytes if binary else client.send_text).assert_awaited_once_with(payload)


async def test_cdp_proxy_rejects_messages_above_limit(monkeypatch):
    async def upstream(connection):
        await connection.send("x" * (16 * 1024 * 1024 + 1))
        await connection.wait_closed()

    async with websockets.serve(upstream, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(browser, "require_sandbox", Mock(return_value=SimpleNamespace(browser_engine="chromium", id="sb_test")))
        monkeypatch.setattr(browser, "verify_ticket", Mock())
        monkeypatch.setattr(
            browser.browser_service, "upstream_browser_version",
            AsyncMock(return_value={"webSocketDebuggerUrl": f"ws://127.0.0.1:{port}"}),
        )
        client = SimpleNamespace(
            query_params={"ticket": "test-ticket"}, accept=AsyncMock(), close=AsyncMock(),
            receive=asyncio.Event().wait, send_text=AsyncMock(), send_bytes=AsyncMock(),
        )
        await asyncio.wait_for(browser.cdp_browser_proxy(client, "demo"), timeout=10)

    client.send_text.assert_not_awaited()
    client.close.assert_awaited_once_with(code=1011, reason="browser proxy error")
