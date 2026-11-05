# Deployment Guide

English | [中文](deployment.zh.md)

[Project home](../../README.md) · [Deployment](deployment.md) · [Usage](usage.md) · [Development](development.md)

For a server, follow the [private Linux deployment guide](headless-linux.md). The Compose example below is for local evaluation; the Docker commands cover manual deployment.

## Get the Source

Install Docker and Docker Compose, then clone the repository:

```bash
git clone https://github.com/zzzgydi/verge-browser.git
cd verge-browser
```

Run all commands below from the repository root.

## Try Locally with Docker Compose

Use these commands for trusted local development only.
Do not expose this development example on a public VPS.
It publishes port 8000 on all host interfaces and uses development secrets.
Run from the repository root.

```bash
export PROJECT_ROOT="$PWD"
docker compose -f deployments/docker-compose.yml build api runtime-xvfb runtime-xpra
docker compose -f deployments/docker-compose.yml up api
```

Open the [admin console](http://127.0.0.1:8000/admin).

For local development, sign in with the default admin token `dev-admin-token` unless you override `VERGE_ADMIN_AUTH_TOKEN`.

For a server deployment, use the [private Linux deployment guide](../../docs/guides/headless-linux.md).

Deployment-related environment variables are documented in [`docs/env.md`](../../docs/env.md).

## Manual Docker Deployment

Keep this API private. The command publishes port 8000 on all host interfaces.
For a public server, use the [private deployment guide](../../docs/guides/headless-linux.md).

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

> **Note**: For GPU acceleration on Linux, add the device flag to `docker run`. The API container uses it to detect the GPU:
>
> - **Intel / AMD**: `--device /dev/dri:/dev/dri`
> - **NVIDIA** (requires [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) on the host): `--gpus all`

Mount the project at the same absolute path on the host and inside the API container.
Runtime containers use that path to mount sandbox workspaces.

For a complete list of deployment env vars, see [`docs/env.md`](../../docs/env.md).

Once the service is running, follow the [usage guide](usage.md) to create a sandbox. To work on the source, see the [development guide](development.md).
