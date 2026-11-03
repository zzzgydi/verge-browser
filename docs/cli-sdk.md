# SDK & CLI Quick Start

## Client versions

The Node package prepares 0.4.0 for engine selection and managed Camoufox commands.
The npm 0.3.0 package does not include those features.
Check `npm view verge-browser version` before installing; a source version is not proof of publication.
Until 0.4.0 is published, use the [Node source build](../packages/node/README.md#version-compatibility) and a matching API.
The npm package does not install the server or browser runtime.

## Environment Variables

Use `dev-admin-token` only for local development. For other deployments, use the server's configured admin token.
Keep the token and returned ticketed URLs private.

```bash
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=dev-admin-token
```

## CLI

Run these as independent examples, not as one script. Each command requires the named sandbox and input files to exist.

**Data loss:** back up required files before `sandbox rm` or `files rm`.
`sandbox rm` deletes the profile and shared files. `files rm` deletes the selected file.
The `--overwrite` example replaces existing file content.

Use time-limited tickets for routine access. A `permanent` ticket has no expiry.

```bash
verge-browser sandbox list --json
verge-browser sandbox create --alias shopping --width 1440 --height 900
verge-browser sandbox create --alias proxied --http-proxy http://proxy.example.com:8080 --no-proxy localhost,127.0.0.1
verge-browser sandbox create --alias human-loop --kind xpra --json
verge-browser sandbox get shopping --json
verge-browser sandbox cdp shopping --json
verge-browser sandbox cdp shopping --mode reusable --ttl-sec 300 --json
verge-browser sandbox cdp shopping --mode permanent --json
verge-browser sandbox session shopping --json
verge-browser sandbox session shopping --mode reusable --ttl-sec 120 --json
verge-browser sandbox restart shopping --json
verge-browser sandbox pause shopping --json
verge-browser sandbox resume shopping --json
verge-browser sandbox rm shopping --json
verge-browser browser screenshot shopping --output ./shot.png --json
verge-browser browser actions shopping --input ./actions.json --json
verge-browser files list shopping /workspace --json
verge-browser files read shopping /workspace/notes.txt
verge-browser files write shopping /workspace/notes.txt --content "hello verge" --overwrite --json
verge-browser files upload shopping ./local-file.txt --json
verge-browser files download shopping /workspace/notes.txt --output ./notes.txt --json
verge-browser files rm shopping /workspace/notes.txt --json
```

Notes:

- The SDK and CLI send requests to `/sandbox/...` by default.
- JSON responses are automatically unwrapped from `{ code, message, data }`.
- `sandbox cdp` calls `POST /sandbox/{id}/cdp/apply` with default mode `reusable`.
- `sandbox session` calls `POST /sandbox/{id}/session/apply` with default mode `one_time`.
- Use `--mode` to specify the ticket mode (`one_time` / `reusable` / `permanent`) and `--ttl-sec` to set the expiry in seconds.
- `sandbox create` defaults to the `xvfb_vnc` sandbox type; use `--kind xpra` to select Xpra instead.

## Python SDK

Run this example separately from the CLI and Node examples. Reusing an existing alias during creation causes a conflict.

```python
from verge_browser import VergeClient

client = VergeClient()
sandbox = client.create_sandbox(alias="shopping", width=1440, height=900)
proxied = client.create_sandbox(
    alias="proxied",
    http_proxy="http://proxy.example.com:8080",
    https_proxy="http://proxy.example.com:8080",
    no_proxy="localhost,127.0.0.1",
)
xpra_sandbox = client.create_sandbox(alias="manual-step", kind="xpra")
detail = client.get_sandbox("shopping")
cdp = client.get_cdp_info("shopping", mode="reusable", ttl_sec=300)
session = client.get_session_url("shopping")
```

`cdp["cdp_url"]` is a signed-ticket WebSocket URL ready for direct use.

## Node SDK

```ts
import { VergeClient } from "verge-browser";

const client = new VergeClient({
  baseUrl: "http://127.0.0.1:8000",
  token: process.env.VERGE_BROWSER_TOKEN,
});

const sandbox = await client.createSandbox({ alias: "shopping" });
const proxied = await client.createSandbox({
  alias: "proxied",
  http_proxy: "http://proxy.example.com:8080",
  https_proxy: "http://proxy.example.com:8080",
  no_proxy: "localhost,127.0.0.1",
});
const xpraSandbox = await client.createSandbox({
  alias: "manual-step",
  kind: "xpra",
});
const detail = await client.getSandbox("shopping");
const cdp = await client.getCdpInfo("shopping", {
  mode: "reusable",
  ttl_sec: 300,
});
const session = await client.getSessionUrl("shopping");
```

## Human-in-the-Loop Workflow

1. Create a sandbox for the automation task.
2. Before manual control, stop all automation clients.
3. Confirm that no browser action is still running.
4. Request a session URL with `get_session_url()` or `verge-browser sandbox session <id-or-alias>`.
5. Complete the manual action in that session.
6. Tell the agent that manual control is complete.
7. If CDP disconnected, obtain a fresh URL with `get_cdp_info()` or `verge-browser sandbox cdp <id-or-alias>`.
8. Take a fresh snapshot before resuming automation.

Notes:

- Both `xvfb_vnc` and `xpra` sandbox types expose a unified `session_url`.
- Whether noVNC or the Xpra page is served depends on the sandbox `kind`.
- Opening a session URL does not stop automation.
- Do not use `sandbox pause` for live handoff. It removes the runtime container.

See [Human Handoff](guides/human-handoff.md), [Persistent Browser Profiles](guides/persistent-profiles.md), and [Codex with Playwright MCP](integrations/codex.md) for the complete workflows and their limits.

## Camoufox engine routing

A matching source build supports `sandbox create --browser-engine camoufox`.
Read `sandbox get ID --json` before selecting an automation command.

| Engine | Automation |
| --- | --- |
| `chromium`, `cloakbrowser` | Use `agent-browser --cdp` with a ticketed CDP URL. |
| `camoufox` | Use the [managed commands](../skills/verge-browser-usage/references/camoufox.md), such as `verge-browser browser snapshot ID -i`. |

Both Node and Python CLIs use the same syntax. Managed commands call the remote sandbox. They never start a local browser.

Python: `client.browser_command("fox", {"action": "snapshot", "interactive": True})`.
Node: `await client.browserCommand("fox", {action: "snapshot", interactive: true})`.

Install matching client and server versions. A published package does not necessarily contain unreleased source changes.
See [setup, limitations and licenses](guides/camoufox.md).

Maintainers: see the [Node package release checklist](guides/node-release.md).
