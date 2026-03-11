# @verge-browser/cli

Node.js implementation of the `verge-browser` CLI (built with TypeScript, native ESM, and `cac`).

## Environment Variables

```bash
export VERGE_BROWSER_URL=http://127.0.0.1:8000
export VERGE_BROWSER_TOKEN=dev-admin-token
```

## Check

```bash
pnpm install
pnpm run check
pnpm test
```

## Command Examples

```bash
verge-browser sandbox list --json
verge-browser sandbox create --alias shopping --width 1440 --height 900
verge-browser sandbox get shopping --json
verge-browser sandbox cdp shopping --json
verge-browser sandbox vnc shopping --json
verge-browser sandbox pause shopping --json
verge-browser sandbox resume shopping --json
verge-browser sandbox rm shopping --json
```
