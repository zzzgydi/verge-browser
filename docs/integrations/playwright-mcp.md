# Playwright and Playwright MCP over CDP

Verge Browser exposes the existing Chromium browser through a ticketed Chrome DevTools Protocol WebSocket. It does not serve the Playwright wire protocol or an MCP endpoint itself.

For deployment, sandbox creation, and ticket setup, follow [Codex with a Self-Hosted Browser](codex.md#1-create-or-reuse-a-sandbox). The CDP connection works independently of Codex.

## Direct Playwright Connection

In a Node.js project with `playwright` installed, obtain a fresh ticket using the Verge CLI:

```bash
set -euo pipefail
VERGE_CDP_URL="$(verge-browser sandbox cdp codex-demo --mode reusable --ttl-sec 3600 --json | jq -er '.cdp_url')"
export VERGE_CDP_URL
```

Save the following as an `.mjs` file in that Node.js project, then run it with `node`:

```javascript
import { chromium } from "playwright";

const endpoint = process.env.VERGE_CDP_URL;
if (!endpoint) throw new Error("Set VERGE_CDP_URL first");

const browser = await chromium.connectOverCDP(endpoint);
try {
  const context = browser.contexts()[0];
  if (!context) throw new Error("No default Chromium context found");
  const page = context.pages()[0] ?? await context.newPage();
  await page.goto("https://example.com");
  console.log(await page.title());
} finally {
  // Disconnect this Playwright client from the existing browser.
  await browser.close();
}
```

Use the existing default context to share the runtime's browser profile and tabs. A new incognito context does not provide the same persisted login state. For a real task, select the intended tab by URL rather than navigating an arbitrary existing tab as this disposable demo does.

`chromium.connectOverCDP()` is not `browserType.connect()`. Playwright documents CDP as a [lower-fidelity connection](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp) than its native protocol, so do not assume every Playwright feature works identically.

## Playwright MCP

An MCP client can launch this command as a local stdio server:

```bash
npx -y @playwright/mcp@0.0.83 --cdp-endpoint "${VERGE_CDP_URL:?Set VERGE_CDP_URL first}"
```

This attaches to the Verge browser instead of launching local Chromium. It is a stdio server, so running it in an ordinary terminal alone does not issue browser actions. Let your MCP client launch it; [the Codex guide](codex.md#3-configure-codexs-mcp-server) supplies one configuration.

Pass the full ticketed WebSocket URL. Do not substitute a session URL, the API base URL, or the runtime's private `9222`/`9223` address. `--cdp-header` is available upstream but is not needed for Verge's signed-ticket connection. `--shared-browser-context` controls sharing between MCP HTTP clients; it is not required for a person to view the same Chromium through noVNC or Xpra.

The MCP process and browser may be on different hosts. File paths in MCP tools are not automatically Verge `/workspace` paths; use the [Verge file APIs or CLI](../cli-sdk.md) when transferring files to or from the sandbox.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| REST requests return 401 | `VERGE_BROWSER_TOKEN` must match the server's admin token |
| CDP connection rejected / invalid ticket | Obtain a new ticket; preserve the complete query string and use `reusable` if the client reconnects |
| Browser unavailable / connection closes | Confirm the sandbox is `RUNNING` and inspect `metadata.runtime_error`; ticket issuance alone is not a readiness check |
| Connection refused or wrong host | The endpoint must be reachable from the MCP process; keep the SSH tunnel open if using one |
| Wrong `ws://` scheme behind HTTPS | Configure the reverse proxy and trusted forwarded headers correctly, including WebSocket upgrades; do not publish runtime ports as a workaround |
| Wrong tab or unexpected login state | Check the sandbox ID and selected tab; avoid creating a separate incognito context |
| App on your laptop is unreachable | `localhost` in the browser means the runtime container, not the laptop running Codex; provide a reachable app URL or a separately configured tunnel |

Tickets authorize new connections and expire without automatic renewal. Browser restarts and pause/resume also break live connections. See [Persistent Browser Profiles](../guides/persistent-profiles.md) for the lifecycle contract.

Validation covers the documented flags, MCP stdio initialization/tool listing, and repository contracts; remote Playwright and MCP browser actions still require a runtime-backed smoke test. See the [upstream MCP documentation](https://github.com/microsoft/playwright-mcp) for supported options.
