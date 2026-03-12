# verge-browser

Node.js SDK and CLI for [Verge Browser](https://github.com/zzzgydi/verge-browser) — a browser sandbox system for agent workflows.

## Features

- **TypeScript-first** — Full type definitions with IntelliSense support
- **SDK + CLI** — Use programmatically or from command line
- **ESM-native** — Modern ES module support
- **Complete API coverage** — Sandbox lifecycle, browser controls, CDP, session tickets, and file operations
- **Lightweight** — Minimal runtime dependencies (CLI uses `cac`)

## Installation

```bash
npm install verge-browser
```

Or use with `npx` (no installation required):

```bash
npx verge-browser --help
```

## Quick Start

### SDK Usage

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

Import specific error classes for fine-grained handling:

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
| `deleteSandbox(idOrAlias)` | Delete a sandbox |
| `pauseSandbox(idOrAlias)` | Pause a sandbox |
| `resumeSandbox(idOrAlias)` | Resume a sandbox |

#### Browser Control

| Method | Description |
|--------|-------------|
| `getBrowserInfo(idOrAlias)` | Get browser version and viewport info |
| `getBrowserViewport(idOrAlias)` | Get window and page viewport metadata |
| `getBrowserScreenshot(idOrAlias, options?)` | Capture screenshot (window or page) |
| `executeBrowserActions(idOrAlias, payload)` | Execute GUI actions (click, type, scroll, etc.) |
| `restartBrowser(idOrAlias, payload?)` | Restart Chromium inside sandbox |

#### CDP & Session

| Method | Description |
|--------|-------------|
| `getCdpInfo(idOrAlias, options?)` | Get Chrome DevTools Protocol WebSocket URL |
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
| `VergeConfigError` | — | Configuration errors (missing token, etc.) |
| `VergeAuthError` | 401 | Authentication failed |
| `VergeNotFoundError` | 404 | Resource not found |
| `VergeConflictError` | 409 | Request conflict |
| `VergeValidationError` | 413, 422 | Validation/payload errors |
| `VergeServerError` | 5xx | Server errors |

### Types

```typescript
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

## Requirements

- Node.js >= 18

## License

MIT
