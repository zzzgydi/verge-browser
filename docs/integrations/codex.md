# Use Codex with a Self-Hosted Browser

Connect Codex CLI to a Verge Browser sandbox through Microsoft's Playwright MCP server. Chromium runs on the Verge host; Codex and the MCP process can run on your own computer. A person can open the same browser through noVNC or Xpra.

This is an external-tool integration, not a built-in Codex connector or task orchestrator. The repository also provides [CLI-based Agent Skills](../../skills/verge-browser-usage/SKILL.md); MCP is optional.

## Prerequisites

- A running Verge Browser deployment. For a VPS, first follow [Headless Linux Deployment](../guides/headless-linux.md), including its SSH tunnel.
- Codex CLI, Bash, Node.js 22+, npm, and `jq` on the machine running Codex.
- The Verge CLI: `npm install -g verge-browser`.
- The deployment's admin token. Do not put it into a prompt or tracked config file.

## 1. Create or Reuse a Sandbox

Run in Bash on the Codex machine. The URL must be reachable from that machine, not just from the Verge server:

```bash
set -euo pipefail
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
read -r -s -p "Verge admin token: " VERGE_BROWSER_TOKEN; echo
export VERGE_BROWSER_TOKEN

verge-browser sandbox create --alias codex-demo --kind xvfb_vnc --json
verge-browser sandbox get codex-demo --json
```

Create once; for an existing sandbox, run only `sandbox get`. Wait until `status` is `RUNNING` before connecting. If it remains `STARTING`, check again; if it reports `FAILED` or `DEGRADED`, inspect `metadata` and the runtime logs rather than treating creation as success. A `STOPPED` sandbox needs `verge-browser sandbox resume codex-demo --json` first.

Use `--kind xpra` at creation for Xpra instead of noVNC; the remaining steps are the same.

## 2. Get a Scoped CDP URL

```bash
set -euo pipefail
VERGE_CDP_URL="$(verge-browser sandbox cdp codex-demo --mode reusable --ttl-sec 3600 --json | jq -er '.cdp_url')"
export VERGE_CDP_URL
```

The CLI unwraps the API envelope, so the field is `.cdp_url`, not `.data.cdp_url`. The returned `ws://` or `wss://` URL contains a sandbox-scoped bearer ticket. Keep the full URL, including its query string, private. It is not an HTTP MCP endpoint, and the admin bearer token is not a substitute for its ticket.

The explicit one-hour TTL avoids the server's default 60-second ticket expiring during setup. It permits new connections until expiry; it does not refresh itself or impose a one-hour cutoff on a WebSocket that is already connected. Do not use a permanent ticket just to avoid renewal.

## 3. Configure Codex's MCP Server

Add this table to your user `~/.codex/config.toml` without replacing your other settings. If the table already exists, update it instead of adding a duplicate:

```toml
[mcp_servers.verge_playwright]
command = "bash"
args = ["-c", "exec npx -y @playwright/mcp@0.0.83 --cdp-endpoint \"${VERGE_CDP_URL:?Set VERGE_CDP_URL before starting Codex}\""]
env_vars = ["VERGE_CDP_URL"]
startup_timeout_sec = 60
```

The ticket stays in the launching shell's environment instead of being saved in the config. The Bash check fails explicitly if it is missing, rather than letting MCP launch an unrelated local browser. Only the scoped CDP URL needs to be forwarded to MCP, not the Verge admin token.

This example pins the MCP version whose CLI options were checked. Before upgrading, verify the [upstream options](https://github.com/microsoft/playwright-mcp#configuration). Codex's current config format is documented in the [official MCP guide](https://developers.openai.com/codex/mcp).

Start a new Codex CLI session from the **same shell**, but remove management credentials from the child process:

```bash
env -u VERGE_BROWSER_TOKEN -u VERGE_ADMIN_AUTH_TOKEN -u VERGE_TICKET_SECRET codex
```

This keeps `VERGE_CDP_URL` available while leaving the admin token in your management shell, not in Codex or its shell tools. The MCP `env_vars` setting does not control Codex's own environment. Use this launch command each time, including after ticket renewal. Do not reload these secrets from shell startup files; removing environment variables does not isolate Codex from credential files it can read.

Inspect `/mcp` to confirm `verge_playwright` is available. A desktop app opened separately may not inherit this shell's variables; this recipe targets Codex CLI and does not configure a hosted Codex cloud task.

## 4. Automate and Hand Off

Try a low-risk prompt first:

> Use verge_playwright to open https://example.com and read its title. Use the existing browser. Before any login, MFA, purchase, or other confirmation step, stop browser actions and ask me to take over. Continue only after I say I am done, then take a fresh page snapshot.

To view or control that sandbox while Codex is running, run this yourself in a separate management terminal with the Verge client variables set as in step 1 (without creating another sandbox). Do not give Codex the admin token or ask it to issue the ticket:

```bash
verge-browser sandbox session codex-demo --mode one_time --ttl-sec 900 --json
```

Open the returned `url` privately. Select the tab used by MCP and verify it shows the same page. After the agent has stopped acting, complete the manual step yourself. Tell Codex to take a fresh snapshot before it continues; old element references may no longer match.

Opening the session URL **does not pause the agent**. Do not use `sandbox pause` for handoff: it removes the runtime container and disconnects both clients. See [Human Handoff](../guides/human-handoff.md).

## Reconnect and Finish

- If a new connection fails after ticket expiry, request a fresh `VERGE_CDP_URL` as in step 2 and start a new Codex session from that shell using the credential-stripping launch command in step 3. Existing processes do not receive subsequent shell environment changes.
- After a sandbox pause/resume or browser restart, reconnect and inspect the current tabs. Do not assume the old page or WebSocket survived.
- When finished, stop the automation client. To release the runtime while keeping on-disk data, run `verge-browser sandbox pause codex-demo --json`.
- `sandbox rm` deletes the sandbox, including its profile and files. It is not a logout or temporary stop.

## Validation Status

The MCP `0.0.83` command-line options and stdio initialization/tool listing were checked. The installed Codex CLI parsed the config, and the missing-URL guard failed explicitly as intended. Verge ticket/CLI contracts were also checked. A complete Codex -> MCP -> Docker Chromium -> human handoff run has **not** been verified for this guide. Before relying on it, confirm navigation, the same visible tab, handoff, and reconnection in your deployment. For connection failures, see the [CDP troubleshooting guide](playwright-mcp.md#troubleshooting).
