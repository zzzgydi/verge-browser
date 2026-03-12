# verge-browser

Node.js SDK and CLI for [Verge Browser](https://github.com/verge-browser/verge-browser) - a browser sandbox system for agent workflows.

## Features

- **TypeScript-first**: Full type definitions included
- **SDK + CLI**: Use programmatically or from command line
- **ESM-native**: Modern ES module support
- **Lightweight**: Zero runtime dependencies (CLI uses `cac`)

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
| `getCdpInfo(idOrAlias)` | Get Chrome DevTools Protocol info |
| `createVncTicket(idOrAlias, options?)` | Create a VNC access ticket |
| `getVncUrl(idOrAlias)` | Get VNC URL with ticket |

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
