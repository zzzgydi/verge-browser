# Experimental CloakBrowser Runtime

For normal use, follow [CloakBrowser in the admin console](cloak.md).
This guide covers the standalone diagnostic fixture. It reuses the Xvfb image, X11 desktop, CDP relay, and noVNC stack.
It does not add BrowseForge, Cloak Manager, cloakserve, or a Playwright server.

**Validation status:** unit tests and static configuration checks are available.
Real Cloak startup, GUI/CDP compatibility, cookie persistence, and license-seat release still require the opt-in Docker test.
Do not treat this fixture as production-ready.

## Requirements and licensing

- A Linux amd64 Docker runtime. This fixture does not support ARM64 or Xpra. Emulation is not equivalent to native validation.
- Your own CloakBrowser key. A [free GitHub key](https://cloakbrowser.dev/free) permits the latest binary and one concurrent browser session. Sign in with GitHub to receive the key by email. No payment card or paid subscription is required.
- Access to the official CloakHQ download and license services. A cached binary is not a promise of offline or indefinite access.
- Internal use under the [CloakBrowser Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md). Downloading or installing the binary accepts its terms. This integration does not grant redistribution rights or permission for a customer-controlled hosted browser service.

The public Xvfb image contains the pinned MIT wrapper and Python dependencies. It does **not** contain the Cloak browser binary.
The image build does not run `cloakbrowser install` or `playwright install`. Binary downloads occur only during explicit installation.

Keep the binary volume private. Do not publish an image made from an installed container or export its volume to third parties.

## Build and explicitly install

Store your key in a restricted file outside browser workspaces.
Do not put it in a command, image build argument, or Git-tracked file.
Use a path on the Docker daemon's host, not an API-container-only path.

Read the Binary License before running the installation command with `--accept-binary-license`.
The commands do not obtain or purchase a key:

```bash
export VERGE_CLOAK_LICENSE_FILE="$(pwd)/.local/secrets/cloak-license"
# Place your key in that file using your normal secret-management process.
chmod 600 "$VERGE_CLOAK_LICENSE_FILE"

docker compose -f deployments/docker-compose.cloak-experimental.yml \
  --profile install build cloak-install

docker compose -f deployments/docker-compose.cloak-experimental.yml \
  --profile install run --rm cloak-install --accept-binary-license
```

The installer uses `cloakbrowser==0.6.4` and its official Ed25519, manifest, version, and SHA256 checks.

| Key type | Download selection |
| --- | --- |
| Free | Wrapper's latest Stable build, without a version pin. |
| Paid | Resolve Stable first, then request that exact version. |

The installer records the returned version and signed receipt. It retains the original binary directory and license files.
It updates `current.json` only after success. It never uses the old keyless binary as a fallback.
The installer rejects wrapper-environment overrides for downloads, paths, and checksums.

Free keys do not grant arbitrary version selection or rollback.
Each explicit installation uses a fresh cache to download the official latest Stable build.
Runtime starts reuse the verified local installation, like the wrapper's disabled auto-update mode.
This does not guarantee indefinite authorization for an old build.

The default internal volume is `verge-browser-cloak-binaries`.
If you override `VERGE_CLOAK_BINARY_VOLUME`, use the same value for installation and runtime.
Run only one installer at a time.

Failed staging directories contain a sanitized `failure.json` with the failing phase and exception type.
They do not replace the current installation. Staging cleanup occurs before publication of `current.json`.
A cleanup failure leaves the current version unchanged.

A failed finalization can leave a fully prepared release for reuse on retry.
When no installation is running, inspect and remove failed staging data manually.

## Start an isolated desktop

Keep the experimental ports on loopback. These endpoints bypass Verge ticket authentication.
Do not expose them publicly.

```bash
docker compose -f deployments/docker-compose.cloak-experimental.yml \
  --profile experiment up -d cloak-xvfb
```

- noVNC: `http://127.0.0.1:16080/vnc.html`
- CDP discovery: `http://127.0.0.1:19223/json/version`

The CDP discovery document can contain the browser's internal address.
For a direct connection, use its `/devtools/browser/...` path with the published loopback port `19223`.
This Compose file does not enable normal Verge API access.

The browser uses the installed Linux binary, its native Linux persona, existing open-source fonts, and the real X11 display.
This fixture uses CPU rendering.

Unsupported features:

- Hardware GPU rendering.
- Authenticated proxies.
- Automatic GeoIP.
- Wrapper humanization.

Changing the binary does not guarantee that a website will accept the browser.

Optional settings before the **first** start:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERGE_CLOAK_LOCALE` | `zh-CN` | Browser and fingerprint locale |
| `VERGE_CLOAK_TIMEZONE` | `UTC` | IANA timezone, saved with the profile |
| `VERGE_CLOAK_CDP_PORT` | `19223` | Host loopback CDP relay port |
| `VERGE_CLOAK_GUI_PORT` | `16080` | Host loopback noVNC port |

The fixture creates separate workspace and runtime-state volumes.
It generates a seed once and saves it in the profile and a private runtime record.
It also records the installed artifact. Later starts reuse that record, even after the current installation changes.

Missing or conflicting seed data causes an explicit failure. The fixture does not rotate the identity.
Do not import an existing Chromium profile.

The key mounts read-only at `/root/.cloakbrowser/license.key`.
The parent directory is private writable state, separate from the read-only binary volume.
This prevents accidental exposure through the workspace file API.
It does not prevent access by an administrator or a fully privileged browser/container controller.
Use this fixture only in a trusted internal environment.

## Inspect and stop safely

Read structured process and license diagnostics:

```bash
docker compose -f deployments/docker-compose.cloak-experimental.yml exec -T cloak-xvfb \
  /opt/sandbox/cloak-venv/bin/python /opt/sandbox/cloak/cloak_control.py status
```

License diagnostics distinguish session limits, invalid keys, license-network failures, and configuration problems.
The controller reads post-CDP-handshake denials from the binary's status file.
Cloak automatic restart and startup retries are disabled. A denied browser does not launch repeatedly.

Cloak uses Supervisor `startsecs=0` to retain fast-exit codes. Chromium keeps its one-second startup threshold.
Supervisor `RUNNING` does not prove browser readiness. CDP and license diagnostics must also pass.
The desktop container can remain alive for inspection after the browser stops.

`status` reports `process_state` to distinguish running and stopped browsers.
A clean `EXITED/0` or normal Supervisor stop is not an error.
A nonzero browser exit, failed startup, license denial, or launcher failure is an error.
Use `status` for diagnostics, not as a standalone readiness probe.

Before container removal, request normal browser closure with the control command.
If it fails, stop here. Preserve the container for inspection instead of running the subsequent stop and removal commands:

```bash
docker compose -f deployments/docker-compose.cloak-experimental.yml exec -T cloak-xvfb \
  /opt/sandbox/cloak-venv/bin/python /opt/sandbox/cloak/cloak_control.py stop

docker compose -f deployments/docker-compose.cloak-experimental.yml stop --timeout 10 cloak-xvfb
docker compose -f deployments/docker-compose.cloak-experimental.yml rm -f cloak-xvfb
```

The control command sends browser-level `Browser.close` and checks process exit.
If CDP is unavailable, it uses a bounded Supervisor stop.

| Result | Meaning |
| --- | --- |
| `graceful=true` | Zero-code browser exit, without a denial or launcher error. |
| `graceful=false` with a warning | Normal fallback Supervisor stop. This is not a license error. |
| Nonzero command exit | Crash, license failure, or another stop error. An already-stopped process does not erase the error. |

Successful closure **does not prove that the official license seat is free**.

Starting again reuses the workspace and state volumes.
Do not use `down -v` unless you intend to delete the test identity and data.
A newer installed build applies to new profiles, not existing ones.

If the official service requires a newer build:

1. Stop the old browser.
2. Run the installer again.
3. Select a new Compose project name for fresh workspace and state volumes.
4. Keep the same binary volume and license file.
5. Preserve the old workspace and state volumes.

This standalone fixture does not provide runtime-image upgrades or control-plane profile migration.
Keep the tested image unchanged while reusing an experimental profile.

## Opt-in integration test

After installation, stop any browser using the same license seat.
The test creates its own uniquely named container and profile. It mounts the private binary volume read-only.
It does not call the managed-container cleanup fixture:

```bash
VERGE_TEST_CLOAK=1 PYTHONPATH=apps/api-server \
  .venv/bin/python -m pytest tests/integration/test_cloak_experimental.py -v -s
```

`VERGE_CLOAK_LICENSE_FILE` must remain set. The Docker daemon must be able to read that path.
The default image is `verge-browser-runtime-xvfb:cloak-experimental`. To use another image, set `VERGE_CLOAK_TEST_IMAGE`.

Use the development test configuration, not production API secrets.
The test uses its own named workspace and state volumes. Browser-created files do not require host-user read permissions.

The test uses only a local page. It checks:

- Direct CDP and Verge's ticketed CDP proxy.
- Screenshot/action routes and noVNC availability.
- Browser restart and container recreation.
- Cookies, LocalStorage, and IndexedDB.
- Unchanged seed and build records.

On success, it removes only its own container and workspace/state volumes. The installed binary volume remains intact.
On failure, it prints the container name and preserves the container and test volumes for diagnosis.
After inspection, close the browser with the control command. Then remove the test container and volumes.

Manual input, clipboard, GPU, and negative-license cases require separate validation.

Without the explicit test flag, the test skips before accessing Docker or secrets.
Do not run `tests/integration/test_runtime_api.py` on a daemon with business sandboxes.
Its cleanup fixture removes all `verge.managed=true` containers.

## Console integration

The API, Registry, DockerAdapter, lifecycle, SDKs, and admin UI accept `browser_engine`.
To create Cloak sandboxes from the console, use the [normal API overlay](cloak.md), not this standalone fixture.
The managed Xpra adapter is experimental. ARM64, GPU, profile migration, and real licensed-runtime acceptance remain outside this fixture's verified scope.
