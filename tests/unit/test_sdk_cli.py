from __future__ import annotations

import json

import httpx
import pytest

from verge_browser import VergeClient, VergeConfigError, VergeConflictError
from verge_browser_cli import main


def test_sdk_reads_token_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERGE_BROWSER_TOKEN", "env-token")

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        return httpx.Response(200, json={"code": 0, "message": "ok", "data": []})

    client = VergeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test"))
    try:
        assert client.list_sandboxes() == []
    finally:
        client.close()

    assert captured["authorization"] == "Bearer env-token"


def test_sdk_maps_http_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"code": 409, "message": "alias already exists", "data": None})

    client = VergeClient(token="token", http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test"))
    try:
        with pytest.raises(VergeConflictError, match="alias already exists"):
            client.create_sandbox(alias="dup")
    finally:
        client.close()


def test_sdk_requires_token() -> None:
    with pytest.raises(VergeConfigError, match="missing token"):
        VergeClient(base_url="http://test", token=None)


def test_cli_json_output(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERGE_BROWSER_TOKEN", "token")
    original_client = httpx.Client

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "message": "ok", "data": [{"id": "sb_123", "alias": "demo"}]})

    monkeypatch.setattr(
        "verge_browser.client.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), base_url="http://test", headers=kwargs.get("headers")),
    )

    exit_code = main(["--base-url", "http://test", "--json", "sandbox", "list"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert json.loads(output) == [{"id": "sb_123", "alias": "demo"}]


def test_cli_error_exit_code(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERGE_BROWSER_TOKEN", "token")
    original_client = httpx.Client

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 401, "message": "invalid token", "data": None})

    monkeypatch.setattr(
        "verge_browser.client.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), base_url="http://test", headers=kwargs.get("headers")),
    )

    exit_code = main(["--base-url", "http://test", "--json", "sandbox", "list"])
    error = json.loads(capsys.readouterr().err)

    assert exit_code == 3
    assert error["error"] == "invalid token"


def test_sdk_get_session_url_uses_canonical_sandbox_id_for_ticket() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/sandbox/demo":
            return httpx.Response(
                200,
                json={"code": 0, "message": "ok", "data": {"id": "sb_123", "alias": "demo", "kind": "xvfb_vnc", "browser": {}}},
            )
        if request.url.path == "/sandbox/sb_123/session/apply":
            return httpx.Response(
                200,
                json={"code": 0, "message": "ok", "data": {"ticket": "ticket-1", "session_url": "http://test/sandbox/sb_123/session/?ticket=ticket-1", "mode": "one_time", "ttl_sec": 60, "expires_at": None}},
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = VergeClient(token="token", http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test"))
    try:
        payload = client.get_session_url("demo")
    finally:
        client.close()

    assert payload["url"] == "http://test/sandbox/sb_123/session/?ticket=ticket-1"
    assert seen_paths == ["/sandbox/demo", "/sandbox/sb_123/session/apply"]


def test_sdk_create_sandbox_sends_kind() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json={"code": 0, "message": "sandbox created", "data": {"id": "sb_1", "kind": "xpra"}})

    client = VergeClient(token="token", http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test"))
    try:
        client.create_sandbox(kind="xpra")
    finally:
        client.close()

    assert captured["json"] == {"kind": "xpra", "width": 1280, "height": 1024, "metadata": {}}
