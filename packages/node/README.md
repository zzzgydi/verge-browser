# verge-browser

Node.js SDK and CLI for [Verge Browser](https://github.com/zzzgydi/verge-browser) — a browser sandbox system for agent workflows.

## Features

- **Types** — TypeScript definitions for SDK requests and responses.
- **SDK and CLI** — Call the API from code or the command line.
- **Modules** — Native ES module support.
- **API access** — Sandbox lifecycle, browser controls, CDP tickets, visual sessions, and file operations.
- **Engine selection** — Chromium, optional CloakBrowser, and experimental Camoufox.
- **Camoufox commands** — Control the remote Firefox-based browser through Verge's command API, not CDP.
- **CLI parser** — Uses `cac`.

## Installation

```bash
npm install verge-browser
```

Or let `npx` download and run the package:

```bash
npx verge-browser --help
```

### Version compatibility

This source tree prepares **0.4.0**. At the 2026-11-03 registry check, npm `latest` was **0.3.0**.
Version 0.3.0 has neither engine selection nor managed Camoufox commands.
Check the published version before installing:

```bash
npm view verge-browser version
verge-browser --version
```

Until 0.4.0 is published, build from this repository:

```bash
pnpm --dir packages/node install --frozen-lockfile
pnpm --dir packages/node build
node packages/node/dist/src/cli.js --version
node packages/node/dist/src/cli.js sandbox create --alias fox --browser-engine camoufox --json
```

The create command requires a configured API and Camoufox runtime.
Upgrading this client does not upgrade the API or install a browser.

## Quick Start

### SDK Usage

Use a disposable sandbox for this example. The last call deletes its profile and files.
Replace `your-api-token` with your deployment's admin token. Do not commit the real token.
Keep the console output private: the example prints a ticketed session URL.

```typescript
import { VergeClient } from 'verge-browser';

const client = new VergeClient({
  baseUrl: 'http://127.0.0.1:8000',
  token: 'your-api-token',
});

// Create a sandbox
const sandbox = await client.createSandbox({
  alias: 'my-sandbox',
  width: 1280,
  height: 720,
});

// Get session URL for VNC access
const session = await client.getSessionUrl(sandbox.id);
console.log('Session URL:', session.url);

// Take a screenshot
const screenshot = await client.getBrowserScreenshot(sandbox.id, {
  type: 'page',
  format: 'png',
});

// Execute browser actions
await client.executeBrowserActions(sandbox.id, {
  actions: [
    { type: 'HOTKEY', keys: ['ctrl', 'l'] },
    { type: 'TYPE_TEXT', text: 'https://example.com' },
    { type: 'KEY_PRESS', key: 'Return' },
  ],
});

// Cleanup
await client.deleteSandbox(sandbox.id);
```

### Environment Variables

The SDK reads configuration from environment variables:

```bash
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=your-api-token
```

Then initialize without options:

```typescript
const client = new VergeClient(); // Uses env vars automatically
```

### CLI Usage

Use `dev-admin-token` only for local development.
Install the CLI globally, or prefix each command with `npx`.
Create `actions.json` and `local-file.txt` before running the commands that use them.

Use a disposable sandbox. The last command deletes its profile and files.
The `--overwrite` command replaces existing file content.

```bash
# Set environment variables
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=dev-admin-token

# List sandboxes
verge-browser sandbox list

# Create a sandbox
verge-browser sandbox create --alias shopping --width 1440 --height 900

# Get CDP info for browser automation
verge-browser sandbox cdp shopping --json

# Take a screenshot
verge-browser browser screenshot shopping --output ./shot.png

# Execute actions from a JSON file
verge-browser browser actions shopping --input ./actions.json

# File operations
verge-browser files list shopping /workspace
verge-browser files write shopping /workspace/notes.txt --content "hello" --overwrite
verge-browser files upload shopping ./local-file.txt

# Manage sandbox lifecycle
verge-browser sandbox pause shopping
verge-browser sandbox resume shopping
verge-browser sandbox rm shopping
```

## Error Handling

Handle errors that your application can resolve. Rethrow other errors, as this example does:

```typescript
import {
  VergeClient,
  VergeAuthError,
  VergeNotFoundError,
  VergeValidationError,
  VergeConflictError,
} from 'verge-browser';

try {
  await client.getSandbox('non-existent');
} catch (error) {
  if (error instanceof VergeNotFoundError) {
    console.log('Sandbox not found');
  } else if (error instanceof VergeAuthError) {
    console.log('Authentication failed');
  } else {
    throw error;
  }
}
```

## Camoufox

Use a matching API with the optional runtime enabled. Follow the [server setup and support boundary](https://github.com/zzzgydi/verge-browser/blob/main/docs/guides/camoufox.md).
The tested runtime uses Camoufox `v156.0.1-beta.36` on Linux ARM64 with Xvfb/noVNC and CPU rendering.
This is not support for stock Firefox or every Firefox release.
Camoufox does not support Xpra, GPU rendering, proxies, CDP, or BiDi through Verge.

Read `sandbox.browser_engine` before selecting an automation route:

| Engine | Automation route |
|--------|------------------|
| `chromium`, `cloakbrowser` | Get a ticket with `getCdpInfo()` or `sandbox cdp`; connect a CDP client such as `agent-browser`. |
| `camoufox` | Use `browserCommand()` or the managed CLI commands below. Do not request CDP. |

### SDK

Use a new alias for this example. Continue only when the sandbox reports `RUNNING`.

```typescript
import { VergeClient } from 'verge-browser';

const client = new VergeClient();
const sandbox = await client.createSandbox({
  alias: 'fox-sdk',
  browser_engine: 'camoufox',
  default_url: 'https://example.com',
});
if (sandbox.status !== 'RUNNING') {
  throw new Error(`Sandbox is ${sandbox.status}`);
}
const snapshot = await client.browserCommand(sandbox.id, {
  action: 'snapshot',
  interactive: true,
});
console.log(snapshot);
```

### CLI

Use a 0.4.0 client or replace `verge-browser` with the source command shown above.
These examples use a separate alias from the SDK example:

```bash
verge-browser sandbox create --alias fox-cli --browser-engine camoufox --default-url https://example.com --json
verge-browser sandbox get fox-cli --json
# Continue only when status is RUNNING.
verge-browser browser snapshot fox-cli -i --json
verge-browser browser open fox-cli https://example.org --tab research --json
verge-browser browser tabs fox-cli --json
verge-browser browser screenshot fox-cli --type page --format png --output ./fox.png --json
```

The commands operate on the remote sandbox, not a browser on the client machine.
Use PNG screenshots for Camoufox. Do not pass a CDP target ID.
Command failures return nonzero exit codes. Neither the SDK nor CLI retries failed commands.
After a stale element reference or GUI handoff, read a new snapshot before choosing another action.

| CLI after `verge-browser browser` | `browserCommand()` payload |
|---------------------------------|----------------------------|
| `open ID URL` | `{ action: 'open', url: 'https://example.com' }` |
| `snapshot ID -i` | `{ action: 'snapshot', interactive: true }` |
| `click ID REF` | `{ action: 'click', ref: '@e1' }` |
| `fill ID REF TEXT` | `{ action: 'fill', ref: '@e2', text: '' }` |
| `press ID KEY` | `{ action: 'press', key: 'Enter' }` |
| `text ID TARGET` | `{ action: 'text', target: '#result' }` |
| `tabs ID` | `{ action: 'tabs' }` |
| `switch ID INDEX` | `{ action: 'switch', index: 0 }` |
| `url ID` | `{ action: 'url' }` |
| `title ID` | `{ action: 'title' }` |
| `upload ID SELECTOR PATH` | `{ action: 'upload', selector: '#file', path: '/workspace/uploads/file.txt' }` |

Replace `ID`, `REF`, and other uppercase arguments with actual values.
Use references from the latest snapshot, not the example references in this table.
Tab indices start at zero. `--tab NAME` selects a named tab; the default is `default`.
Use `snapshot --selector CSS` to limit the snapshot scope.
Upload a local file with `files upload` before passing its remote `/workspace/...` path to `browser upload`.
For full semantics, see the [Camoufox command guide](https://github.com/zzzgydi/verge-browser/blob/main/skills/verge-browser-usage/references/camoufox.md).

## API Reference

### `VergeClient`

#### Constructor Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `baseUrl` | `string` | `VERGE_BROWSER_URL` or `http://127.0.0.1:8000` | API base URL |
| `token` | `string` | `VERGE_BROWSER_TOKEN` | API bearer token (required) |
| `fetchImpl` | `FetchLike` | `globalThis.fetch` | Custom fetch implementation |

#### Sandbox Management

| Method | Description |
|--------|-------------|
| `listSandboxes()` | List all sandboxes |
| `createSandbox(payload?)` | Create a new sandbox |
| `getSandbox(idOrAlias)` | Get sandbox by ID or alias |
| `updateSandbox(idOrAlias, payload)` | Update sandbox alias |
| `deleteSandbox(idOrAlias)` | Delete the runtime, profile, and shared files |
| `pauseSandbox(idOrAlias)` | Remove the runtime and keep the workspace |
| `resumeSandbox(idOrAlias)` | Start a runtime with the existing workspace |

#### Browser Control

| Method | Description |
|--------|-------------|
| `getBrowserInfo(idOrAlias)` | Get browser version and viewport info |
| `getBrowserViewport(idOrAlias)` | Get window and page viewport metadata |
| `getBrowserScreenshot(idOrAlias, options?)` | Capture screenshot (window or page) |
| `executeBrowserActions(idOrAlias, payload)` | Execute GUI actions; see `BrowserActionType` below |
| `restartBrowser(idOrAlias, payload?)` | Restart the sandbox's selected browser engine |
| `browserCommand(idOrAlias, payload)` | Run a managed command on a RUNNING Camoufox sandbox |

#### CDP & Session

| Method | Description |
|--------|-------------|
| `getCdpInfo(idOrAlias, options?)` | Get a ticketed CDP WebSocket URL for Chromium/CloakBrowser; Camoufox returns 409 |
| `createSessionTicket(idOrAlias, options?)` | Create VNC session access ticket |
| `getSessionUrl(idOrAlias)` | Get complete session URL with ticket |

#### File Operations

| Method | Description |
|--------|-------------|
| `listFiles(idOrAlias, path?)` | List directory contents |
| `readFile(idOrAlias, path)` | Read UTF-8 text file |
| `writeFile(idOrAlias, payload)` | Write UTF-8 text file |
| `uploadFile(idOrAlias, payload)` | Upload file to `/workspace/uploads` |
| `downloadFile(idOrAlias, path)` | Download file as bytes |
| `deleteFile(idOrAlias, path)` | Delete file or empty directory |

### Error Classes

| Class | HTTP Status | Description |
|-------|-------------|-------------|
| `VergeError` | — | Base error class |
| `VergeConfigError` | — | Client configuration error, such as a missing token |
| `VergeAuthError` | 401 | Authentication failed |
| `VergeNotFoundError` | 404 | Resource not found |
| `VergeConflictError` | 409 | Request conflict |
| `VergeValidationError` | 413, 422 | Validation/payload errors |
| `VergeServerError` | 5xx | Server errors |

### Types

```typescript
// Browser engine (independent of the Xvfb/Xpra desktop kind)
type BrowserEngine = 'chromium' | 'cloakbrowser' | 'camoufox';

// Sandbox status
type SandboxStatus = 'STARTING' | 'RUNNING' | 'STOPPED' | 'FAILED' | 'DEGRADED';

// Screenshot options
type ScreenshotType = 'window' | 'page';
type ScreenshotFormat = 'png' | 'jpeg' | 'webp';

// Browser actions
type BrowserActionType =
  | 'MOVE_TO' | 'CLICK' | 'DOUBLE_CLICK' | 'RIGHT_CLICK'
  | 'MOUSE_DOWN' | 'MOUSE_UP' | 'DRAG_TO' | 'SCROLL'
  | 'TYPE_TEXT' | 'KEY_PRESS' | 'HOTKEY' | 'WAIT';

// Session ticket mode
type AccessTicketMode = 'one_time' | 'reusable' | 'permanent';
```

## CLI Reference

### Global Options

| Option | Description |
|--------|-------------|
| `--base-url <url>` | API base URL |
| `--token <token>` | API bearer token |
| `--json` | Output JSON format |
| `--help` | Show help |
| `--version` | Show version |

### Commands

```
verge-browser sandbox <command>   Manage sandboxes
verge-browser browser <command>   Browser control
verge-browser files <command>     File operations
```

Use `verge-browser sandbox --help` or `verge-browser browser --help` for command options.
Create a selected engine with `sandbox create --browser-engine chromium|cloakbrowser|camoufox`.
The server checks engine availability and allowed desktop kinds.

## Requirements

- Node.js >= 18

## License

MIT
