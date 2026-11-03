# Playwright and Playwright MCP over CDP

Verge Browser exposes the existing Chromium browser through a ticketed Chrome DevTools Protocol (CDP) WebSocket.
It does not serve the Playwright wire protocol or an MCP endpoint.

For deployment, sandbox creation, and ticket setup, follow [Codex with a Self-Hosted Browser](codex.md#1-create-or-reuse-a-sandbox). The CDP connection works independently of Codex.

## Direct Playwright Connection

In a Node.js project with `playwright` installed, obtain a fresh ticket using the Verge CLI:

```bash
set -euo pipefail
VERGE_CDP_URL="$(verge-browser sandbox cdp codex-demo --mode reusable --ttl-sec 3600 --json | jq -er '.cdp_url')"
export VERGE_CDP_URL
```

Use a disposable sandbox. This example navigates an existing tab.

1. Save the example as an `.mjs` file in your Node.js project.
2. Run the file with `node`.

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

Use the existing default context to share the runtime's profile and tabs.
A new incognito context does not share that persisted login state.
For real tasks, select the intended tab by URL. Do not navigate an arbitrary tab as this disposable example does.

`chromium.connectOverCDP()` is not `browserType.connect()`.
Playwright documents CDP as a [lower-fidelity connection](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp) than its native protocol.
Do not assume that every Playwright feature works identically.

## Playwright MCP

An MCP client can launch this command as a local stdio server:

```bash
npx -y @playwright/mcp@0.0.83 --cdp-endpoint "${VERGE_CDP_URL:?Set VERGE_CDP_URL first}"
```

The command attaches to the Verge browser instead of launching local Chromium.
It starts a stdio server. Running it alone in a terminal does not issue browser actions.
Let your MCP client launch it. The [Codex guide](codex.md#3-configure-codexs-mcp-server) provides a configuration.

Pass the full ticketed WebSocket URL. Do not substitute a session URL, API base URL, or private runtime address on `9222`/`9223`.
Verge's signed-ticket connection does not require `--cdp-header`.

`--shared-browser-context` controls sharing between MCP HTTP clients.
A person does not need this flag to view the same Chromium through noVNC or Xpra.

The MCP process and browser can run on different hosts.
MCP tool paths do not automatically refer to Verge `/workspace` paths.
Use the [Verge file APIs or CLI](../cli-sdk.md) to transfer sandbox files.

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

Recorded checks cover the documented flags, MCP stdio initialization, tool listing, and repository contracts.
Remote Playwright and MCP browser actions still require a runtime-backed smoke test for this guide.
See the [upstream MCP documentation](https://github.com/microsoft/playwright-mcp) for supported options.
