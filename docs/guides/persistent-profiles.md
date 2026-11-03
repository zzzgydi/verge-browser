# Persistent Browser Profiles and Lifecycle

Verge Browser stores a sandbox's workspace and metadata on the Docker host.
With default settings, Chromium uses `/workspace/browser-profile`. Shared files use `/workspace`, including its `downloads` and `uploads` directories.

This is **on-disk persistence**, not a snapshot of browser memory.
Chromium can reuse profile data that it saved to disk. Persistence does not guarantee that a website login survives.

A new login can be necessary after:

- Website session expiry or revocation.
- Loss of session-only cookies.
- Loss of browser writes that did not reach disk.

## What Each Operation Preserves

| Operation | Runtime and connections | Persisted data |
| --- | --- | --- |
| `sandbox pause` | Removes the runtime container; browser, CDP, and viewer connections stop | Keeps the workspace, profile directory, and sandbox metadata |
| `sandbox resume` | Creates a runtime for the same sandbox and waits for readiness | Mounts the existing workspace; does not restore browser memory or guarantee the same tabs |
| `sandbox restart` | Restarts Chromium, or recreates a missing runtime | Reuses the workspace; current connections and unsaved browser state can be lost |
| API server restart | Reloads metadata and reconciles surviving containers. Records without a running container stay `STOPPED`. | Requires the same persisted directory and mount mapping. Reconnect clients and create new viewer sessions. |
| `sandbox rm` | Removes the runtime and sandbox record | Deletes the sandbox directory, including the profile and shared files |
| Create again with the same alias after deletion | Creates a new sandbox ID and workspace | Does not recover the deleted profile |

Save important work before stopping Chromium. Chromium pause uses forced container removal, not a graceful browser checkpoint.
Keeping directories does not guarantee that recent writes reached disk.

Cloak and Camoufox use engine-specific close procedures before container removal.
See [Cloak lifecycle](cloak.md#pause-restart-and-updates) and [Camoufox lifecycle](camoufox.md#operate-the-existing-sandbox) for their failure behavior.

## Reuse a Profile

1. Configure the [CLI](../cli-sdk.md).
2. Create a sandbox once with the commands below.
3. Wait for `RUNNING`.
4. Open the returned visual session URL.
5. Log in to the website yourself.

Reuse this sandbox's ID or alias for later work.

```bash
verge-browser sandbox create --alias account-demo --json
verge-browser sandbox get account-demo --json
verge-browser sandbox session account-demo --mode one_time --ttl-sec 900 --json
```

Before releasing the runtime, stop automation and save your work.
The following commands pause the sandbox and start it again with the same workspace:

```bash
verge-browser sandbox pause account-demo --json
verge-browser sandbox resume account-demo --json
verge-browser sandbox get account-demo --json
verge-browser sandbox session account-demo --mode one_time --ttl-sec 900 --json
```

After resume:

1. Confirm `RUNNING`.
2. Inspect the current page.
3. If the site requests it, sign in again.
4. Reconnect CDP clients with a fresh ticket.

Use separate sandboxes for independent accounts. Do not share a profile directory between concurrent Chromium instances.
For recovery after disk loss, back up the sandbox directory and its metadata. Verge Browser has no built-in backup or restore service.

The persistence unit tests cover workspace reuse and startup reconciliation. They do not establish that any particular website's login or running tabs survive a lifecycle operation.
