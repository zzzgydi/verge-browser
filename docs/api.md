# API Reference

This document describes the current Verge Browser control plane API.

Base convention:

- REST resources are scoped under `/sandboxes/{sandbox_id}/...`
- WebSocket resources follow the same sandbox scoping model
- `Authorization: Bearer <token>` is optional in the current build; without it the subject defaults to `anonymous`

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

Request body:

```json
{
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
- `status`: lifecycle status
- `browser.cdp_url`: external CDP proxy URL
- `browser.vnc_entry_base_url`: VNC landing URL prefix
- `browser.vnc_ticket_endpoint`: endpoint for a one-time VNC ticket

### `GET /sandboxes/{sandbox_id}`

Return current sandbox metadata and browser access info.

### `DELETE /sandboxes/{sandbox_id}`

Destroy the sandbox and delete the workspace directory.

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

## Shell

### `POST /sandboxes/{sandbox_id}/shell/exec`

Run a one-shot shell command in the sandbox workspace.

Exactly one of `argv` or `command` must be provided.

Request with `argv`:

```json
{
  "argv": ["bash", "-lc", "pwd && ls -la"],
  "cwd": "/workspace",
  "timeout_sec": 30
}
```

Response:

```json
{
  "exit_code": 0,
  "stdout": "/workspace\n...",
  "stderr": "",
  "duration_ms": 18
}
```

### `POST /sandboxes/{sandbox_id}/shell/sessions`

Create an interactive shell session.

Query parameters:

- `cwd`: working directory, default `/workspace`

Response:

```json
{
  "session_id": "abcd1234",
  "ws_url": "/sandboxes/{sandbox_id}/shell/sessions/abcd1234/ws"
}
```

### `WS /sandboxes/{sandbox_id}/shell/sessions/{session_id}/ws`

Interactive shell stream. Send text frames as stdin and receive text frames as stdout.

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
