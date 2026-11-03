# Use Codex with a Self-Hosted Browser

Connect Codex CLI to a Verge Browser sandbox through Microsoft's Playwright MCP server.
Chromium runs on the Verge host. Codex and the MCP process can run on your computer.
A person can open the same browser through noVNC or Xpra.

This is an external-tool integration. It is not a built-in Codex connector or task orchestrator.
As an alternative, use the [CLI-based Agent Skills](../../skills/verge-browser-usage/SKILL.md).

## Prerequisites

- A running Verge Browser deployment. For a VPS, first follow [Headless Linux Deployment](../guides/headless-linux.md), including its SSH tunnel.
- Codex CLI, Bash, Node.js 22+, npm, and `jq` on the machine running Codex.
- The Verge CLI: `npm install -g verge-browser`.
- The deployment's admin token. Do not put it into a prompt or tracked config file.

## 1. Create or Reuse a Sandbox

Run these commands in Bash on the Codex machine. That machine must be able to reach the API URL:

```bash
set -euo pipefail
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
read -r -s -p "Verge admin token: " VERGE_BROWSER_TOKEN; echo
export VERGE_BROWSER_TOKEN

verge-browser sandbox create --alias codex-demo --kind xvfb_vnc --json
verge-browser sandbox get codex-demo --json
```

Create the sandbox once. For an existing sandbox, run only `sandbox get`.

| Status | Action |
| --- | --- |
| `RUNNING` | Continue to the connection step. |
| `STARTING` | Check the status again before connecting. |
| `FAILED`, `DEGRADED` | Inspect `metadata` and runtime logs. Do not treat creation as success. |
| `STOPPED` | Run `verge-browser sandbox resume codex-demo --json`. Wait for `RUNNING`. |

Use `--kind xpra` at creation for Xpra instead of noVNC; the remaining steps are the same.

## 2. Get a Scoped CDP URL

```bash
set -euo pipefail
VERGE_CDP_URL="$(verge-browser sandbox cdp codex-demo --mode reusable --ttl-sec 3600 --json | jq -er '.cdp_url')"
export VERGE_CDP_URL
```

The CLI unwraps the API envelope. Use `.cdp_url`, not `.data.cdp_url`.
The returned `ws://` or `wss://` URL contains a sandbox-scoped bearer ticket.
Keep the full URL private, including its query string.

This URL is a CDP WebSocket endpoint, not an HTTP MCP endpoint.
The admin bearer token cannot replace the ticket.

The example sets a one-hour ticket lifetime instead of the default 60 seconds.
The ticket permits new connections until expiry. It does not renew itself or terminate an existing WebSocket at expiry.
Do not use a permanent ticket just to avoid renewal.

## 3. Configure Codex's MCP Server

Add this table to `~/.codex/config.toml`. Keep your other settings.
If the table exists, update it instead of adding a duplicate:

```toml
[mcp_servers.verge_playwright]
command = "bash"
args = ["-c", "exec npx -y @playwright/mcp@0.0.83 --cdp-endpoint \"${VERGE_CDP_URL:?Set VERGE_CDP_URL before starting Codex}\""]
env_vars = ["VERGE_CDP_URL"]
startup_timeout_sec = 60
```

The ticket stays in the launching shell's environment, not in the config file.
If the URL is missing, the Bash check fails. This prevents MCP from launching an unrelated local browser.
Forward only the scoped CDP URL to MCP. Do not forward the Verge admin token.

This example pins the MCP version whose CLI options were checked. Before upgrading, verify the [upstream options](https://github.com/microsoft/playwright-mcp#configuration). Codex's current config format is documented in the [official MCP guide](https://developers.openai.com/codex/mcp).

Start Codex CLI from the **same shell** with this command. It removes management credentials from the child process:

```bash
env -u VERGE_BROWSER_TOKEN -u VERGE_ADMIN_AUTH_TOKEN -u VERGE_TICKET_SECRET codex
```

The command keeps `VERGE_CDP_URL` available. The admin token stays in your management shell, not in Codex or its shell tools.
MCP's `env_vars` setting does not control Codex's own environment.

Use this launch command each time, including after ticket renewal. Do not reload secrets from shell startup files.
Removing environment variables does not block access to readable credential files.

Inspect `/mcp` to confirm that `verge_playwright` is available.
This recipe targets Codex CLI, not a hosted Codex cloud task.
A separately opened desktop app does not necessarily inherit this shell's variables.

## 4. Automate and Hand Off

Try a low-risk prompt first:

> Use verge_playwright to open https://example.com and read its title. Use the existing browser. Before any login, MFA, purchase, or other confirmation step, stop browser actions and ask me to take over. Continue only after I say I am done, then take a fresh page snapshot.

Do not give Codex the admin token or ask it to issue the session ticket.
In a separate management terminal, set the client variables from step 1. Do not create another sandbox.
Request a visual session for the existing sandbox:

```bash
verge-browser sandbox session codex-demo --mode one_time --ttl-sec 900 --json
```

1. Open the returned `url` privately.
2. Select the tab used by MCP.
3. Confirm that it shows the intended page.
4. Wait for the agent to stop browser actions.
5. Complete the manual step yourself.
6. Tell Codex to take a fresh snapshot before continuing.

Old element references can become invalid after manual actions.

Opening the session URL **does not stop the agent**.
Do not use `sandbox pause` for handoff. It removes the runtime container and disconnects both clients.
See [Human Handoff](../guides/human-handoff.md).

## Reconnect and Finish

- If a new connection fails after ticket expiry, request a fresh `VERGE_CDP_URL` as in step 2. Start a new Codex session with the credential-stripping command from step 3. Existing processes do not receive later shell environment changes.
- After a sandbox pause/resume or browser restart, reconnect and inspect the current tabs. Do not assume the old page or WebSocket survived.
- When finished, stop the automation client. To release the runtime and keep on-disk data, run `verge-browser sandbox pause codex-demo --json`.
- `sandbox rm` deletes the sandbox, including its profile and files. It is not a logout or temporary stop.

## Validation Status

Recorded checks cover:

- MCP `0.0.83` command-line options, stdio initialization, and tool listing.
- Config parsing by the installed Codex CLI.
- Explicit failure when `VERGE_CDP_URL` is missing.
- Verge ticket and CLI contracts.

A complete Codex -> MCP -> Docker Chromium -> human handoff run has **not** been verified for this guide.
Before relying on it, test navigation, the same visible tab, handoff, and reconnection in your deployment.
For connection failures, see [CDP troubleshooting](playwright-mcp.md#troubleshooting).
