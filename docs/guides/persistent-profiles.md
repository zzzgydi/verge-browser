# Persistent Browser Profiles and Lifecycle

Verge Browser persists a sandbox's workspace and metadata on the Docker host. With the default settings, Chromium uses `/workspace/browser-profile`, and shared files live under `/workspace`, including `downloads` and `uploads`.

This is **on-disk persistence**, not a snapshot of browser memory. Cookies and other profile data that Chromium has saved may be reused, but website expiry, revocation, session-only cookies, and unflushed writes can still require a new login.

## What Each Operation Preserves

| Operation | Runtime and connections | Persisted data |
| --- | --- | --- |
| `sandbox pause` | Removes the runtime container; browser, CDP, and viewer connections stop | Keeps the workspace, profile directory, and sandbox metadata |
| `sandbox resume` | Creates a runtime for the same sandbox and waits for readiness | Mounts the existing workspace; does not restore browser memory or guarantee the same tabs |
| `sandbox restart` | Restarts Chromium, or recreates a missing runtime | Reuses the workspace; current connections and unsaved browser state can be lost |
| API server restart | Reloads metadata and reconciles surviving running containers; records without a running container stay `STOPPED` | Requires the same persisted directory and mount mapping; client connections and in-memory viewer sessions must be re-established |
| `sandbox rm` | Removes the runtime and sandbox record | Deletes the sandbox directory, including the profile and shared files |
| Create again with the same alias after deletion | Creates a new sandbox ID and workspace | Does not recover the deleted profile |

Pause currently uses forced container removal, not a graceful Chromium checkpoint. Save important work before stopping it; preservation of directories is not a guarantee that every recent browser write has reached disk.

## Reuse a Profile

After configuring the [CLI](../cli-sdk.md), create a sandbox once, log in through its visual session, and reuse that sandbox's ID or alias:

```bash
verge-browser sandbox create --alias account-demo --json
verge-browser sandbox get account-demo --json
verge-browser sandbox session account-demo --mode one_time --ttl-sec 900 --json
```

Wait for `RUNNING` before opening the session. When done, stop automation and close out any work before releasing the runtime:

```bash
verge-browser sandbox pause account-demo --json
verge-browser sandbox resume account-demo --json
verge-browser sandbox get account-demo --json
verge-browser sandbox session account-demo --mode one_time --ttl-sec 900 --json
```

After resume, confirm `RUNNING`, inspect the actual page, and sign in again if the site requires it. CDP clients also need to reconnect; a fresh ticket avoids attempting a connection with an expired URL.

Use separate sandboxes for independent accounts. Do not share one profile directory between concurrently running Chromium instances. Keep backups of the sandbox directory, including metadata, if you need recovery beyond the local disk; there is no built-in backup/restore service.

The persistence unit tests cover workspace reuse and startup reconciliation. They do not establish that any particular website's login or running tabs survive a lifecycle operation.
