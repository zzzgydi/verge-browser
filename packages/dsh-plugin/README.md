# Verge Browser for DeepSeek Harness

English | [Chinese](README.zh.md)

Use DSH to control an existing Verge browser. The plugin does not install or start a browser on the DSH host.

This is a preview package. It is not published to npm.

## Functions

| Function | Scope |
| --- | --- |
| Page actions | Navigate, read page state, click, enter text, and select tabs. Tools depend on the browser engine. |
| Screenshots | Capture a page or the full browser window as PNG. |
| Human handoff | Block this connection's automation and return a temporary link for manual control. |
| Remote files | List files and read or write UTF-8 text inside `/workspace`. |
| DSH integration | Use Agent-scoped tools, DSH tool policies, image attachments, and programmatic tool calling. |

## Terms

| Term | Meaning |
| --- | --- |
| Sandbox | An existing Verge environment with a browser and remote files. |
| Agent | The live DSH agent that uses this plugin's browser tools. |
| Profile | The DSH configuration that selects plugins and tool policies. |
| Provider | The plugin instance that occupies DSH's `browserUse` slot. |
| Bridge | The plugin process that exposes browser tools through the Model Context Protocol (MCP). |
| CDP | Chrome DevTools Protocol, used to connect to Chromium and Cloak. |
| Snapshot | Page text and element references. It is not a screenshot. |
| PTC | Programmatic tool calling through DSH's `run_code` tool. |

## Requirements

| Item | Requirement |
| --- | --- |
| DSH | `^0.2.0`. Later `0.3.x` releases need the exact-version exemption. Requires the host's Agent, MCP, tools, scope, system prompt, and working-directory services. |
| Node | `>=22.12.0`. Local tests used `22.21.1`. |
| Playwright MCP | Pinned to `0.0.80`. |
| Verge | An accessible API, an admin token, and an existing sandbox in `RUNNING` state. |
| Images | An image-capable model and a DSH attachment store. |

`engines.dsh: "^0.2.0"` admits `0.2.0` and every later `0.2.x` release, including prereleases.
It rejects `0.3.0` and its prereleases. Host DSH peers use the same range.
For an untested DSH release, grant the exact-version exemption:
`dsh plugin --profile YOUR_PROFILE allow-version dsh-plugin-verge-browser@0.1.1 --dsh-version <exact-version> --accept-risk`.
Browser helpers are bundled at the tested version. Host services remain shared, not bundled.
Development dependencies stay pinned for reproducible builds. Do not replace them with `latest`.

## Build and install

1. Open the complete Verge repository.
2. Install dependencies from the repository root.

   ```bash
   pnpm --dir packages/dsh-plugin install --ignore-scripts --registry=https://registry.npmjs.org
   ```

3. Build the package.

   ```bash
   pnpm --dir packages/dsh-plugin build
   ```

4. Check the package.

   ```bash
   pnpm --dir packages/dsh-plugin check
   pnpm --dir packages/dsh-plugin test
   ```

5. Create the package archive.

   ```bash
   cd packages/dsh-plugin
   npm pack
   ```

6. Install the archive into your target profile.

   Replace `YOUR_PROFILE` with the profile name. Run this command from `packages/dsh-plugin`.

   ```bash
   dsh plugin --profile YOUR_PROFILE add ./dsh-plugin-verge-browser-0.1.1.tgz --registry=https://registry.npmjs.org
   ```

The archive includes the matching Verge SDK. It does not need an adjacent SDK directory at runtime.
Archive installation does not build the plugin or download a browser.
Source installation from a Git subdirectory is not supported.

### Upgrade from 0.1.0

Install the new archive into the same profile, then restart DSH.
Do not grant a version exemption. The old npm `0.1.0` still requires DSH `0.2.1-rc.2`.
Existing row IDs and connection settings stay the same.
If your profile overrides the `verge-browser-registry` row's `name`, change that name to
`dsh-plugin-verge-browser/registry`. Leave the row disabled when the scope already has `browserUse`.

### Install from a plugin index

Once a version is on npm, DSH can list it from this repository's plugin index:

```text
https://raw.githubusercontent.com/zzzgydi/verge-browser/main/packages/dsh-plugin/market/index.json
```

1. Open **Plugins** and switch on **Custom plugin indexes** under **Experimental plugins**.
2. Open **Discover**, choose **Add index source**, and paste the URL.
3. Pick a version the running DSH accepts, then confirm the source.

The index lists published npm versions only. [market/README.md](https://github.com/zzzgydi/verge-browser/blob/main/packages/dsh-plugin/market/README.md) records how to
keep it in step with a release.

If a development tool lacks its platform binary, complete that tool's approved setup before building.

## Configure

Installation leaves both plugin entries disabled. It does not contact Verge.

1. Set these variables in the environment that starts DSH.

   | Variable | Value |
   | --- | --- |
   | `VERGE_BROWSER_URL` | Verge API URL. Do not use a CDP or handoff URL. |
   | `VERGE_BROWSER_TOKEN` | Verge admin token. Do not use a CDP ticket. |
   | `VERGE_BROWSER_SANDBOX` | Existing sandbox ID or alias. |

2. Disable any competing browser-use provider in the target scope.
3. Add this configuration to the target profile's `cordis.patch.yml`.

   If the scope already has a `browserUse` service, keep `verge-browser-registry` disabled instead.

   ```yaml
   - id: verge-browser-registry
     disabled: false
   - id: verge-browser
     disabled: false
     config:
       baseUrl: !!js process.env.VERGE_BROWSER_URL
       token: !!js process.env.VERGE_BROWSER_TOKEN
       sandbox: !!js process.env.VERGE_BROWSER_SANDBOX
   ```

4. Start the target DSH profile with these environment variables.
5. Create or resume an Agent after the plugin is enabled.

The plugin does not attach tools to Agents that were already live when it was enabled.
DSH accepts only one browser-use provider in each scope.

Keep the API private or access it through a tunnel. Do not put credentials in tool arguments or reports.
The API URL and CDP endpoint must have the same host and port.
An HTTPS API URL requires a `wss:` CDP endpoint.

### Timeouts and ticket lifetime

| Configuration field | Default | Allowed values |
| --- | --- | --- |
| `requestTimeoutMs` | `30000` milliseconds | Integer from 1 to 300000 |
| `toolCallTimeoutMs` | `60000` milliseconds | Integer from 1 to 300000 |
| `cdpTicketTtlSec` | `300` seconds | Integer from 1 to 3600 |
| `handoffTtlSec` | `300` seconds | Integer from 1 to 3600 |

Keep all connection fields when changing a timeout. DSH overrides replace the complete `config` object.

## Use the tools

Ask the Agent to inspect the browser before it acts.
Tool names have the prefix `mcp__verge-browser__`.
The server's `browser_engine` selects the browser tools.

| Shared tool | Function |
| --- | --- |
| `verge_status` | Read the selected sandbox ID, engine, status, viewport, and automation state. |
| `verge_screenshot` | Return a page or full-window PNG. |
| `verge_handoff` | Block this bridge's automation and return a one-time handoff link. |
| `verge_resume` | Allow automation after handoff or an interrupted operation. |
| `verge_files_list` | List files inside the remote `/workspace`. |
| `verge_file_read` | Read up to 64 KiB of UTF-8 text. |
| `verge_file_write` | Write up to 64 KiB of UTF-8 text. Existing files require `overwrite: true`. |

Remote `/workspace` paths are not paths on the DSH host.
Page and window screenshots use different coordinate systems.
Without image support, DSH returns a diagnostic instead of claiming that the model inspected an image.

### Browser tools

Chromium and Cloak use CDP with selected Playwright MCP tools.
Camoufox uses the Verge command API, not CDP.

| Task | Chromium / Cloak | Camoufox |
| --- | --- | --- |
| Navigate | `browser_navigate`, `browser_navigate_back` | `verge_open` |
| Read page state | `browser_snapshot` | `verge_snapshot`, `verge_text`, `verge_url`, `verge_title` |
| Enter data | `browser_click`, `browser_type`, `browser_press_key` | `verge_click`, `verge_fill`, `verge_press` |
| Forms | `browser_hover`, `browser_select_option`, `browser_fill_form` | Use click and fill tools. |
| Dialogs and waiting | `browser_handle_dialog`, `browser_wait_for` | No separate tools. |
| Tabs | `browser_tabs`: list, new, select | `verge_tabs`, `verge_switch` |
| Upload to a page | Not exposed | `verge_upload`: select a file already inside the remote `/workspace`. |

The plugin does not expose these operations:

- Browser installation or closing.
- Tab closing.
- Arbitrary JavaScript execution.
- Local file upload.
- Playwright output-file parameters.

## Watch the browser in the sidebar

In a Web profile the plugin also adds a **Verge Browser** tab to the right Sidebar.
Open the right Sidebar, then pick **Verge Browser** from its guide.
The tab shows the same browser window that a person sees in Xpra or noVNC, and it accepts mouse and keyboard input.

The tab needs no second login.
The Host fetches a reusable session ticket with `handoffTtlSec` as its lifetime, then proxies the session page, its assets, and its WebSocket through the DSH origin.
The browser receives neither the admin token nor the Verge session cookie, and no third-party cookie is involved.
Press **Reconnect** to drop the frame and request a fresh ticket.

| Limit | Behavior |
| --- | --- |
| Web only | Headless and desktop compositions have no HTTP server, so they expose the tools and no tab. |
| One sandbox | Every Agent in this plugin instance shows the same configured sandbox. |
| Configured target only | The proxy forwards to the configured sandbox session and to no other host or path. |
| Trusted local | The profile's HTTP server serves `GET /verge-browser/session/`; do not bind it to an untrusted network. |

## Hand off to a person

Do not copy handoff links into reports. Each link grants temporary access and is recorded in the conversation.

1. Ask the Agent to call `verge_handoff`.
2. Open the returned link for manual control.
3. Complete the manual task.
4. Confirm completion to the Agent.
5. Ask the Agent to call `verge_resume`.
6. Ask the Agent to take a new snapshot before acting.

During handoff, only status, handoff, and resume tools remain available through this bridge.
Other clients and people can still change the browser.
Do not reuse element references from before handoff.

## Recover from an error

Do not repeat a timed-out action without checking the browser. The server can finish an action after the client stops waiting.

1. Inspect the browser through the Verge CLI or admin console.
2. Confirm that the remote action has stopped.
3. Call `verge_resume` if automation is interrupted.
4. Take a new snapshot before the next action.

The plugin does not replay failed actions automatically.
HTTP cancellation does not undo a remote command or guarantee that it stopped.
Confirm that remote work has stopped before requesting handoff after an error.

During CDP connection setup, cancellation waits for Playwright to return or time out.
The plugin then disconnects the client.
The connection wait is bounded by `requestTimeoutMs`, which defaults to 30 seconds.
Cleanup errors are reported. A failed handoff keeps automation blocked until explicit resume.

## Ownership and limits

One live Agent reserves the sandbox connection within this provider instance.
Other Agents remain usable without this provider's browser tools.
After release, create or reactivate an Agent to acquire the connection.

Unloading the provider disconnects its client.
It does not pause, restart, delete, or close the remote browser.
The reservation is not a cross-process lock.

This preview does not provide:

- Automatic sandbox creation for each Agent.
- Binary file transfer between the DSH host and the sandbox.
- A custom DSH handoff card.
- Coordination with other browser clients.

Use the Verge CLI or admin console to manage sandboxes and transfer binary files.
Cloak requires its separately configured engine and authorization.

## DSH behavior

Tools use DSH's normal session-scoped MCP pipeline.
Structured results remain available to PTC.
Screenshots use DSH's image-attachment pipeline.

Apply the target profile's tool policy to website actions.
Installing the plugin does not approve every action.
Treat page content and files as untrusted data, not instructions.

Tool schemas and guidance remain stable across turns.
The browser engine determines which catalog is available.
The plugin does not add a model loop or make separate model calls.

## Verification

Local verification on 2026-11-01 passed with DSH `0.2.1-rc.2`:

| Check | Verified scope |
| --- | --- |
| Build, types, and 14 package tests | Built bridge, Agent isolation, policy rejection, argument limits, and error recovery. |
| DSH attachments | Missing-store diagnostic, image storage, and image read-back with a test model route. |
| Archive installation and PTC | Isolated profile, real DSH Loader, real Agent, and `run_code`. No model calls. |
| Chromium and Camoufox | Two real Docker scenarios, also run against the installed archive. |

Docker coverage includes native clicks, PNG capture, remote files, and one-time session access.
It also covers blocked automation during handoff, GUI input, resume, and preservation after disconnect.

Not verified: Cloak, Xpra, Desktop rendering, real model vision, and real login or MFA workflows.
Tests do not cover every network failure or every Agent fork/resume path.
Chromium results do not verify Cloak.

### Repeat local checks

Run from the repository root:

```bash
pnpm --dir packages/dsh-plugin check
pnpm --dir packages/dsh-plugin build
pnpm --dir packages/dsh-plugin test
```

### Repeat Docker checks

Build the plugin and runtime images before running this test.
Replace the binary path with your Camoufox directory.
Run from the repository root in the Python development environment:

```bash
VERGE_DSH_RUNTIME_TEST=1 \
VERGE_CAMOUFOX_BINARY_DIR=/absolute/path/to/camoufox \
PYTHONPATH=apps/api-server pytest tests/integration/test_dsh_plugin.py
```

### Repeat the DSH profile check

Use a disposable `DSH_HOME`. This test creates a real Agent and stores test session data.

1. Install the archive into profile `verify` under that home.
2. Run this command from the repository root.

   ```bash
   DSH_HOME=/absolute/path/to/disposable-home pnpm --dir packages/dsh-plugin test:profile
   ```

This check uses a mock Verge API and real DSH PTC.
It makes no model calls and does not change saved profile configuration.

## License

Original plugin code is MIT.
Dependencies retain their own licenses.
The archive contains no browser binaries or fonts.
Optional engines retain their existing distribution restrictions.
