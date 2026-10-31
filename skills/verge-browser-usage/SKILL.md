---
name: verge-browser-usage
description: Operate a deployed Verge Browser service, selecting agent-browser over ticketed CDP for Chromium/CloakBrowser or Verge's managed camoufox-cli commands for Camoufox (Firefox/Juggler). Includes sandbox lifecycle, screenshots, files, and human handoff.
---

# Verge Browser Usage

Use this skill for an already deployed Verge Browser service. For installation or runtime setup, use `verge-browser-deploy` instead.

## Choose the correct automation path

1. Set `VERGE_BROWSER_URL` to the actual deployment URL and `VERGE_BROWSER_TOKEN` to its admin token. Do not print tokens or ticketed URLs in reports.
2. Create or reuse the intended sandbox; read `verge-browser sandbox get ID --json` before choosing an automation client.
3. Route by the returned **`browser_engine`**, not the User-Agent or sandbox `kind`:

| `browser_engine` | Automation | Do not use |
| --- | --- | --- |
| `chromium` | `agent-browser --cdp "$CDP_URL" ...` | Camoufox commands |
| `cloakbrowser` | `agent-browser --cdp "$CDP_URL" ...` | A separate local Cloak launch |
| `camoufox` | `verge-browser browser open/snapshot/click/fill/... ID ...` | CDP, `agent-browser`, local `camoufox-cli open` |
| Missing or unknown | Check server version / `GET /runtime/engines`; stop engine-specific commands until resolved | Guessing or launching a different browser |

`kind` selects the display transport (`xvfb_vnc` or `xpra`), not the browser engine. Camoufox currently supports only `xvfb_vnc`. It is Firefox-based, uses Playwright/Juggler, and is **not** a non-CDP mode of agent-browser. Stock Firefox is not a supported Verge engine.

The server must report RUNNING before automation. If it reports DEGRADED, inspect `metadata.runtime_error` and the session; do not silently start a replacement browser. A command timeout may have occurred after a click or submission: inspect the resulting state before retrying.

## Client setup

Use a CLI version matching the server. Camoufox support may require a source build until released; installing the published `latest` package does not prove support. Both the Python and Node Verge CLIs use the same commands below. The client machine does **not** need Python Camoufox, Firefox or a downloaded browser: the managed Python `camoufox-cli` command engine runs inside the remote sandbox.

For Chromium/Cloak only, install `agent-browser` if missing. Remote CDP usage does not require `agent-browser install` to download a local browser. Never fall back to a bare `agent-browser open` if CDP fails.

```bash
export VERGE_BROWSER_URL="https://verge.example.com"
export VERGE_BROWSER_TOKEN="replace-with-admin-token"
verge-browser sandbox list --json
verge-browser sandbox get demo --json
```

## Chromium and CloakBrowser

```bash
verge-browser sandbox create --alias demo --browser-engine chromium --json
export AGENT_BROWSER_SESSION="verge-demo"
CDP_URL="$(verge-browser sandbox cdp demo --mode reusable --ttl-sec 300 --json | jq -r '.cdp_url')"
agent-browser --cdp "$CDP_URL" snapshot -i
# Choose refs from the actual snapshot, not these illustrative numbers.
agent-browser --cdp "$CDP_URL" fill @e2 "hello@example.com"
agent-browser --cdp "$CDP_URL" snapshot -i
agent-browser --cdp "$CDP_URL" click @e3
```

Cloak uses `--browser-engine cloakbrowser` and the same CDP flow, after server configuration. Free Cloak keys support one active browser; pause the previous Cloak sandbox first.

CDP tickets default to reusable with a 60-second TTL; obtain a fresh URL after expiry. Session tickets default to one-time. Avoid permanent tickets unless explicitly needed. Refresh snapshots after navigation, DOM changes, tab changes, or human input. See [references/agent-browser-examples.md](references/agent-browser-examples.md) for CDP-only examples.

## Camoufox

Read [references/camoufox.md](references/camoufox.md) for supported commands, refs, tab selection, and file uploads. Short flow:

```bash
verge-browser sandbox create --alias fox --browser-engine camoufox --kind xvfb_vnc --default-url https://example.com --json
verge-browser sandbox get fox --json
verge-browser browser snapshot fox -i --json
# Replace @e1 with a ref from this sandbox's latest snapshot.
verge-browser browser click fox @e1 --json
verge-browser browser snapshot fox -i --json
```

Do not obtain a CDP ticket for Camoufox (the API rejects it). These commands reuse the existing headed persistent context via a managed worker; they do not spawn a local browser or a native CLI daemon. Do not run upstream `install`, `open`, `close`, or `--all` against the sandbox. Use Verge lifecycle commands.

## Shared lifecycle, files and human handoff

```bash
verge-browser browser screenshot demo --type window --format png --output ./window.png --json
verge-browser browser screenshot demo --type page --format png --output ./page.png --json
verge-browser browser actions demo --input ./actions.json --json
verge-browser sandbox session demo --json
verge-browser files upload demo ./local-file.txt --json
verge-browser files list demo /workspace/downloads --json
verge-browser files download demo /workspace/downloads/report.txt --output ./report.txt --json
verge-browser sandbox pause demo --json
verge-browser sandbox resume demo --json
verge-browser sandbox restart demo --json
```

Session URLs show the same live browser used by automation. For MFA or other human-only steps, hand off through the session, then select the intended tab and take a new snapshot before continuing. Page coordinates and full-window coordinates differ; use returned viewport metadata for GUI actions, not a fixed toolbar offset. Camoufox screenshots currently require PNG and do not accept CDP target IDs.

Pause/resume retains the profile and identity. Restart is explicit. `sandbox rm` deletes the sandbox **and its profile/files**; use it only when deletion is intended.

See [references/commands.md](references/commands.md) for the shared API/SDK patterns. Camoufox exceptions in this skill take precedence over CDP-only examples.
