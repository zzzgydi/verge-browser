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
verge-browser sandbox get shopping --json
verge-browser sandbox cdp shopping --json
verge-browser sandbox vnc shopping --json
verge-browser sandbox pause shopping --json
verge-browser sandbox resume shopping --json
verge-browser sandbox rm shopping --json
```

## Python SDK

```python
from verge_browser import VergeClient

client = VergeClient()
sandbox = client.create_sandbox(alias="shopping", width=1440, height=900)
detail = client.get_sandbox("shopping")
cdp = client.get_cdp_info("shopping")
vnc = client.get_vnc_url("shopping")
```

## 人机协同工作流

1. Agent 创建 sandbox 并执行初始自动化。
2. 需要人工处理登录或验证码时，调用 `get_vnc_url()` 或 `verge-browser sandbox vnc <id-or-alias>`。
3. 人类完成接管后，Agent 再通过 `get_cdp_info()` 或 CLI 的 `sandbox cdp` 继续自动化。
