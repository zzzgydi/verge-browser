# CLAUDE.md

## Overview

Verge Browser is a browser sandbox system for agent workflows. The current repository contains a functional MVP path:

- build the runtime image
- create a sandbox through the API
- take real window and page screenshots
- execute GUI actions
- open a ticketed VNC entry
- run file APIs inside the same workspace

## Repository Conventions

- API code lives in `apps/api-server/app`.
- Runtime scripts live in `apps/runtime-xvfb/scripts` and `apps/runtime-xpra/scripts`.
- Supervisor wiring lives in `apps/runtime-xvfb/supervisor` and `apps/runtime-xpra/supervisor`.
- Integration tests that require Docker live under `tests/integration`.
- Use **Conventional Commits** for all `git commit` messages.
- Do not leak local developer information in generated code or `git commit` messages, including machine-specific paths, usernames, home directories, or other local environment details.

## Development Workflow

### Local Python setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run the API server

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

### Build the runtime image

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
```

### Run tests

```bash
PYTHONPATH=apps/api-server pytest tests/unit
PYTHONPATH=apps/api-server pytest -m integration tests/integration/test_runtime_api.py
```

## Implementation Notes

- The runtime currently assumes Docker is the sandbox backend.
- `BrowserService` contains the real screenshot, viewport discovery, and CDP screenshot logic.
- `SandboxLifecycleService` owns startup readiness and container cleanup.
- `DockerAdapter` is the boundary for Docker interactions. Prefer extending it instead of scattering `docker` shell calls.

## When Updating This Repo

- Keep README in sync with what is actually validated.
- Add or extend integration tests whenever runtime behavior changes.
- If you change runtime ports, update both the Docker image and the API-side runtime metadata.
- If you change screenshot or session behavior, validate against a real built runtime image before considering the change done.
