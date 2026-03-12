# Verge Browser

English | [中文](./README.zh.md)

A browser sandbox platform for AI agents, combining CDP automation, GUI-level screenshots, shared files, and visual human handoff in one isolated runtime.

## Core Capabilities

- **Real GUI Chromium**: not headless; supports multi-tabs, downloads, popups, and full browser behavior
- **CDP Automation**: compatible with Playwright and Puppeteer through a WebSocket endpoint
- **GUI-Level Screenshots**: capture the full browser window, not only page content
- **Human Handoff**: unified session entry for both noVNC and Xpra
- **File Sharing**: browser and APIs share `/workspace` for uploads, downloads, and artifacts

## Desktop Options Comparison

| Feature            | `xvfb_vnc`                               | `xpra`                                     |
| ------------------ | ---------------------------------------- | ------------------------------------------ |
| Stack              | Xvfb + x11vnc + noVNC                    | Xpra Server + HTML5 Client                 |
| Latency            | Medium                                   | Low                                        |
| Clipboard          | One-way (manual sync)                    | Bidirectional auto-sync                    |
| Network Adaptation | Good                                     | Excellent                                  |
| Use Case           | Automation-first, occasional human check | Frequent human collaboration and debugging |
| Usage              | Set `kind: "xvfb_vnc"` on create         | Set `kind: "xpra"` on create               |

How to choose:

- Mostly automation, with occasional human inspection: use `xvfb_vnc`
- Frequent manual intervention or remote debugging: use `xpra`

## Status

The platform is functional today for local development and single-node deployment.

The current codebase already includes:

- runtime container boot with Chromium, Xvfb/Openbox or Xpra, and a CDP relay
- sandbox creation through the API
- persisted sandbox metadata with startup recovery into `STOPPED`
- pause and resume lifecycle for reusing an existing workspace
- real window screenshots
- page screenshots through CDP
- GUI action execution through `xdotool`
- ticket-based session entry for noVNC and Xpra

Current hardening work is focused on health-driven lifecycle transitions, browser crash recovery semantics, and broader integration and E2E coverage.

## Why This Exists

Most browser automation systems focus on headless page control. That is not enough for agent workflows that need to combine:

- browser automation through CDP
- visual reasoning over the full browser window
- human takeover when automation stalls
- shared files inside the same environment

Verge Browser keeps browser, GUI, and files in one isolated sandbox so those workflows remain continuous instead of split across multiple tools.

## Architecture

At a high level, the platform has two parts:

1. API server
   Exposes REST and WebSocket endpoints for sandbox lifecycle, browser control, files, CDP proxying, and ticket-based session access.
2. Sandbox runtime
   Runs Chromium, the desktop stack, and shared `/workspace` inside one isolated container.

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
| xvfb_vnc or xpra + Chromium + /workspace      |
+-----------------------------------------------+
```

## Current Capabilities

The repository currently implements:

- sandbox create / get / pause / resume / delete flow with Docker-backed runtime startup
- persisted workspace metadata and startup recovery for stopped sandboxes
- browser screenshot, actions, restart, and CDP proxying
- ticket-based session entry with noVNC or Xpra asset proxying
- workspace-scoped file list, read, write, upload, download, and delete operations
- an admin web console built into static assets and served by the API at `/admin`
- runtime Dockerfiles, supervisor configuration, startup scripts, and Docker-backed integration coverage

## Repository Layout

```text
apps/
  api-server/         FastAPI application
  admin-web/          Vite + React admin console, built into API static assets
  runtime-xvfb/       Xvfb + VNC runtime assets
  runtime-xpra/       Xpra runtime assets
deployments/          Local deployment assets
docker/               Runtime and API container build files
tests/                Unit and integration tests
docs/                 Product, API, and technical docs
```

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
export PROJECT_ROOT="$PWD"
docker compose -f deployments/docker-compose.yml build api runtime-xvfb runtime-xpra
docker compose -f deployments/docker-compose.yml up api
```

Open [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin) to start using.

For local development, sign in with the default admin token `dev-admin-token` unless you override `VERGE_ADMIN_AUTH_TOKEN`.

Deployment-related environment variables are documented in [`docs/env.md`](./docs/env.md).

### Option 2: Local Development

Prerequisites:

- Python 3.11+
- Node.js 22+ with Corepack / pnpm
- Docker

1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

2. Install and build the admin web

```bash
corepack enable
pnpm --dir apps/admin-web install --frozen-lockfile
pnpm --dir apps/admin-web build
```

This emits static files into `apps/api-server/app/static/admin`.

3. Build the runtime images

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
```

4. Start the API server

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

The API is available at [http://127.0.0.1:8000](http://127.0.0.1:8000), and the admin console is at [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin).

### Option 3: Docker Deployment

Run the API server in Docker and let it manage runtime containers through the host Docker socket.

```bash
# Build runtime images
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .

# Build API server image (also bundles the admin web)
docker build -f docker/api-server.Dockerfile -t verge-browser-api:latest .

# Create a directory for sandbox persistence
mkdir -p .local/sandboxes

# Set non-default auth secrets before exposing the service
export VERGE_ADMIN_AUTH_TOKEN="replace-with-a-long-random-token"
export VERGE_TICKET_SECRET="replace-with-a-long-random-ticket-secret"

# Run the API server container
docker run -d \
  --name verge-api \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$(pwd):$(pwd)" \
  -e VERGE_SANDBOX_BASE_DIR="$(pwd)/.local/sandboxes" \
  -e VERGE_ADMIN_AUTH_TOKEN="$VERGE_ADMIN_AUTH_TOKEN" \
  -e VERGE_TICKET_SECRET="$VERGE_TICKET_SECRET" \
  -w "$(pwd)" \
  verge-browser-api:latest
```

This mode expects the API container to see the same absolute project path as the host so it can mount sandbox workspaces into runtime containers correctly.

For a complete list of deployment env vars, see [`docs/env.md`](./docs/env.md).

### Basic Usage Examples

Install the CLI:

```bash
npm install -g verge-browser
```

Create a sandbox:

```bash
verge-browser sandbox create --alias test --width 1440 --height 900
```

Take a screenshot:

```bash
verge-browser browser screenshot test --output ./screenshot.png
```

Execute GUI actions:

```bash
verge-browser browser actions test --input ./actions.json
```

Get a human handoff URL:

```bash
verge-browser sandbox session test
```

For more commands, see [`docs/cli-sdk.md`](./docs/cli-sdk.md).

## Development Guide

### Admin Web Development

For admin UI development, run Vite separately:

```bash
pnpm --dir apps/admin-web dev
```

The dev server listens on [http://127.0.0.1:5173](http://127.0.0.1:5173).

### Run Tests

Run the full unit suite:

```bash
PYTHONPATH=apps/api-server pytest
```

Run the expected local validation flow for runtime-backed changes:

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
PYTHONPATH=apps/api-server pytest tests/unit tests/integration/test_runtime_api.py
```

### Manual Smoke Scripts

Human-friendly smoke scripts live under [`tests/scripts`](./tests/scripts).

Common flows:

- `tests/scripts/create-sandbox.sh`: create a sandbox and print the IDs and follow-up URLs you need
- `tests/scripts/get-session-url.sh`: create or reuse a sandbox and print a browser-ready session URL
- `tests/scripts/browser-smoke.sh`: save browser metadata plus window and page screenshots under `tests/scripts/.artifacts/`
- `tests/scripts/files-smoke.sh`: exercise the file APIs against `/workspace`
- `tests/scripts/restart-browser.sh`: restart Chromium and save browser info before and after
- `tests/scripts/full-manual-tour.sh`: run the most useful create + screenshot + files + session flow end to end
- `tests/scripts/cleanup-sandbox.sh`: delete a sandbox when you pass `SANDBOX_ID=...`

Example:

```bash
tests/scripts/full-manual-tour.sh
```

If your API server is not on `http://127.0.0.1:8000`, set:

```bash
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
```

Business APIs require the admin bearer token. Set:

```bash
export VERGE_BROWSER_TOKEN="<admin-token>"
```

### Cleanup Development Containers

Quick cleanup:

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
docker rm -f verge-api 2>/dev/null || true
```

Full cleanup, including persisted data:

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
rm -rf .local/sandboxes
```

Using Docker Compose:

```bash
docker compose -f deployments/docker-compose.yml down
docker compose -f deployments/docker-compose.yml down -v
```

## Runtime Image

The runtime images host:

- Chromium
- xdotool
- supervisor
- a small TCP relay so the platform can expose a stable CDP entrypoint even though Chromium itself listens on an internal debugging port

Two runtime variants are supported:

- `xvfb_vnc`: Xvfb + Openbox + x11vnc + noVNC / websockify
- `xpra`: Xpra server + HTML5 client assets

## API Surface

The current API follows the `/sandbox/{sandbox_id}/...` routing model.

Detailed endpoint documentation lives in [`docs/api.md`](./docs/api.md).

SDK and CLI usage examples live in [`docs/cli-sdk.md`](./docs/cli-sdk.md).

## Scope

Verge Browser focuses on browser control:

- browser lifecycle: create, pause, resume, delete
- browser automation via CDP
- GUI screenshots and input actions
- session-based human takeover with `xvfb_vnc` or `xpra`
- file exchange through the sandbox workspace

Arbitrary command execution is intentionally excluded to keep the surface area minimal and the focus narrow.

## Current Hardening Areas

- stronger Docker lifecycle management and health-driven state transitions
- production-ready browser crash recovery and degraded-state handling
- file and browser integration coverage
- broader end-to-end and failure-mode coverage

## Development Notes

- The project targets Python 3.11+.
- The API server is implemented with FastAPI.
- WebSocket proxying is designed around CDP and session relay use cases.
- File operations are constrained to the sandbox workspace root.
- Containerized API deployment uses Docker-outside-of-Docker via `/var/run/docker.sock`.
- The current implementation favors a practical MVP structure over premature multi-tenant orchestration.

## License

The original source code in this repository is licensed under the MIT License. See [LICENSE](./LICENSE).

Built runtime artifacts may include third-party software under separate licenses. In particular, the `runtime-xpra` image installs Xpra, which is licensed under GPL v2 or later and remains subject to its own license terms.

See [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) and [docs/open-source-compliance.md](./docs/open-source-compliance.md) before distributing container images externally.
