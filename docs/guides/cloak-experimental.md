# Experimental CloakBrowser Runtime

This is the first-stage runtime experiment, not a supported engine in the Verge API yet. It reuses the Xvfb image, X11 desktop, CDP relay and noVNC stack. It does not add BrowseForge, Cloak Manager, cloakserve or a Playwright server.

**Validation status:** unit tests and static configuration checks are available. Real Cloak startup, GUI/CDP compatibility, cookie persistence and license-seat release still require the opt-in Docker test below. Do not treat this as production-ready.

## Requirements and licensing

- A Linux amd64 Docker runtime. ARM64 and Xpra are not supported by this experiment; emulation on another host is not an equivalent native validation.
- Your own CloakBrowser key. A [free GitHub key](https://cloakbrowser.dev/free) is enough to try this experiment: sign in with GitHub and receive the key by email, with no payment card required. The free tier provides the latest binary and one concurrent browser session; a paid subscription is not required.
- Access to the official CloakHQ download and license services. A cached binary is not a promise of offline or indefinite access.
- Internal use only under the applicable [CloakBrowser Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md). Downloading/installing the binary accepts its terms. This integration does not grant permission to redistribute it or offer a customer-controlled hosted browser service.

The public Xvfb image contains the fixed MIT wrapper and its Python dependencies, **not the Cloak browser binary**. It does not run `cloakbrowser install` or `playwright install` during image build. Binary downloads happen only in the explicit installation step. Keep the binary volume private; do not publish an image created from an installed container or export its volume for third parties.

## Build and explicitly install

Store your own key in a restricted file outside any browser workspace. Do not paste it into a command, image build argument or Git-tracked file. Set the path on the Docker daemon's host, not a path visible only inside an API container:

```bash
export VERGE_CLOAK_LICENSE_FILE="$(pwd)/.local/secrets/cloak-license"
# Place your key in that file using your normal secret-management process.
chmod 600 "$VERGE_CLOAK_LICENSE_FILE"

docker compose -f deployments/docker-compose.cloak-experimental.yml \
  --profile install build cloak-install

docker compose -f deployments/docker-compose.cloak-experimental.yml \
  --profile install run --rm cloak-install --accept-binary-license
```

Read the linked Binary License before passing the acceptance flag. No key is obtained or purchased by these commands.

The installer uses `cloakbrowser==0.6.4` and its official Ed25519/manifest/version/SHA256 checks. Free keys use the wrapper's latest Stable download without a version pin; paid keys resolve Stable first and request that exact version. The installer records the version actually returned and its signed receipt, retains the original binary directory and license files, and updates `current.json` only after success. It never falls back to the old keyless binary. Download/path/checksum overrides from the wrapper environment are not accepted.

Free keys do not grant arbitrary version selection or rollback. Each explicit installation uses a fresh download cache to get the official latest Stable build. Runtime starts reuse the verified local installation, as with the wrapper's disabled auto-update mode; this is not a promise that an old build remains authorized indefinitely.

By default the internal volume is `verge-browser-cloak-binaries`. Override `VERGE_CLOAK_BINARY_VOLUME` consistently for installation and runtime if needed. Run only one installer at a time. Failed staging directories contain a sanitized `failure.json` with the failing phase and exception type; they do not replace the current installation. Staging cleanup happens before publishing `current.json`, so cleanup failure also leaves the current version unchanged. A fully prepared release may remain after a failed finalization and can be reused on retry. Inspect and remove failed staging data manually when no installation is running.

## Start an isolated desktop

```bash
docker compose -f deployments/docker-compose.cloak-experimental.yml \
  --profile experiment up -d cloak-xvfb
```

- noVNC: `http://127.0.0.1:16080/vnc.html`
- CDP discovery: `http://127.0.0.1:19223/json/version`

These experimental endpoints bypass Verge ticket authentication and are bound to loopback only. Do not expose them publicly. A CDP discovery document may advertise the browser's internal address; use its `/devtools/browser/...` path with the published loopback port `19223` when connecting directly. Normal Verge API access is deliberately not enabled by this Compose file.

The browser uses the installed Linux binary directly, its native Linux persona, the existing open-source fonts, and the real X11 display. The first experiment uses CPU rendering; hardware GPU, authenticated proxies, automatic GeoIP and wrapper humanization are not supported. Changing the binary does not promise to pass any particular site's detection.

Optional settings before the **first** start:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VERGE_CLOAK_LOCALE` | `zh-CN` | Browser and fingerprint locale |
| `VERGE_CLOAK_TIMEZONE` | `UTC` | IANA timezone, saved with the profile |
| `VERGE_CLOAK_CDP_PORT` | `19223` | Host loopback CDP relay port |
| `VERGE_CLOAK_GUI_PORT` | `16080` | Host loopback noVNC port |

The experiment creates separate workspace and runtime-state volumes. It generates a seed once, saves it in both the profile and a private runtime record, and records the installed artifact. Subsequent starts reuse that record, even if the deployment's current installation has changed. Missing or conflicting seed data fails explicitly; it does not rotate the identity. Do not import an existing Chromium profile.

The key is mounted read-only at `/root/.cloakbrowser/license.key`; the parent directory is private writable state, separate from the read-only binary volume. This prevents accidental exposure through the workspace file API, not malicious access by an administrator or a fully privileged browser/container controller. Only trusted internal use is intended.

## Inspect and stop safely

Read structured process and license diagnostics:

```bash
docker compose -f deployments/docker-compose.cloak-experimental.yml exec -T cloak-xvfb \
  /opt/sandbox/cloak-venv/bin/python /opt/sandbox/cloak/cloak_control.py status
```

Known license exits distinguish session limits, invalid keys, license-network failure and configuration problems. A post-CDP-handshake denial is detected from the binary's status file. Cloak automatic restart and startup retries are disabled, so a denied browser is not repeatedly launched. Cloak uses Supervisor `startsecs=0` to retain fast-exit codes; Chromium keeps its original one-second startup threshold. Supervisor `RUNNING` alone is not browser readiness: CDP and license diagnostics must also pass. The desktop container can remain alive for inspection even when its browser has stopped.

`status` uses `process_state` to distinguish a running browser from a stopped one. A clean `EXITED/0` or a normal Supervisor stop is not an error; a nonzero browser exit, failed startup, license denial or launcher failure is. It is a diagnostic command, not a standalone readiness probe.

Before stopping or removing the container, request normal browser closure:

```bash
docker compose -f deployments/docker-compose.cloak-experimental.yml exec -T cloak-xvfb \
  /opt/sandbox/cloak-venv/bin/python /opt/sandbox/cloak/cloak_control.py stop

docker compose -f deployments/docker-compose.cloak-experimental.yml stop --timeout 10 cloak-xvfb
docker compose -f deployments/docker-compose.cloak-experimental.yml rm -f cloak-xvfb
```

The control command sends browser-level `Browser.close`, confirms process exit, and falls back to a bounded Supervisor stop if CDP is unavailable. It reports `graceful=true` only after a zero-code browser exit without a denial or launcher error. Crashes and license failures remain errors even if the process has already stopped, and the command returns a nonzero exit code. A normal fallback Supervisor stop reports `graceful=false` with a warning, rather than a false license error. It **does not claim the official session seat is already released**. If the command fails, preserve the container and inspect it instead of automatically forcing removal.

Starting again reuses the workspace and state volumes. Do not use `down -v` unless you intend to delete the test identity and data. A newer installed build applies to a new profile, not an existing one. If the official service requires a newer build, stop the old browser, rerun the installer and use a new Compose project name for fresh workspace/state volumes, keeping the same binary volume and license file. Preserve the old volumes rather than deleting them. Runtime-image upgrades and profile migration through the control plane are still future work; keep the tested image unchanged while reusing an experimental profile.

## Opt-in integration test

After installation, stop any other browser consuming the same license seat. This test creates its own uniquely named container and test profile, reuses the private binary volume read-only, and never calls the existing managed-container cleanup fixture:

```bash
VERGE_TEST_CLOAK=1 PYTHONPATH=apps/api-server \
  .venv/bin/python -m pytest tests/integration/test_cloak_experimental.py -v -s
```

`VERGE_CLOAK_LICENSE_FILE` must remain set and be visible to the Docker daemon. The default image is `verge-browser-runtime-xvfb:cloak-experimental`; override `VERGE_CLOAK_TEST_IMAGE` if necessary. Use the normal development test configuration, not production API secrets. The test uses its own named workspace/state volumes, so browser-created files do not require host-user read permissions.

The test checks direct CDP, Verge's existing CDP-ticket proxy and screenshot/action routes, noVNC availability, normal browser restart, container recreation, Cookies/LocalStorage/IndexedDB, and unchanged seed/build records. It uses only a local test page. On success it removes only its own container and workspace/state volumes, leaving the installed binary volume intact. On failure it prints the isolated container name and preserves it and its test volumes for diagnosis; close it with the control command and clean them up when done. Manual input/clipboard/GPU and negative-license cases still need separate validation.

Without the explicit test flag, this test skips before accessing Docker or secrets. Do not run `tests/integration/test_runtime_api.py` on a daemon with business sandboxes: its existing cleanup fixture removes all `verge.managed=true` containers.

## Not implemented yet

The public API, Registry, DockerAdapter, lifecycle, SDKs and admin UI do not yet accept or manage `browser_engine`. Passing an unknown engine property to the current API must not be used to select Cloak. Phase two must add typed engine/configuration persistence, secret/volume wiring, readiness and browser-health checks, and graceful lifecycle operations before this becomes a normal Verge sandbox option.
