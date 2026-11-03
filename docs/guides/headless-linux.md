# Deploy on a Headless Linux Server

The host does not require a desktop environment or monitor. The runtime supplies Xvfb/Openbox or Xpra.
Chromium runs with a graphical interface, not in headless mode.

This recipe uses one Linux Docker host and an SSH tunnel.
Deploy it only on a trusted host. The API has access to the host Docker socket.
This deployment is not an isolation boundary between mutually untrusted tenants.

## Start a Private API with Docker Compose

Install Docker Engine with Compose, Git, and OpenSSL. Your account must have access to the Docker daemon.
Run the following commands in Bash on the server:

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

`compose run` does not publish the service's default ports. The explicit `--publish` binds this container to loopback only.
Do not add `--service-ports` or start the stock `api` service alongside it. Either can expose the API beyond loopback.

Check the binding with `docker port verge-api-private 8000`. The expected output is `127.0.0.1:8000`.

Compose sets `VERGE_SANDBOX_RUNTIME_NETWORK` to `${COMPOSE_PROJECT_NAME}_default`. The API and its browser containers use that network.
A custom Compose project name (`-p`) also changes this value.

If you override the network name, update this setting to match. The standalone API default, `bridge`, is a different network.
Do not publish runtime ports to work around a network mismatch.

Changing this setting does not move existing containers.
Before upgrading, coordinate a browser interruption with users. A sandbox pause/resume recreates its container on the configured network and ends the live session.

The `-e` options pass secrets into the API container. Host exports alone do not change the stock Compose service environment.

1. Store the generated secrets in your private secret manager before ending this shell.
2. Transfer the admin token securely to your client.
3. Reuse the secrets when recreating the API container.

Do not commit secrets. Rotating the ticket secret invalidates existing tickets.

For Xpra, also build `runtime-xpra` and create a sandbox with `--kind xpra`.

`/healthz` confirms only API liveness. It does not prove that Chromium can start.
Use the [integration guide](../integrations/codex.md#1-create-or-reuse-a-sandbox) to check sandbox `RUNNING` status, CDP access, and the visual session.

## Access from Your Computer

Replace `user@server` with your SSH destination. Run this command on your computer and leave the tunnel running:

```bash
ssh -N -L 127.0.0.1:8000:127.0.0.1:8000 user@server
```

Open [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin) on your computer.
Sign in with the server's admin token. Configure the CLI on the same computer:

```bash
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
read -r -s -p "Verge admin token: " VERGE_BROWSER_TOKEN; echo
export VERGE_BROWSER_TOKEN
```

Request CDP and session URLs through this client URL. The returned addresses must be reachable from your computer.
If local port 8000 is occupied, change the first SSH forwarding port and the client URL port.
Do not expose runtime ports publicly to make the client connect.

The SSH recipe does not require a public API.
For direct access through a domain, configure:

- HTTPS.
- WebSocket forwarding.
- Trusted proxy headers.
- Strong secrets.
- Network access restrictions.

## Keep Data and Inspect Failures

Compose mounts the checkout at the same absolute path on the Docker host and inside the API container.
Runtime workspaces use bind mounts under `.local/sandboxes`.
Keep that directory and mount mapping when recreating the API.

Include metadata and profile files in a migration or backup. The container image alone does not contain sandbox data.

```bash
docker logs --tail 100 verge-api-private
docker ps --filter label=verge.managed=true
```

Inspect logs locally. Do not publish browser content, tokens, or ticketed URLs from logs.

After a host reboot:

1. Start the API with `docker start verge-api-private`.
2. Inspect sandbox state.
3. Resume stopped sandboxes explicitly.

This recipe does not configure automatic startup or full session restoration.

For the exact persistence behavior, see [Persistent Browser Profiles](persistent-profiles.md). For server settings, see [Environment Variables](../env.md).

Static checks cover the Compose model and command options.
A live Linux/Docker smoke test of this complete recipe has not been run. Do not treat it as a runtime-verified walkthrough.
