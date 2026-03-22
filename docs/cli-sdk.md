# SDK & CLI Quick Start

## Environment Variables

```bash
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=dev-admin-token
```

## CLI

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

1. The agent creates a sandbox and runs initial automation.
2. When human takeover is needed, call `get_session_url()` or `verge-browser sandbox session <id-or-alias>`.
3. After the human completes their actions, the agent resumes automation via `get_cdp_info()` or `verge-browser sandbox cdp <id-or-alias>`.

Notes:

- Both `xvfb_vnc` and `xpra` sandbox types expose a unified `session_url`.
- Whether noVNC or the Xpra page is served depends on the sandbox `kind`.
