# API Reference

This document describes the current Verge Browser control plane API.

Base convention:

- REST resources are scoped under `/sandboxes/{sandbox_id}/...`
- WebSocket resources follow the same sandbox scoping model
- All business APIs require `Authorization: Bearer <admin-token>`
- `GET /healthz` remains anonymous

## Health

### `GET /healthz`

Returns a basic liveness payload.

Example response:

```json
{
  "status": "ok"
}
```

## Sandboxes

### `POST /sandboxes`

Create a sandbox and start the runtime if Docker is available.

Persistence notes:

- The sandbox workspace is created under the configured sandbox base directory.
- Chromium uses `/workspace/browser-profile`, so cookies and local storage survive browser restarts and `pause` / `resume`.
- The API server persists sandbox metadata to disk and reloads it on service startup. Reloaded sandboxes come back as `STOPPED` until resumed.

Request body:

```json
{
  "alias": "manual-test",
  "image": "verge-browser-runtime:latest",
  "default_url": "https://github.com/zzzgydi/verge-browser",
  "width": 1440,
  "height": 900,
  "metadata": {
    "purpose": "manual-test"
  }
}
```

Response highlights:

- `id`: sandbox ID
- `alias`: human-readable sandbox alias
- `status`: lifecycle status
- `updated_at` / `last_active_at`: lifecycle timestamps
- `browser.cdp_url`: external CDP proxy URL
- `browser.vnc_entry_base_url`: VNC landing URL prefix
- `browser.vnc_ticket_endpoint`: endpoint for a one-time VNC ticket

### `GET /sandboxes`

Return all sandboxes with status, alias, timestamps, metadata, CDP URL, and VNC entry info.

### `GET /sandboxes/{sandbox_id}`

Return current sandbox metadata and browser access info. The path parameter accepts either the real sandbox ID or the configured alias.

### `PATCH /sandboxes/{sandbox_id}`

Update mutable sandbox fields.

Request body:

```json
{
  "alias": "manual-test-renamed",
  "metadata": {
    "owner": "agent"
  }
}
```

### `DELETE /sandboxes/{sandbox_id}`

Destroy the sandbox and delete the workspace directory. The path parameter accepts either the real sandbox ID or the configured alias.

### `POST /sandboxes/{sandbox_id}/pause`

Stop and remove the runtime container while keeping the sandbox workspace on disk.

Example response:

```json
{
  "ok": true
}
```

### `POST /sandboxes/{sandbox_id}/resume`

Recreate the runtime container for a sandbox in `STOPPED` state and remount the existing workspace.

Behavior notes:

- Returns `409` if the sandbox is not currently `STOPPED`.
- Returns `{ "ok": false }` if resume was attempted from `STOPPED` but the runtime could not be started.

Example response:

```json
{
  "ok": true
}
```

### `POST /sandboxes/{sandbox_id}/browser/restart`

Restart Chromium inside the sandbox.

Request body:

```json
{
  "level": "hard"
}
```

## Browser

### `GET /sandboxes/{sandbox_id}/browser/info`

Returns browser version, protocol version, whether a CDP WebSocket is available, and the active window viewport.

### `GET /sandboxes/{sandbox_id}/browser/viewport`

Returns the full window viewport, inferred page viewport, and active X11 window metadata.

### `GET /sandboxes/{sandbox_id}/browser/screenshot`

Capture either the full browser window or the active page.

Query parameters:

- `type`: `window` or `page`
- `format`: `png`, `jpeg`, or `webp`
- `target_id`: optional CDP target ID for page screenshots

Response shape:

```json
{
  "type": "page",
  "format": "png",
  "media_type": "image/png",
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

### `POST /sandboxes/{sandbox_id}/browser/actions`

Execute GUI-level actions through `xdotool`.

Request body:

```json
{
  "actions": [
    { "type": "WAIT", "duration_ms": 500 },
    { "type": "MOVE_TO", "x": 300, "y": 200 },
    { "type": "CLICK", "x": 300, "y": 200 },
    { "type": "TYPE_TEXT", "text": "hello verge" },
    { "type": "HOTKEY", "keys": ["ctrl", "l"] }
  ],
  "continue_on_error": false,
  "screenshot_after": false
}
```

Supported action types:

- `MOVE_TO`
- `CLICK`
- `DOUBLE_CLICK`
- `RIGHT_CLICK`
- `MOUSE_DOWN`
- `MOUSE_UP`
- `DRAG_TO`
- `SCROLL`
- `TYPE_TEXT`
- `KEY_PRESS`
- `HOTKEY`
- `WAIT`

### `GET /sandboxes/{sandbox_id}/browser/cdp/info`

Returns the external CDP proxy URL and browser protocol metadata.

### `WS /sandboxes/{sandbox_id}/browser/cdp/browser`

Proxy WebSocket for browser-level CDP traffic. Use this URL from Playwright, Puppeteer, or another CDP client.

## VNC

### `POST /sandboxes/{sandbox_id}/vnc/tickets`

Issue a short-lived, one-time VNC ticket.

Example response:

```json
{
  "ticket": "hexpayload.signature"
}
```

### `GET /sandboxes/{sandbox_id}/vnc/?ticket=...`

Consumes the ticket, sets the `vnc_session` cookie, and returns the noVNC landing page.

This is the URL humans should open in a browser.

### `GET /sandboxes/{sandbox_id}/vnc/{asset_path}`

Proxy for noVNC static assets. Requires a valid `vnc_session` cookie.

### `WS /sandboxes/{sandbox_id}/vnc/websockify`

WebSocket proxy for the VNC data channel. Requires a valid `vnc_session` cookie.

## Files

### `GET /sandboxes/{sandbox_id}/files/list?path=/workspace`

List files under a workspace-relative path.

### `GET /sandboxes/{sandbox_id}/files/read?path=/workspace/file.txt`

Read a text file and return its content inline.

### `POST /sandboxes/{sandbox_id}/files/write`

Write a text file.

Request body:

```json
{
  "path": "/workspace/notes.txt",
  "content": "hello verge",
  "overwrite": true
}
```

### `POST /sandboxes/{sandbox_id}/files/upload`

Upload a multipart file into the sandbox.

Form field:

- `upload`: file payload

### `GET /sandboxes/{sandbox_id}/files/download?path=/workspace/notes.txt`

Download a file as a regular file response.

### `DELETE /sandboxes/{sandbox_id}/files?path=/workspace/notes.txt`

Delete a file or directory entry inside the workspace.
