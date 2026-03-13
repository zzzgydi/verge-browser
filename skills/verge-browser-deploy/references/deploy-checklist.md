# Deploy Checklist

## Recommended: Docker Compose

If this file is being read outside the repository tree, fetch the source first:

```bash
git clone https://github.com/zzzgydi/verge-browser
cd verge-browser
```

Run from the repository root:

```bash
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

Key variables:

- `VERGE_ENV=production`
  Enables production-mode secret checks.
- `VERGE_ADMIN_AUTH_TOKEN`
  Admin token required by API, CLI, SDK requests, and admin dashboard sign-in.
- `VERGE_TICKET_SECRET`
  Secret used for CDP and session ticket signing.
- `PROJECT_ROOT`
  Absolute repository path consumed by `deployments/docker-compose.yml`.

## Public Base URL

The current server does not have a dedicated Base URL env var.

Returned `session_url` and `cdp_url` are derived from the incoming request base URL. To make returned URLs use a public hostname:

1. put Verge Browser behind that hostname with a reverse proxy
2. preserve WebSocket support
3. call the API using the public hostname

Example client setup:

```bash
export VERGE_BROWSER_URL="https://verge.example.com"
export VERGE_BROWSER_TOKEN="replace-with-your-admin-token"
```

## Local API Development

Use only when editing backend code:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"

corepack enable
pnpm --dir apps/admin-web install --frozen-lockfile
pnpm --dir apps/admin-web build

docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .

uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

## API In Docker With Host Docker Socket

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
docker build -f docker/api-server.Dockerfile -t verge-browser-api:latest .

mkdir -p .local/sandboxes

export VERGE_ADMIN_AUTH_TOKEN="replace-with-a-long-random-token"
export VERGE_TICKET_SECRET="replace-with-a-long-random-secret"

docker run -d \
  --name verge-api \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:$PWD" \
  -e VERGE_SANDBOX_BASE_DIR="$PWD/.local/sandboxes" \
  -e VERGE_ADMIN_AUTH_TOKEN="$VERGE_ADMIN_AUTH_TOKEN" \
  -e VERGE_TICKET_SECRET="$VERGE_TICKET_SECRET" \
  -w "$PWD" \
  verge-browser-api:latest
```

Critical rule:

- the path visible inside the API container must match the host path exactly
