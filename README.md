# Verge Browser

English | [中文](./README.zh.md)

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
- persisted sandbox metadata with startup recovery into `STOPPED`
- pause / resume lifecycle for reusing an existing workspace
- real window screenshots
- real page screenshots through CDP
- GUI action execution through `xdotool`
- ticket-based VNC entry with noVNC asset proxying

Some parts are still not production-hard yet, especially health-driven lifecycle transitions, browser crash recovery semantics, and broader integration / E2E coverage.

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

- sandbox create / get / pause / resume / delete flow with Docker-backed runtime startup
- persisted workspace metadata and startup recovery for stopped sandboxes
- browser info, viewport, screenshot, actions, restart, and CDP proxying
- ticket-based VNC entry with noVNC asset proxying
- shell one-shot execution and interactive shell sessions
- workspace-scoped file list, read, write, upload, download, and delete operations
- runtime Dockerfile, supervisor configuration, startup scripts, and Docker-backed integration coverage

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

### Option 1: Local Development

**Prerequisites:**

- Python 3.11+
- Docker (for building and running the runtime image)

**1. Install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**2. Build the runtime image**

```bash
docker build -f docker/runtime-image.Dockerfile -t verge-browser-runtime:latest .
```

**3. Start the API server**

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

The API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Option 2: Docker Deployment (Recommended)

Run the API server and runtime entirely in Docker.

```bash
# Build the runtime image (contains Chromium, VNC, etc.)
docker build -f docker/runtime-image.Dockerfile -t verge-browser-runtime:latest .

# Build the API server image
docker build -f docker/api-server.Dockerfile -t verge-browser-api:latest .

# Create a directory for sandbox persistence
mkdir -p .local/sandboxes

# Run the API server container
docker run -d \
  --name verge-api \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$(pwd)/.local/sandboxes:/app/.local/sandboxes" \
  -e VERGE_SANDBOX_BASE_DIR=/app/.local/sandboxes \
  verge-browser-api:latest
```

The API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Option 3: Docker Compose

For convenience, use the provided compose file:

```bash
export PROJECT_ROOT="$PWD"
docker compose -f deployments/docker-compose.yml build api runtime-image
docker compose -f deployments/docker-compose.yml up api
```

### Run Tests

```bash
PYTHONPATH=apps/api-server pytest
```

To include Docker-backed integration coverage:

```bash
PYTHONPATH=apps/api-server pytest -m integration
```

### Manual Smoke Scripts

Human-friendly smoke scripts live under [`tests/scripts`](./tests/scripts).

Common flows:

- `tests/scripts/create-sandbox.sh`
  Creates a sandbox and prints the IDs and follow-up URLs you need.
- `tests/scripts/get-vnc-url.sh`
  Always creates a fresh sandbox and prints a browser-ready noVNC URL that you can open directly.
- `tests/scripts/browser-smoke.sh`
  Saves browser metadata plus window and page screenshots under `tests/scripts/.artifacts/`.
- `tests/scripts/file-shell-smoke.sh`
  Verifies that `/workspace` files are visible from both the file API and shell exec.
- `tests/scripts/restart-browser.sh`
  Restarts Chromium and saves browser info before and after.
- `tests/scripts/full-manual-tour.sh`
  Runs the most useful create + screenshot + shell/files + VNC flow end to end.
- `tests/scripts/cleanup-sandbox.sh`
  Deletes a sandbox when you pass `SANDBOX_ID=...`.

Example:

```bash
tests/scripts/full-manual-tour.sh
```

If your API server is not on `http://127.0.0.1:8000`, set:

```bash
export BASE_URL="http://127.0.0.1:8000"
```

If you want to attach a bearer token, set:

```bash
export AUTH_TOKEN="<jwt>"
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

The API follows the `/sandboxes/{sandbox_id}/...` routing model from [`docs/tech.md`](./docs/tech.md).

Detailed endpoint documentation lives in [`docs/api.md`](./docs/api.md).

## What Is Still In Progress

The following areas still need deeper implementation work before the project reaches the full V1 target described in [`docs/tech.md`](./docs/tech.md):

- stronger Docker lifecycle management and health-driven state transitions
- production-ready browser crash recovery and degraded-state handling
- shell/files/browser cross-feature integration coverage
- broader end-to-end and failure-mode coverage

## Development Notes

- The project targets Python 3.11+.
- The API server is implemented with FastAPI.
- WebSocket proxying is designed around CDP and VNC relay use cases.
- File operations are constrained to the sandbox workspace root.
- Containerized API deployment uses Docker-outside-of-Docker via `/var/run/docker.sock`.
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

This project is licensed under the MIT License. See [LICENSE](./LICENSE).
