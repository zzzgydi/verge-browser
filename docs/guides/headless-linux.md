# Deploy on a Headless Linux Server

The host does not need a desktop environment or a monitor. The runtime image supplies Xvfb/Openbox or Xpra and runs **GUI Chromium**, not Chromium's headless mode.

This recipe uses a single Linux Docker host and an SSH tunnel. The API has access to the host Docker socket: deploy it on a trusted host, not as an isolation boundary for mutually untrusted tenants.

## Start a Private API with Docker Compose

Prerequisites: Docker Engine with Compose, Git, OpenSSL, and permission to access the Docker daemon. Run these commands in Bash on the server:

```bash
set -euo pipefail
git clone https://github.com/zzzgydi/verge-browser.git
cd verge-browser
export PROJECT_ROOT="$PWD"

VERGE_ADMIN_AUTH_TOKEN="$(openssl rand -hex 32)"
VERGE_TICKET_SECRET="$(openssl rand -hex 32)"
export VERGE_ADMIN_AUTH_TOKEN VERGE_TICKET_SECRET

docker compose -f deployments/docker-compose.yml build api runtime-xvfb
docker compose -f deployments/docker-compose.yml run -d \
  --name verge-api-private \
  --publish 127.0.0.1:8000:8000 \
  -e VERGE_ENV=production \
  -e VERGE_ADMIN_AUTH_TOKEN \
  -e VERGE_TICKET_SECRET \
  api

curl --fail http://127.0.0.1:8000/healthz
```

Unlike `compose up`, `compose run` does not publish the service's default ports; the explicit `--publish` binds this container to loopback only. Do not add `--service-ports` or start the stock `api` service alongside it. Check the binding with `docker port verge-api-private 8000`: it should show `127.0.0.1:8000`.

The Compose service sets `VERGE_SANDBOX_RUNTIME_NETWORK` to `${COMPOSE_PROJECT_NAME}_default`, so the API and the browser containers it creates share the project's network. This also follows a custom Compose project name (`-p`). If you override the network name, update this setting to match; the standalone API default, `bridge`, is a different network. Do not publish runtime ports to work around a network mismatch.

Existing runtime containers are not moved automatically when this setting changes. A sandbox pause/resume recreates its container on the configured network, but ends the live browser session; coordinate that interruption before upgrading an existing deployment.

The `-e` options explicitly pass the secrets into the API container; merely exporting them on the host does not change the stock Compose service environment. Store the generated values in your private secret manager before ending this shell, and securely transfer the admin token to your client. Do not commit them. Reusing the same secrets matters when recreating the API container; rotating the ticket secret invalidates previously issued tickets.

For Xpra, also build `runtime-xpra` and create a sandbox with `--kind xpra`.

`/healthz` confirms only that the API is up, not that Chromium can start. Create a sandbox and verify `RUNNING`, CDP access, and the visual session using the [integration guide](../integrations/codex.md#1-create-or-reuse-a-sandbox).

## Access from Your Computer

Run this on your computer, replacing `user@server` with your SSH destination, and leave the tunnel running:

```bash
ssh -N -L 127.0.0.1:8000:127.0.0.1:8000 user@server
```

Open [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin) locally and sign in with the server's admin token. Configure the CLI on that same computer:

```bash
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
read -r -s -p "Verge admin token: " VERGE_BROWSER_TOKEN; echo
export VERGE_BROWSER_TOKEN
```

Request CDP and session URLs through this client URL so the returned addresses are reachable from your computer. If local port 8000 is occupied, change the first port in the SSH forward and in the client URL. Do not open public runtime ports to make the client connect.

For direct access through a domain instead, use HTTPS, WebSocket forwarding, correctly trusted proxy headers, strong secrets, and appropriate network restrictions. The SSH recipe avoids requiring public API exposure.

## Keep Data and Inspect Failures

The supplied Compose service mounts the checkout at the same absolute path inside the API container as on the Docker host. Runtime workspaces are bind-mounted from that path under `.local/sandboxes`. Keep that directory and mount mapping when recreating the API. A machine migration or backup also needs the metadata and profile files, not just the container image.

```bash
docker logs --tail 100 verge-api-private
docker ps --filter label=verge.managed=true
```

Inspect logs locally; do not publish browser content, tokens, or ticketed URLs from them. After a host reboot, start the API container with `docker start verge-api-private`, inspect sandbox state, and resume stopped sandboxes explicitly. This command recipe does not configure automatic service startup or full session restoration.

For the exact persistence behavior, see [Persistent Browser Profiles](persistent-profiles.md). For server settings, see [Environment Variables](../env.md).

The Compose model and command options have been checked, but this deployment recipe still needs a live Linux/Docker smoke test before being treated as a verified deployment walkthrough.
