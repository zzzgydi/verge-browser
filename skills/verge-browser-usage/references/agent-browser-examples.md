# agent-browser Examples

Install first if needed:

```bash
npm install -g agent-browser@latest
agent-browser install
```

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
