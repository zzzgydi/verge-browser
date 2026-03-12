# SDK 与 CLI 快速上手

## 环境变量

```bash
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=dev-admin-token
```

## CLI

```bash
verge-browser sandbox list --json
verge-browser sandbox create --alias shopping --width 1440 --height 900
verge-browser sandbox create --alias human-loop --kind xpra --json
verge-browser sandbox get shopping --json
verge-browser sandbox cdp shopping --json
verge-browser sandbox session shopping --json
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

说明：

- SDK 与 CLI 默认请求 `/sandbox/...`
- JSON 业务响应会自动解包 `{ code, message, data }`
- `sandbox cdp` 会调用 `POST /sandbox/{id}/cdp/apply`
- `sandbox session` 会调用 `POST /sandbox/{id}/session/apply`
- `sandbox create` 默认创建 `xvfb_vnc` 沙盒，也可通过 `--kind xpra` 选择 Xpra

## Python SDK

```python
from verge_browser import VergeClient

client = VergeClient()
sandbox = client.create_sandbox(alias="shopping", width=1440, height=900)
xpra_sandbox = client.create_sandbox(alias="manual-step", kind="xpra")
detail = client.get_sandbox("shopping")
cdp = client.get_cdp_info("shopping", mode="reusable", ttl_sec=300)
session = client.get_session_url("shopping")
```

`cdp["cdp_url"]` 是可直接使用的带签名 ticket 的 WebSocket 地址。

## Node SDK

```ts
import { VergeClient } from "verge-browser";

const client = new VergeClient({
  baseUrl: "http://127.0.0.1:8000",
  token: process.env.VERGE_BROWSER_TOKEN,
});

const sandbox = await client.createSandbox({ alias: "shopping" });
const xpraSandbox = await client.createSandbox({ alias: "manual-step", kind: "xpra" });
const detail = await client.getSandbox("shopping");
const cdp = await client.getCdpInfo("shopping", { mode: "reusable", ttl_sec: 300 });
const session = await client.getSessionUrl("shopping");
```

## 人机协同工作流

1. Agent 创建 sandbox 并执行初始自动化。
2. 需要人工接管时，调用 `get_session_url()` 或 `verge-browser sandbox session <id-or-alias>`。
3. 人类完成操作后，Agent 通过 `get_cdp_info()` 或 `verge-browser sandbox cdp <id-or-alias>` 继续自动化。

补充：

- `xvfb_vnc` 和 `xpra` 都使用统一的 `session_url`
- 具体下发的是 noVNC 还是 Xpra 页面，由沙盒 `kind` 决定
