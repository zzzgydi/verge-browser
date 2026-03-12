# verge-browser

Node.js SDK and CLI for [Verge Browser](https://github.com/zzzgydi/verge-browser) - a browser sandbox system for agent workflows.

## Features

- **TypeScript-first**: Full type definitions included
- **SDK + CLI**: Use programmatically or from command line
- **ESM-native**: Modern ES module support
- **Control plane coverage**: Sandbox lifecycle, browser controls, VNC/CDP, and files APIs
- **Lightweight**: Minimal runtime dependency surface (CLI uses `cac`)

## Installation

```bash
npm install verge-browser
```

## SDK Usage

```typescript
import { VergeClient } from 'verge-browser';

const client = new VergeClient({
  baseUrl: 'http://127.0.0.1:8000',
  token: 'your-api-token',
});

// List all sandboxes
const sandboxes = await client.listSandboxes();

// Create a sandbox
const sandbox = await client.createSandbox({
  alias: 'my-sandbox',
  width: 1280,
  height: 720,
});

// Get VNC URL
const vnc = await client.getVncUrl(sandbox.id);
console.log(vnc.url);

// Get CDP info
const cdp = await client.getCdpInfo(sandbox.id);
console.log(cdp.cdp_url);

// Inspect the browser viewport
const viewport = await client.getBrowserViewport(sandbox.id);
console.log(viewport.active_window.title);

// Execute GUI actions
await client.executeBrowserActions(sandbox.id, {
  actions: [
    { type: 'HOTKEY', keys: ['ctrl', 'l'] },
    { type: 'TYPE_TEXT', text: 'https://example.com' },
    { type: 'KEY_PRESS', key: 'Return' },
  ],
});

// Read and write workspace files
await client.writeFile(sandbox.id, {
  path: '/workspace/notes.txt',
  content: 'hello verge',
  overwrite: true,
});
const file = await client.readFile(sandbox.id, '/workspace/notes.txt');
console.log(file.content);

// Cleanup
await client.deleteSandbox(sandbox.id);
```

### Environment Variables

The client reads from environment variables if options are not provided:

```bash
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=your-api-token
```

### Error Handling

```typescript
import { VergeAuthError, VergeNotFoundError, VergeValidationError } from 'verge-browser';

try {
  await client.getSandbox('non-existent');
} catch (error) {
  if (error instanceof VergeNotFoundError) {
    console.log('Sandbox not found');
  }
}
```

## CLI Usage

Install globally or use with `npx`:

```bash
npx verge-browser --help
```

### Configuration

Set environment variables or pass flags:

```bash
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=dev-admin-token
```

### Commands

```bash
# List sandboxes
verge-browser sandbox list

# Create a sandbox
verge-browser sandbox create --alias shopping --width 1440 --height 900

# Get sandbox info
verge-browser sandbox get shopping

# Get CDP info
verge-browser sandbox cdp shopping --json

# Get VNC URL
verge-browser sandbox vnc shopping --json

# Restart Chromium inside a sandbox
verge-browser sandbox restart shopping --json

# Inspect the active browser window
verge-browser browser info shopping --json
verge-browser browser viewport shopping --json

# Save a screenshot locally
verge-browser browser screenshot shopping --output ./shot.png --json

# Execute GUI actions from a JSON file
verge-browser browser actions shopping --input ./actions.json --json

# List, read, write, upload, download, and delete workspace files
verge-browser files list shopping /workspace --json
verge-browser files read shopping /workspace/notes.txt
verge-browser files write shopping /workspace/notes.txt --content "hello verge" --overwrite --json
verge-browser files upload shopping ./local-file.txt --json
verge-browser files download shopping /workspace/notes.txt --output ./notes.txt --json
verge-browser files rm shopping /workspace/notes.txt --json

# Update alias
verge-browser sandbox update shopping --alias new-name

# Pause/Resume
verge-browser sandbox pause shopping
verge-browser sandbox resume shopping

# Delete
verge-browser sandbox rm shopping
```

### Global Options

- `--base-url <url>` - API base URL
- `--token <token>` - API bearer token
- `--json` - Output JSON format
- `--help` - Show help
- `--version` - Show version

## API Reference

### `VergeClient`

#### Constructor

```typescript
new VergeClient(options?: VergeClientOptions)
```

**Options:**
- `baseUrl?: string` - API base URL (default: `process.env.VERGE_BROWSER_URL` or `http://127.0.0.1:8000`)
- `token?: string` - API bearer token (default: `process.env.VERGE_BROWSER_TOKEN`)
- `fetchImpl?: FetchLike` - Custom fetch implementation

#### Methods

| Method | Description |
|--------|-------------|
| `listSandboxes()` | List all sandboxes |
| `createSandbox(payload)` | Create a new sandbox |
| `getSandbox(idOrAlias)` | Get sandbox by ID or alias |
| `updateSandbox(idOrAlias, payload)` | Update sandbox alias |
| `deleteSandbox(idOrAlias)` | Delete a sandbox |
| `pauseSandbox(idOrAlias)` | Pause a sandbox |
| `resumeSandbox(idOrAlias)` | Resume a sandbox |
| `restartBrowser(idOrAlias)` | Restart Chromium inside a sandbox |
| `getBrowserInfo(idOrAlias)` | Fetch browser version and active viewport |
| `getBrowserViewport(idOrAlias)` | Fetch window and page viewport metadata |
| `getBrowserScreenshot(idOrAlias, options?)` | Capture a window or page screenshot |
| `executeBrowserActions(idOrAlias, payload)` | Execute GUI actions via `xdotool` |
| `getCdpInfo(idOrAlias)` | Get Chrome DevTools Protocol info |
| `createVncTicket(idOrAlias, options?)` | Create a VNC access ticket |
| `getVncUrl(idOrAlias)` | Get VNC URL with ticket |
| `listFiles(idOrAlias, path?)` | List sandbox files |
| `readFile(idOrAlias, path)` | Read a UTF-8 text file |
| `writeFile(idOrAlias, payload)` | Write a UTF-8 text file |
| `uploadFile(idOrAlias, payload)` | Upload a local file into `/workspace/uploads` |
| `downloadFile(idOrAlias, path)` | Download a file as bytes |
| `deleteFile(idOrAlias, path)` | Delete a file or empty directory |

### Error Classes

- `VergeError` - Base error class
- `VergeConfigError` - Configuration errors
- `VergeAuthError` - Authentication failures (401)
- `VergeNotFoundError` - Resource not found (404)
- `VergeConflictError` - Request conflict (409)
- `VergeValidationError` - Validation failures (422)
- `VergeServerError` - Server errors (5xx)

## Requirements

- Node.js >= 20

## License

MIT
