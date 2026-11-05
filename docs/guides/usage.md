# Usage Guide

English | [中文](usage.zh.md)

[Project home](../../README.md) · [Deployment](deployment.md) · [Usage](usage.md) · [Development](development.md)

This guide assumes a running service. For a first installation, start with the [deployment guide](deployment.md).

## Phone and Remote Access

Once Verge Browser is deployed on a running server, switching off your personal computer does not stop that server's browser.
Use your phone to send tasks to an agent connected to Verge Browser. A mobile agent with remote API tool support can also connect directly.
The integration depends on the agent client; Verge Browser supplies the browser service, not a mobile agent app.

To work with your laptop offline, the agent and its network route must also be independent of that laptop. Run the agent on a server, in the cloud, or on a supported phone client, with a reachable service URL and credentials. An agent or SSH tunnel running only on your laptop will stop being available when it goes offline.

See the [Linux deployment guide](headless-linux.md#access-from-your-computer) for server access, and the [SDK / CLI](../cli-sdk.md) or [API](../api.md) for tool integration.
Validate mobile agent compatibility with the client you use.

## Basic Usage

Configure `VERGE_BROWSER_URL` and `VERGE_BROWSER_TOKEN` as described in the [CLI guide](../../docs/cli-sdk.md).
The examples require a running API.

Install the CLI:

```bash
npm install -g verge-browser
```

Create a sandbox:

```bash
verge-browser sandbox create --alias test --width 1440 --height 900
```

Take a screenshot:

```bash
verge-browser browser screenshot test --output ./screenshot.png
```

Create `actions.json` with the actions you intend to send. See the [API reference](../../docs/api.md).

Execute GUI actions:

```bash
verge-browser browser actions test --input ./actions.json
```

Get a human handoff URL:

```bash
verge-browser sandbox session test
```

For more commands, see [`docs/cli-sdk.md`](../../docs/cli-sdk.md).

## Compatibility and Limits

| Capability | Support and boundary |
| --- | --- |
| Self-hosted Linux / Docker | Single-node deployment; GUI Chromium runs inside the container, even when the host has no desktop |
| Playwright / Puppeteer | Connect through the ticketed CDP WebSocket endpoint; this is not a Playwright protocol server |
| Codex / Playwright MCP | External integration via CDP; requires client configuration and ticket renewal, not built-in Codex orchestration |
| Human takeover | noVNC or Xpra controls the same browser; the caller must stop agent actions before a person takes over |
| Persistent profile and files | On-disk data survives pause/resume; deletion removes it, and website login validity is not guaranteed |
| Multiple sandboxes | Separate containers and workspaces; not a hardened, mutually untrusted multi-tenant service |
| Full GUI screenshots | Browser window capture as well as page screenshots through CDP |

Use standalone Playwright for local page automation without a remote desktop.
Use Verge Browser when automation and manual control must share one remote browser.

## Integration Guides

- [DeepSeek Harness plugin](../../packages/dsh-plugin/README.md): preview bundle for DSH `0.2.1-rc.2`, with scoped Chromium/Camoufox tools and human handoff.
- [Codex with a self-hosted browser](../../docs/integrations/codex.md): configure Playwright MCP, use scoped CDP tickets, and hand off to a person.
- [Playwright and Playwright MCP over CDP](../../docs/integrations/playwright-mcp.md): connect to the existing browser rather than launching another one.
- [Deploy on a headless Linux server](../../docs/guides/headless-linux.md): keep the API private and access it through an SSH tunnel.
- [Human handoff](../../docs/guides/human-handoff.md): stop automation, complete the manual step, and read the page again.
- [Persistent browser profiles](../../docs/guides/persistent-profiles.md): what pause, resume, restart, and deletion actually preserve.
- [Optional CloakBrowser engine](../../docs/guides/cloak.md): configure a key and install privately. Real licensed-runtime validation remains incomplete.
- [Optional Camoufox engine](../../docs/guides/camoufox.md): Firefox-based Xvfb runtime using managed Python camoufox-cli commands (not CDP); browser installed separately.

## Agent Skills

This repository provides Agent Skills under [`skills/`](../../skills):

- [`skills/verge-browser-deploy`](../../skills/verge-browser-deploy): deploy Verge Browser, configure env vars, verify health, and troubleshoot startup issues
- [`skills/verge-browser-usage`](../../skills/verge-browser-usage): operate an already deployed Verge Browser service, manage sandboxes, and combine it with `agent-browser`

## Desktop Options Comparison

| Feature | `xvfb_vnc` | `xpra` |
| --- | --- | --- |
| Desktop stack | Xvfb + Openbox + x11vnc + noVNC | Xpra Server + HTML5 client |
| Clipboard | Explicit text-transfer buttons. See [clipboard use](../../docs/vnc_clipboard.md). | Xpra client clipboard integration. Verify behavior in your target browser. |
| Creation field | `kind: "xvfb_vnc"` | `kind: "xpra"` |

Latency and network performance are not benchmarked here.

How to choose:

- Mostly automation, with occasional human inspection: use `xvfb_vnc`
- Frequent manual intervention or remote debugging: use `xpra`

## API Reference

The current API follows the `/sandbox/{sandbox_id}/...` routing model.

Detailed endpoint documentation lives in [`docs/api.md`](../../docs/api.md).

SDK and CLI usage examples live in [`docs/cli-sdk.md`](../../docs/cli-sdk.md).

### Scope

Verge Browser focuses on browser control:

- browser lifecycle: create, pause, resume, delete
- browser automation via CDP
- GUI screenshots and input actions
- session-based human takeover with `xvfb_vnc` or `xpra`
- file exchange through the sandbox workspace

The API does not provide arbitrary shell command execution.
