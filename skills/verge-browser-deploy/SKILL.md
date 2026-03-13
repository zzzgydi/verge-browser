---
name: verge-browser-deploy
description: Deploy Verge Browser, including Docker Compose setup, environment preparation, health checks, and fallback local-dev startup. Use when the user wants to install, start, verify, or troubleshoot a Verge Browser deployment.
---

# Purpose

Use this skill when the user needs to deploy Verge Browser from source, start the API service, prepare runtime images, or diagnose why deployment is not working.

This skill is for host-level setup and service bring-up. If the service is already running and the user mainly wants to create sandboxes, get CDP URLs, or pair Verge Browser with `agent-browser`, use `verge-browser-usage` instead.

## Workflow

1. If the current directory does not contain this repository, clone `https://github.com/zzzgydi/verge-browser` first.
2. Confirm Docker is installed and usable.
3. Prefer Docker Compose unless the user explicitly wants a local development server.
4. Prepare `.env`, `PROJECT_ROOT`, and `.local/sandboxes`.
5. Build runtime images and start the API service.
6. Verify `/healthz` and, if needed, the admin UI.
7. If deployment fails, debug path mounts, Docker socket access, request host/scheme handling, and WebSocket support.

## Before You Run Anything

If this document was copied out of the repository, do not assume files like `deployments/docker-compose.yml` or `docker/runtime-xvfb.Dockerfile` already exist in the current directory.

Fetch the source first:

```bash
git clone https://github.com/zzzgydi/verge-browser
cd verge-browser
```

Minimum prerequisite:

- a working Docker environment with `docker` and `docker compose`

The browser GUI runs inside runtime containers. The host does not need a desktop session.

## Preferred Deployment Procedure

Run these steps from the repository root unless the user already has an equivalent deployment:

```bash
git clone https://github.com/zzzgydi/verge-browser
cd verge-browser

cat > .env <<'EOF'
VERGE_ENV=production
VERGE_ADMIN_AUTH_TOKEN=replace-with-a-long-random-token
VERGE_TICKET_SECRET=replace-with-an-even-longer-random-secret
EOF

export PROJECT_ROOT="$PWD"
mkdir -p .local/sandboxes

docker compose -f deployments/docker-compose.yml build api runtime-xvfb runtime-xpra
docker compose -f deployments/docker-compose.yml up -d api
curl http://127.0.0.1:8000/healthz
```

`.env` meanings:

- `VERGE_ENV`
  Runtime mode. Use `production` for non-dev deployments. Outside development, the server enforces stronger secret validation.
- `VERGE_ADMIN_AUTH_TOKEN`
  The admin token required by all business APIs, by the CLI / SDK, and also when signing in to the admin dashboard.
- `VERGE_TICKET_SECRET`
  Secret used to sign short-lived session and CDP tickets. In production it must be non-default and at least 32 characters.

`PROJECT_ROOT` meaning:

- absolute path to the cloned repository
- used by `deployments/docker-compose.yml` for the working directory, bind mount, and `VERGE_SANDBOX_BASE_DIR`

Expected health response:

```json
{"status":"ok"}
```

If the user asks for a development setup, use the local-dev path from `references/deploy-checklist.md`.

## Base URL And Public Access

There is no dedicated `BASE_URL` environment variable in the current server.

Current behavior:

- ticketed `session_url` and `cdp_url` are generated from the incoming request's host and scheme
- so the externally visible Base URL is determined by how the API is accessed

Implications:

- if you call the API as `http://127.0.0.1:8000`, returned URLs will point to `127.0.0.1:8000`
- if you want returned URLs to use a public domain such as `https://verge.example.com`, access Verge Browser through that domain or put a reverse proxy in front of it

Typical reverse-proxy pattern:

1. Expose Verge Browser behind a public hostname such as `https://verge.example.com`.
2. Forward HTTP and WebSocket traffic to the API service on port `8000`.
3. Use that public hostname when calling the API, CLI, or SDK.

Client-side examples:

```bash
export VERGE_BROWSER_URL="https://verge.example.com"
export VERGE_BROWSER_TOKEN="replace-with-your-admin-token"
```

Reverse-proxy requirement:

- preserve WebSocket upgrades for `/sandbox/.../cdp/browser` and `/sandbox/.../session/...`

## What To Verify After Startup

- `http://127.0.0.1:8000/healthz` returns `{"status":"ok"}`
- `http://127.0.0.1:8000/admin` is reachable if the admin UI is needed
- you can sign in to the admin dashboard with `VERGE_ADMIN_AUTH_TOKEN`
- the API service can talk to `/var/run/docker.sock`
- runtime images `verge-browser-runtime-xvfb:latest` and `verge-browser-runtime-xpra:latest` exist or can be built

## Troubleshooting Priorities

When deployment fails, check in this order:

1. Docker is available and healthy.
2. `PROJECT_ROOT` and `VERGE_SANDBOX_BASE_DIR` point to valid paths.
3. If the API runs in Docker, the repo path inside the container matches the host path exactly.
4. The API container can access `/var/run/docker.sock`.
5. If URLs point to the wrong host, call the API through the intended external domain instead of a local host alias.
6. The fronting proxy preserves WebSocket upgrades.

## References

- Read `references/deploy-checklist.md` for exact commands by deployment mode.
- Read `references/troubleshooting.md` for common runtime and path-mount failures.
