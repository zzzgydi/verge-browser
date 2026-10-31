# agent-browser Examples

For `chromium` or `cloakbrowser` only. Read `sandbox get ID --json` first; Camoufox uses the managed commands in `camoufox.md`, never CDP.

Install first if needed:

```bash
npm install -g agent-browser@latest
export AGENT_BROWSER_SESSION="verge-ab-demo"
```

Remote CDP does not require downloading a local browser. Never drop `--cdp` to recover from connection failures.

## Minimal Flow

```bash
verge-browser sandbox create --alias ab-demo --default-url https://example.com --json
CDP_URL="$(verge-browser sandbox cdp ab-demo --json | jq -r '.cdp_url')"

agent-browser --cdp "$CDP_URL" snapshot
agent-browser --cdp "$CDP_URL" get url
agent-browser --cdp "$CDP_URL" screenshot ./ab-demo.png
```

## Ref-Based Interaction

```bash
agent-browser --cdp "$CDP_URL" snapshot -i
agent-browser --cdp "$CDP_URL" click @e1
agent-browser --cdp "$CDP_URL" fill @e2 "hello@example.com"
agent-browser --cdp "$CDP_URL" press Enter
```

## Human-In-The-Loop

```bash
verge-browser sandbox session ab-demo --json
CDP_URL="$(verge-browser sandbox cdp ab-demo --json | jq -r '.cdp_url')"
agent-browser --cdp "$CDP_URL" snapshot -i
```

Use this pattern when a human must clear MFA, CAPTCHA, or a fragile one-off GUI step.
