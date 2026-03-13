---
name: verge-browser-usage
description: Operate an already deployed Verge Browser service through its CLI, SDK, and API, including sandbox lifecycle, screenshots, files, human handoff, and CDP access. Use when the user already has Verge Browser running and wants practical automation workflows, especially with agent-browser.
---

# Purpose

Use this skill when Verge Browser is already deployed and the user wants to create sandboxes, manage them, fetch session or CDP URLs, or combine the service with `agent-browser` for browser automation.

This skill assumes deployment is done. If the user instead needs help installing or starting the service itself, use `verge-browser-deploy`.

## Workflow

1. Confirm the user already has a reachable Verge Browser deployment. If not, switch to `verge-browser-deploy`.
2. Install the latest CLI tools if they are not already present.
3. Set `VERGE_BROWSER_URL` to the actual service URL and `VERGE_BROWSER_TOKEN` to the admin token.
4. Create or reuse a sandbox.
5. Decide whether the task needs CLI, SDK, session handoff, or CDP access.
6. For `agent-browser`, get a fresh ticketed `cdp_url` and pass it to `agent-browser --cdp`.
7. Use `/workspace` for file exchange.

## Before You Start

This skill does not require a local checkout of the Verge Browser repository.

You only need:

- a deployed Verge Browser service
- the service URL
- the admin token used by that service

If the CLI tools are missing, install the latest versions:

```bash
npm install -g verge-browser@latest
npm install -g agent-browser@latest
agent-browser install
```

`VERGE_ADMIN_AUTH_TOKEN` matters here because it is also the value you should place into `VERGE_BROWSER_TOKEN` for CLI / SDK access.

## Quick Start

Set client variables first:

```bash
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
export VERGE_BROWSER_TOKEN="replace-with-your-admin-token"
```

If the service is exposed behind a public domain, set that domain here instead, for example:

```bash
export VERGE_BROWSER_URL="https://verge.example.com"
export VERGE_BROWSER_TOKEN="replace-with-your-admin-token"
```

Then the shortest lifecycle flow is:

```bash
verge-browser sandbox create --alias demo --default-url https://example.com --json
verge-browser sandbox get demo --json
verge-browser sandbox cdp demo --json
verge-browser sandbox session demo --json
verge-browser sandbox rm demo --json
```

## Core Commands

- List sandboxes:
  `verge-browser sandbox list --json`
- Create a default sandbox:
  `verge-browser sandbox create --alias demo --width 1440 --height 900 --json`
- Create an Xpra sandbox:
  `verge-browser sandbox create --alias demo-xpra --kind xpra --json`
- Restart browser:
  `verge-browser sandbox restart demo --json`
- Pause or resume:
  `verge-browser sandbox pause demo --json`
  `verge-browser sandbox resume demo --json`
- Delete:
  `verge-browser sandbox rm demo --json`

## Browser And Files

- Window screenshot:
  `verge-browser browser screenshot demo --type window --format png --output ./window.png --json`
- Page screenshot:
  `verge-browser browser screenshot demo --type page --format png --output ./page.png --json`
- Execute GUI actions:
  `verge-browser browser actions demo --input ./actions.json --json`
- List files:
  `verge-browser files list demo /workspace --json`
- Upload:
  `verge-browser files upload demo ./local-file.txt --json`
- Download:
  `verge-browser files download demo /workspace/notes.txt --output ./notes.txt --json`

Use `/workspace/uploads` for inbound files and `/workspace/downloads` for browser-generated artifacts when possible.

## Human Handoff

To let a person take over the live browser, request a session URL:

```bash
verge-browser sandbox session demo --json
```

The same command works for both `xvfb_vnc` and `xpra`. The server decides which front end to return based on sandbox `kind`.

## agent-browser Integration

For `agent-browser`, always prefer the ticketed CDP URL returned by Verge Browser.

Example:

```bash
CDP_URL="$(verge-browser sandbox cdp demo --json | jq -r '.cdp_url')"

agent-browser --cdp "$CDP_URL" snapshot -i
agent-browser --cdp "$CDP_URL" click @e1
agent-browser --cdp "$CDP_URL" fill @e2 "hello@example.com"
agent-browser --cdp "$CDP_URL" press Enter
```

Rules:

- request a fresh `cdp_url` if the previous ticket may have expired
- re-run `snapshot -i` after navigation or significant DOM changes
- if automation blocks on MFA or CAPTCHA, switch to `sandbox session`, let the human finish, then request a new CDP URL and continue
- if `agent-browser` is not installed yet, install it with `npm install -g agent-browser@latest` and then run `agent-browser install`

## References

- Read `references/commands.md` for command patterns and SDK examples.
- Read `references/agent-browser-examples.md` for end-to-end CDP workflows.
