# Verge Browser

Verge Browser is a browser sandbox platform for agents.

It provides a single-session isolated runtime with:

- a real GUI Chromium instance
- Chrome DevTools Protocol (CDP) access
- VNC / noVNC human takeover
- GUI-level screenshots and input automation
- a shared `/workspace` file system
- shell execution and interactive terminal sessions
- a unified REST and WebSocket control plane

## Status

This repository is in active build-out.

The current codebase now includes a working runtime image and a live end-to-end control path for the main browser sandbox loop:

- runtime container boot with Chromium, Xvfb, Openbox, x11vnc, websockify, and a CDP relay
- sandbox creation through the API
- real window screenshots
- real page screenshots through CDP
- GUI action execution through `xdotool`
- ticket-based VNC entry with noVNC asset proxying

Some parts are still not production-hard yet, especially long-term lifecycle management, restart recovery semantics, and broader integration / E2E coverage.

## Why This Exists

Most browser automation systems focus on headless page control. That is not enough for agent workflows that need to combine:

- browser automation through CDP
- visual reasoning over the full browser window
- human takeover when automation stalls
- shared files and shell access inside the same environment

Verge Browser is designed to close that gap with a runtime model that keeps browser, GUI, shell, and files in one isolated sandbox.

## Architecture

At a high level, the platform is split into two parts:

1. API server
   Exposes REST and WebSocket endpoints for sandbox lifecycle, browser control, shell access, files, CDP proxying, and ticket-based VNC access.

2. Sandbox runtime
   Runs Chromium, Xvfb, Openbox, x11vnc, websockify, and supervisor inside a single isolated container with a shared `/workspace`.

```text
Client / Agent / Human
        |
        v
+------------------------------+
| FastAPI Gateway / API Server |
| Auth + REST + WS + Tickets   |
+------------------------------+
        |
        v
+-----------------------------------------------+
| Sandbox Runtime Container                     |
| Xvfb + Openbox + Chromium + x11vnc + tmux     |
| websockify + supervisor + /workspace          |
+-----------------------------------------------+
```

## Current Capabilities

The repository currently implements:

- FastAPI application bootstrap and configuration
- sandbox create / get / delete flow with an in-memory registry and Docker-backed runtime startup
- browser routes for info, viewport, screenshot, actions, restart, and CDP metadata
- real window screenshots through X11 `import`
- real page screenshots through CDP `Page.captureScreenshot`
- CDP browser WebSocket proxy
- VNC ticket issuance, noVNC asset proxying, and VNC WebSocket proxy
- shell one-shot command execution
- interactive shell session creation with WebSocket streaming
- file list, read, write, upload, download, and delete APIs
- `/workspace` path safety checks
- ticket signing, verification, and one-time consumption
- runtime Dockerfile, supervisor configuration, startup scripts, and smoke-tested Chromium runtime

## Repository Layout

```text
apps/
  api-server/         FastAPI application
  sandbox-runtime/    Runtime scripts and supervisor config
deployments/          Local deployment assets
docker/               Runtime container build files
tests/                Unit tests
```

## Quick Start

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Start the API server

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

### 3. Build the runtime image

```bash
docker build -f docker/runtime/Dockerfile -t verge-browser-runtime:latest .
```

### 4. Run tests

```bash
PYTHONPATH=apps/api-server pytest
```

To include Docker-backed integration coverage:

```bash
PYTHONPATH=apps/api-server pytest -m integration
```

## Runtime Image

The runtime image hosts:

- Chromium
- Xvfb
- Openbox
- x11vnc
- noVNC / websockify
- tmux
- xdotool
- supervisor

It also includes a small TCP relay so the platform can expose a stable CDP entrypoint even though Chromium itself listens on the internal debugging port.

## API Surface

The current API structure follows the `/sandboxes/{sandbox_id}/...` convention from the design document.

Representative endpoints:

- `POST /sandboxes`
- `GET /sandboxes/{id}`
- `DELETE /sandboxes/{id}`
- `GET /sandboxes/{id}/browser/info`
- `GET /sandboxes/{id}/browser/screenshot`
- `POST /sandboxes/{id}/browser/actions`
- `POST /sandboxes/{id}/browser/restart`
- `GET /sandboxes/{id}/browser/cdp/info`
- `WS /sandboxes/{id}/browser/cdp/browser`
- `POST /sandboxes/{id}/vnc/tickets`
- `WS /sandboxes/{id}/vnc/websockify`
- `POST /sandboxes/{id}/shell/exec`
- `POST /sandboxes/{id}/shell/sessions`
- `WS /sandboxes/{id}/shell/sessions/{session_id}/ws`
- `GET /sandboxes/{id}/files/list`
- `GET /sandboxes/{id}/files/read`
- `POST /sandboxes/{id}/files/write`
- `POST /sandboxes/{id}/files/upload`
- `GET /sandboxes/{id}/files/download`
- `DELETE /sandboxes/{id}/files`

## What Is Still In Progress

The following areas still need deeper implementation work before the project reaches the full V1 target described in [`docs/tech.md`](./docs/tech.md):

- stronger Docker lifecycle management and health-driven state transitions
- production-ready browser restart and degraded-state recovery
- shell/files/browser cross-feature integration coverage
- broader end-to-end and failure-mode coverage

## Development Notes

- The project targets Python 3.11+.
- The API server is implemented with FastAPI.
- WebSocket proxying is designed around CDP and VNC relay use cases.
- File operations are constrained to the sandbox workspace root.
- The current implementation favors a practical MVP structure over premature distribution or multi-tenant orchestration.

## Roadmap

The intended implementation order remains:

1. Harden the runtime container until Chromium, CDP, and VNC are reliable.
2. Expand Playwright / CDP compatibility validation beyond low-level smoke checks.
3. Strengthen VNC session management and WebSocket lifecycle behavior.
4. Expand shell, file, and integration testing coverage.
5. Add failure injection tests for browser restarts and runtime degradation.
6. Add deployment polish, observability, and production hardening.

## License

No license has been added yet.
