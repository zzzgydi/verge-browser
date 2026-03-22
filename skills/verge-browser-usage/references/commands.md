# Commands And SDK Examples

## Install The Latest CLIs

```bash
npm install -g verge-browser@latest
npm install -g agent-browser@latest
agent-browser install
```

If you do not want a global install for Verge Browser, you can also run:

```bash
npx verge-browser@latest --help
```

## Environment

```bash
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
export VERGE_BROWSER_TOKEN="replace-with-your-admin-token"
```

If the service is published behind a public hostname, use that hostname instead of `127.0.0.1`.

`VERGE_BROWSER_TOKEN` should be the same admin token configured on the Verge Browser server.

## CLI

```bash
verge-browser sandbox list --json
verge-browser sandbox create --alias shopping --width 1440 --height 900 --json
verge-browser sandbox get shopping --json
verge-browser sandbox cdp shopping --json
verge-browser sandbox cdp shopping --mode reusable --ttl-sec 300 --json
verge-browser sandbox cdp shopping --mode permanent --json
verge-browser sandbox session shopping --json
verge-browser sandbox session shopping --mode reusable --ttl-sec 120 --json
verge-browser browser screenshot shopping --type window --format png --output ./window.png --json
verge-browser files list shopping /workspace --json
verge-browser files upload shopping ./local-file.txt --json
verge-browser files download shopping /workspace/notes.txt --output ./notes.txt --json
```

## Python SDK

```python
from verge_browser import VergeClient

client = VergeClient()
sandbox = client.create_sandbox(alias="shopping", width=1440, height=900)
cdp = client.get_cdp_info("shopping", mode="reusable", ttl_sec=300)
session = client.get_session_url("shopping")
```

## Node SDK

```ts
import { VergeClient } from "verge-browser";

const client = new VergeClient({
  baseUrl: process.env.VERGE_BROWSER_URL,
  token: process.env.VERGE_BROWSER_TOKEN,
});

const sandbox = await client.createSandbox({ alias: "shopping" });
const cdp = await client.getCdpInfo("shopping", {
  mode: "reusable",
  ttl_sec: 300,
});
```

## Ticket Modes

CDP and session endpoints both support ticket modes. The defaults differ:

| Endpoint | Default mode | Behavior |
| -------- | ------------ | -------- |
| `/cdp/apply` | `reusable` | URL can be used repeatedly until TTL expires |
| `/session/apply` | `one_time` | URL is consumed on first use |

Available modes:

| Mode | Description |
| ---- | ----------- |
| `one_time` | Consumed on first use. Cannot be reused. |
| `reusable` | Can be used repeatedly until TTL expires. |
| `permanent` | Never expires. No TTL. |

When `ttl_sec` is omitted, it defaults to `VERGE_TICKET_TTL_SEC` (server config, default `60` seconds).
