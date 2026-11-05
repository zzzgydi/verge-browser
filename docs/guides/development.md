# Development Guide

English | [中文](development.zh.md)

[Project home](../../README.md) · [Deployment](deployment.md) · [Usage](usage.md) · [Development](development.md)

Run all commands from the repository root. If you only need to run the service, follow the [deployment guide](deployment.md).

## Local Development Setup

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

Keep this development server private. `--host 0.0.0.0` listens on all host interfaces.

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

API: [http://127.0.0.1:8000](http://127.0.0.1:8000).
Admin console: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin).

## Development Workflow

### Admin Web Development

For admin UI development, run Vite separately:

```bash
pnpm --dir apps/admin-web dev
```

The dev server listens on [http://127.0.0.1:5173](http://127.0.0.1:5173).

### Run Tests

Use a Docker daemon without sandboxes you want to keep.
The `test_runtime_api.py` cleanup fixture removes all managed containers.

Run the test suite:

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

Smoke-test scripts are in [`tests/scripts`](../../tests/scripts).

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

Management APIs require the admin bearer token. Set:

```bash
export VERGE_BROWSER_TOKEN="<admin-token>"
```

### Cleanup Development Containers

Confirm that all managed development containers can be removed before running this command.
It forcibly removes every container with `verge.managed=true` on this Docker daemon.

Remove containers:

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
docker rm -f verge-api 2>/dev/null || true
```

Back up data before running full cleanup.
The next command also deletes `.local/sandboxes`, including browser profiles and shared files.

Remove containers and persisted data:

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
rm -rf .local/sandboxes
```

Use `down` to stop Compose services.
Use `down -v` only when you intend to remove their volumes too:

```bash
docker compose -f deployments/docker-compose.yml down
docker compose -f deployments/docker-compose.yml down -v
```

### Development Notes

- The project targets Python 3.11+.
- The API server is implemented with FastAPI.
- WebSocket proxying is designed around CDP and session relay use cases.
- File operations are constrained to the sandbox workspace root.
- Containerized API deployment uses Docker-outside-of-Docker via `/var/run/docker.sock`.
- The current implementation targets single-node use, not multi-tenant orchestration.

## Project Structure and Runtimes

### System Architecture

The platform has two parts:

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

### Technical Notes

The project targets local development and single-node deployment.

The source includes:

- runtime container boot with Chromium, Xvfb/Openbox or Xpra, and a CDP relay
- sandbox creation through the API
- persisted sandbox metadata with startup reconciliation of surviving runtime containers; records without a running container remain `STOPPED`
- pause and resume lifecycle for reusing an existing workspace
- real window screenshots
- page screenshots through CDP
- GUI action execution through `xdotool`
- ticket-based session entry for noVNC and Xpra
- workspace-scoped file list, read, write, upload, download, and delete operations
- an admin web console built into static assets and served by the API at `/admin`
- runtime Dockerfiles, supervisor configuration, startup scripts, and Docker-backed integration coverage

Areas that require further hardening:

- stronger Docker lifecycle management and health-driven state transitions
- production-ready browser crash recovery and degraded-state handling
- file and browser integration coverage
- broader end-to-end and failure-mode coverage

### Repository Layout

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

### Runtime Images

The runtime images host:

- Chromium
- xdotool
- supervisor
- a TCP relay that exposes a stable CDP entry point while Chromium listens on an internal debugging port

Two runtime variants are supported:

- `xvfb_vnc`: Xvfb + Openbox + x11vnc + noVNC / websockify
- `xpra`: Xpra server + HTML5 client assets
