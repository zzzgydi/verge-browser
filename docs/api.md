# API Reference

This document describes the current Verge Browser control plane API.

Base convention:

- REST resources are scoped under `/sandbox/{sandbox_id}/...`
- WebSocket resources follow the same sandbox scoping model
- All JSON business APIs return `{ "code": number, "message": string, "data": ... }`
- Success responses use `code = 0`
- Error responses keep `data = null` and put actionable detail in `message`
- All business APIs require `Authorization: Bearer <admin-token>`
- `GET /healthz` remains anonymous

## Health

### `GET /healthz`

Returns:

```json
{
  "status": "ok"
}
```

## Response Envelope

All JSON business APIs use:

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
  "image": "verge-browser-runtime-xvfb:latest",
  "default_url": "https://example.com",
  "width": 1440,
  "height": 900,
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

Delete a sandbox.

### `POST /sandbox/{sandbox_id}/pause`

Pause a sandbox.

### `POST /sandbox/{sandbox_id}/resume`

Resume a stopped sandbox.

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

Apply for an Xpra session access ticket and return a ticketed entry URL.

Request:

```json
{
  "mode": "one_time",
  "ttl_sec": 60
}
```

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

Validate the ticket, mint a short-lived sandbox session cookie scoped to that sandbox, and return the runtime entry page.
- `xpra`: returns the proxied Xpra HTML5 entry page.
- `xvfb_vnc`: redirects to the proxied noVNC entry page.

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
