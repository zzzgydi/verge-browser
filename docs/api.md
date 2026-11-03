# API Reference

This document describes the current Verge Browser control plane API.

Management API conventions:

- REST resources are scoped under `/sandbox/{sandbox_id}/...`
- WebSocket resources follow the same sandbox scoping model
- Management JSON responses use `{ "code": number, "message": string, "data": ... }`
- Success responses use `code = 0`
- Error responses keep `data = null` and put actionable detail in `message`
- Management APIs require `Authorization: Bearer <admin-token>`
- `GET /healthz` remains anonymous

CDP connections require a signed ticket, not the admin token. Visual sessions use a ticket for entry and a sandbox-scoped cookie afterward.
The [clipboard API](vnc_clipboard.md#http-接口) uses that cookie and its own JSON format. File downloads return binary content.

Keep tokens, ticketed URLs, and session cookies private. Each grants access within its scope.

## Health

### `GET /healthz`

Returns:

```json
{
  "status": "ok"
}
```

## Response Envelope

Management JSON APIs use this envelope. The health, clipboard, and binary-download endpoints are exceptions.

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

Error example:

```json
{
  "code": 409,
  "message": "sandbox 'demo' is not stopped; call pause first or wait until the sandbox reaches STOPPED before resuming",
  "data": null
}
```

## Sandbox

### `POST /sandbox`

Create a sandbox.

Request:

```json
{
  "alias": "manual-test",
  "kind": "xvfb_vnc",
  "browser_engine": "chromium",
  "image": "verge-browser-runtime-xvfb:latest",
  "default_url": "https://example.com",
  "width": 1440,
  "height": 900,
  "http_proxy": "http://proxy.example.com:8080",
  "https_proxy": "http://proxy.example.com:8080",
  "no_proxy": "localhost,127.0.0.1",
  "metadata": {
    "purpose": "manual-test"
  }
}
```

Response notes:

- Creation and detail responses no longer expose `cdp_url` or `session_url`
- Browser runtime info is aggregated under `data.browser`
- `kind` selects the runtime stack: `xvfb_vnc` or `xpra`
- If `image` is omitted, the server picks the default image for the selected `kind`

`browser_engine` selects the browser:

| Engine | Runtime kinds | Requirements and limits |
| --- | --- | --- |
| `chromium` | `xvfb_vnc`, `xpra` | Default engine. No Cloak key required. |
| `cloakbrowser` | `xvfb_vnc`, experimental `xpra` | Requires [server setup](guides/cloak.md). No GPU, authenticated proxies, or per-request image override. |
| `camoufox` | `xvfb_vnc` | Requires [server setup](guides/camoufox.md). No GPU, proxies, per-request image override, or CDP. |

Check `/runtime/engines` for the configured `kinds` before creating a sandbox.

### `GET /runtime/engines`

Report supported engines, allowed runtime kinds, and configuration readiness. This endpoint requires admin authentication. It never returns license keys.

Configuration readiness does not prove that a browser can start. Cloak still requires runtime license validation and an available license seat.

### `GET /sandbox`

List sandboxes.

### `GET /sandbox/{sandbox_id}`

Get sandbox detail by sandbox ID or alias.

Example `data` payload:

```json
{
  "id": "sb_123",
  "alias": "manual-test",
  "kind": "xvfb_vnc",
  "status": "RUNNING",
  "created_at": "2026-03-12T10:00:00Z",
  "updated_at": "2026-03-12T10:00:05Z",
  "last_active_at": "2026-03-12T10:00:05Z",
  "width": 1440,
  "height": 900,
  "enable_gpu": false,
  "http_proxy": null,
  "https_proxy": null,
  "no_proxy": null,
  "metadata": {},
  "container_id": "docker-container-id",
  "browser": {
    "browser_version": "Chrome/123.0.x",
    "protocol_version": "1.3",
    "web_socket_debugger_url_present": true,
    "viewport": {
      "width": 1440,
      "height": 900
    },
    "window_viewport": {
      "x": 0,
      "y": 0,
      "width": 1440,
      "height": 900
    },
    "page_viewport": {
      "x": 0,
      "y": 80,
      "width": 1440,
      "height": 820
    },
    "active_window": {
      "window_id": "4194307",
      "x": 0,
      "y": 0,
      "title": "Chromium"
    }
  }
}
```

### `PATCH /sandbox/{sandbox_id}`

Update mutable fields.

### `DELETE /sandbox/{sandbox_id}`

Delete the runtime, sandbox record, profile, and shared files. Back up required data before deletion.

### `POST /sandbox/{sandbox_id}/pause`

Remove the runtime container and retain the workspace. This ends browser connections; it does not suspend browser memory.

### `POST /sandbox/{sandbox_id}/resume`

Create a runtime for a stopped sandbox with its existing workspace. See [lifecycle behavior](guides/persistent-profiles.md).

### Sandbox Kinds

- `xvfb_vnc`
  Exposes a noVNC session behind the unified `/session/...` routes.
- `xpra`
  Exposes an Xpra HTML5 session behind the same `/session/...` routes.

### `POST /sandbox/{sandbox_id}/browser/restart`

Restart Chromium.

Request:

```json
{
  "level": "hard"
}
```

## Browser

### `POST /sandbox/{sandbox_id}/browser/screenshot`

Capture a screenshot.

Window screenshots include the browser controls. Xvfb captures the visible desktop region. Xpra captures the browser window directly.
The Xpra root desktop does not contain the redirected window pixels.

On Xpra, a screenshot of an unmapped browser window makes that window visible. This also occurs without an HTML5 session connection.

Request:

```json
{
  "type": "page",
  "format": "jpeg",
  "quality": 80,
  "target_id": "target-id-optional"
}
```

Response `data`:

```json
{
  "type": "page",
  "format": "jpeg",
  "media_type": "image/jpeg",
  "metadata": {
    "width": 1440,
    "height": 900,
    "page_viewport": {
      "x": 0,
      "y": 80,
      "width": 1440,
      "height": 820
    },
    "window_viewport": {
      "x": 0,
      "y": 0,
      "width": 1440,
      "height": 900
    },
    "window_id": "4194307"
  },
  "data_base64": "..."
}
```

### `POST /sandbox/{sandbox_id}/browser/actions`

Execute GUI actions through `xdotool`.

### `POST /sandbox/{sandbox_id}/cdp/apply`

Apply for a CDP access ticket and return a ticketed proxy URL.

Request:

```json
{
  "mode": "reusable",
  "ttl_sec": 300
}
```

| Field     | Type   | Default      | Description                          |
| --------- | ------ | ------------ | ------------------------------------ |
| `mode`    | string | `"reusable"` | Ticket mode (see below).             |
| `ttl_sec` | int    | `60`         | Ticket lifetime in seconds (1–86400). When omitted, falls back to `VERGE_TICKET_TTL_SEC` (default `60`). |

**Ticket modes:**

| Mode         | Description                                                         |
| ------------ | ------------------------------------------------------------------- |
| `one_time`   | Consumed on first connection. Cannot be reused.                     |
| `reusable`   | Can be connected to repeatedly until the TTL expires. **(default)** |
| `permanent`  | Never expires. No TTL.                                              |

Response `data`:

```json
{
  "ticket": "<opaque-ticket>",
  "cdp_url": "wss://api.example.com/sandbox/sb_123/cdp/browser?ticket=hexpayload.signature",
  "mode": "reusable",
  "ttl_sec": 300,
  "expires_at": "2026-03-12T12:34:56Z"
}
```

### `WS /sandbox/{sandbox_id}/cdp/browser`

Browser-level CDP proxy. Requires `ticket=...` in the query string.

## Session

### `POST /sandbox/{sandbox_id}/session/apply`

Apply for a session access ticket and return a ticketed entry URL.

Request:

```json
{
  "mode": "one_time",
  "ttl_sec": 60
}
```

| Field     | Type   | Default      | Description                          |
| --------- | ------ | ------------ | ------------------------------------ |
| `mode`    | string | `"one_time"` | Ticket mode (see below).             |
| `ttl_sec` | int    | `60`         | Ticket lifetime in seconds (1–86400). When omitted, falls back to `VERGE_TICKET_TTL_SEC` (default `60`). |

**Ticket modes:**

| Mode         | Description                                                         |
| ------------ | ------------------------------------------------------------------- |
| `one_time`   | Consumed on first use. Cannot be reused. **(default)**              |
| `reusable`   | Can be used repeatedly until the TTL expires.                       |
| `permanent`  | Never expires. No TTL.                                              |

Response `data`:

```json
{
  "ticket": "<opaque-ticket>",
  "session_url": "https://api.example.com/sandbox/sb_123/session/?ticket=hexpayload.signature",
  "mode": "one_time",
  "ttl_sec": 60,
  "expires_at": "2026-03-12T12:34:56Z"
}
```

### `GET /sandbox/{sandbox_id}/session/?ticket=...`

The server validates the ticket and creates a cookie for that sandbox.
For a time-limited ticket, the cookie uses the ticket's remaining lifetime. A permanent ticket does not set a session expiry.
The server then serves the runtime entry page:
- `xpra`: returns the proxied Xpra HTML5 entry page.
- `xvfb_vnc`: redirects to Verge's noVNC page with the clipboard toolbar.

### `GET /sandbox/{sandbox_id}/session/{asset_path}`

Proxy runtime static assets after session validation.

### `WS /sandbox/{sandbox_id}/session/ws`

Proxy the Xpra session WebSocket after session validation.

### `WS /sandbox/{sandbox_id}/session/`

Alias of `/session/ws` for Xpra clients that connect on the session root path.

### `WS /sandbox/{sandbox_id}/session/websockify`

Proxy the noVNC/websockify WebSocket for `xvfb_vnc` sandboxes after session validation.

## Files

### `GET /sandbox/{sandbox_id}/files/list?path=/workspace`

List files.

### `GET /sandbox/{sandbox_id}/files/read?path=/workspace/file.txt`

Read a UTF-8 text file.

### `POST /sandbox/{sandbox_id}/files/write`

Write a UTF-8 text file.

### `POST /sandbox/{sandbox_id}/files/upload`

Upload a file using multipart form data.

### `GET /sandbox/{sandbox_id}/files/download?path=/workspace/file.txt`

Download a file as binary content. This endpoint returns the raw file body, not the JSON envelope.

### `DELETE /sandbox/{sandbox_id}/files?path=/workspace/file.txt`

Delete a file.

## Managed Camoufox commands (experimental)

`POST /sandbox/{sandbox_id}/browser/command` requires the admin bearer token. Only `RUNNING` Camoufox sandboxes support this endpoint.
Chromium and Cloak return 409. Use ticketed CDP for those engines.

Example:

```json
{"action":"snapshot","tab":"default","interactive":true}
```

| Action | Fields |
| --- | --- |
| `open` | `url` |
| `snapshot` | `interactive`, `selector` |
| `click` | `ref` |
| `fill` | `ref`, `text` |
| `press` | `key` |
| `text` | `target` |
| `tabs` | None |
| `switch` | `index` |
| `url` | None |
| `title` | None |
| `upload` | `selector`, `path` under `/workspace/uploads` |

All actions accept an optional named `tab`. The API rejects unknown fields and actions.
See [command semantics](../skills/verge-browser-usage/references/camoufox.md) for field requirements.

Results use the `{code,message,data}` envelope. Runtime failures return 502 without retry.

Camoufox rejects CDP WebSocket access. CDP ticket requests return 409.
Camoufox screenshots support PNG and do not accept a CDP target ID.
