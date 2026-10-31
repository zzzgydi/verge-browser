# Managed Camoufox commands

Run these through **Verge Browser**, not the standalone upstream CLI. The API is `POST /sandbox/{id-or-alias}/browser/command`, authenticated with the normal admin bearer token. The remote worker reuses pinned Python `camoufox-cli` refs, identity and command handlers in Verge's existing headed context.

## Commands

```bash
verge-browser browser open fox https://example.com --json
verge-browser browser snapshot fox -i --json
verge-browser browser snapshot fox --selector '#form' --json
verge-browser browser fill fox @e1 'Ada' --json
verge-browser browser snapshot fox -i --json
verge-browser browser click fox @e2 --json
verge-browser browser press fox Enter --json
verge-browser browser text fox body --json
verge-browser browser url fox --json
verge-browser browser title fox --json
verge-browser browser tabs fox --json
verge-browser browser switch fox 1 --json
```

Refs are scoped to the latest snapshot of a named tab. Never copy refs between sandboxes/tabs/clients, or reuse illustrative refs. Navigation, switching, clicks, fill and press invalidate refs: take a fresh snapshot before the next ref operation. Clicking uses native Playwright input, not upstream's DOM `el.click()` workaround.

The default tab handle is `default`. `open --tab research` creates or navigates that handle within the **same context**; subsequent commands must include `--tab research`. A new human-created tab or popup may initially have no handle: `tabs` returns indexes, and `switch INDEX --tab research` adopts one. Indexes may change when tabs close; list again before switching. `active` means the handle's selected page, not necessarily the tab a human last focused. After handoff, explicitly switch to the intended tab. GUI actions always target the visible window.

```bash
verge-browser browser open fox https://example.com --tab research --json
verge-browser browser snapshot fox --tab research -i --json
verge-browser browser tabs fox --json
verge-browser browser switch fox 0 --json
```

## Files

First upload to the workspace; then set the input using the returned **remote** path:

```bash
verge-browser files upload fox ./sample.txt --json
verge-browser browser upload fox 'input[type=file]' /workspace/uploads/sample.txt --json
verge-browser files list fox /workspace/downloads --json
```

Uploads are restricted to real files under `/workspace/uploads`. Browser downloads are saved under `/workspace/downloads`. Inspect the download list before fetching. Do not upload a host path directly to the browser command.

## API / SDK equivalent

```json
{"action":"fill","tab":"default","ref":"@e1","text":"Ada"}
```

Python: `client.browser_command("fox", payload)`.
Node: `await client.browserCommand("fox", payload)`.

Errors return a non-success HTTP response and a nonzero CLI exit status. Invalid refs and timeouts are not retried. The gateway does not accept `eval`, shell commands, cookies manipulation, daemon control, arbitrary launch flags or raw protocol operations. Use supported DOM commands, GUI actions or human handoff. A stopped/degraded browser must be recovered through explicit Verge lifecycle operations, not upstream daemon auto-recovery.

Supported configuration: Xvfb/noVNC, persistent profile, no GPU and no proxy settings yet. No CDP/BiDi endpoint, Xpra support, general stock-Firefox support, or claim of undetectability.
