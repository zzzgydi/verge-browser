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
verge-browser sandbox session shopping --json
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
