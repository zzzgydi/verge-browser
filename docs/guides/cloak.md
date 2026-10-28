# CloakBrowser In The Admin Console

Chromium needs no Cloak key. Start the normal Verge API and create Chromium sandboxes from `/admin`. CloakBrowser is an optional engine in the same console, using the same session links, CDP tickets, files and lifecycle API.

**Validation:** the control-plane integration has unit tests. The Xpra adapter is experimental and still needs real Cloak GUI/CDP and license-seat acceptance. Verify your selected runtime with your key and a disposable profile, not production data.

## Enable CloakBrowser

The adapters target Linux amd64 with CPU rendering, using either Xvfb/noVNC or Xpra/HTML5. A [free GitHub key](https://cloakbrowser.dev/free) works; it allows one running browser at a time across both runtimes. GPU and authenticated proxies are not supported for Cloak yet. Ordinary Chromium retains both desktop runtimes.

Read the [official Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md). The public image contains only the MIT wrapper, not the proprietary browser. The explicit installation step downloads the binary from official channels into a private volume for your internal use. Neither a free key nor a Pro subscription grants third-party hosted-browser or redistribution rights.

From the repository root on the Docker host:

```bash
export PROJECT_ROOT="$PWD"
export COMPOSE_PROJECT_NAME=verge-browser
export VERGE_CLOAK_LICENSE_FILE="$HOME/.config/verge-browser/cloak-license"
# Write your key to this file using your normal secret-management process.
chmod 600 "$VERGE_CLOAK_LICENSE_FILE"

docker compose -f deployments/docker-compose.yml build api runtime-xvfb runtime-xpra

docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.cloak.yml \
  --profile install run --rm cloak-install --accept-binary-license

docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.cloak.yml \
  up -d api
```

Keep your existing project name and deployment overrides when adding this overlay to an existing service. The API must see the key at the same absolute path as the Docker host, and its read-only binary mount must refer to the same `VERGE_CLOAK_BINARY_VOLUME` used by the installer. Do not put keys in requests, browser workspaces or Git. Configure non-default admin/ticket secrets before exposing the API; see [Linux deployment](headless-linux.md).

Refresh `/admin`. The browser selector enables **CloakBrowser** once the server has its key, installed binary and runtime image. It does not claim to validate your license or count free seats; the actual browser enforces the official entitlement. Pause another Cloak sandbox before starting one with the same free key.

The normal deployment works without this overlay or any Cloak variables. The older `docker-compose.cloak-experimental.yml` remains a low-level diagnostic fixture, not the console deployment path.

## API And CLI

`GET /runtime/engines` (admin authentication required) reports engine availability without returning keys. Its `kinds` list contains the runtimes whose configured image declares the supported Cloak launcher; a missing or unsupported Xpra image does not disable Xvfb and vice versa. Images must have `io.verge.browser.launcher-version="1"` and include `cloakbrowser-linux-amd64` in `io.verge.browser.experimental-engines`. Old images without these labels are rejected before creating a profile: rebuild the image when upgrading, rather than relabeling an old image. This is a launcher compatibility check, not proof of a working license or compatible binary. Create a sandbox through the existing API:

```json
{"alias":"cloak-demo","kind":"xvfb_vnc","browser_engine":"cloakbrowser"}
```

For the experimental Xpra adapter, select **CloakBrowser** and **xpra** in the console, or use:

```json
{"alias":"cloak-xpra","kind":"xpra","browser_engine":"cloakbrowser"}
```

Both CLIs accept `--kind xpra --browser-engine cloakbrowser`. Xpra creation can return `STARTING`; wait for `RUNNING` before opening the session. Pause an existing Cloak sandbox first if your key allows only one running browser. A sandbox's desktop runtime cannot be switched in place.

The default `browser_engine` is `chromium`, including records saved by older versions. Engine selection is immutable for a sandbox; create a separate sandbox rather than reusing a Chromium profile. Use `--browser-engine cloakbrowser` with either CLI, or `browser_engine="cloakbrowser"` in the Python SDK / `browser_engine: "cloakbrowser"` in the Node SDK.

Sandbox responses report the engine. License denials and stopped browser processes appear in `metadata.runtime_error`, rather than leaving a healthy-looking desktop container marked RUNNING. Session and CDP access still use the normal authenticated ticket endpoints; there are no separate public Cloak ports.

## Pause, Restart And Updates

Pause, delete and browser restart request `Browser.close` through the runtime controller, with a bounded Supervisor fallback. If the controller cannot confirm the browser stopped, the operation fails and preserves the container/profile. An already exited browser can be removed or restarted even if its last exit was a license denial. A confirmed stop does not guarantee the official seat is already released; follow the reported denial and retry after the service releases the seat.

Each sandbox stores its seed and selected build in private state beside, not inside, its workspace. Pausing or restarting the API preserves that state. Reinstalling a newer official build changes the default for new sandboxes only. If an old build is no longer authorized, install the current build and create a new sandbox; this integration does not migrate profiles or promise indefinite access to old binaries.

Optional server settings are `VERGE_CLOAK_RUNTIME_IMAGE` (Xvfb and the installer), `VERGE_CLOAK_RUNTIME_IMAGE_XPRA` (Xpra), `VERGE_CLOAK_BINARY_VOLUME`, `VERGE_CLOAK_LOCALE` and `VERGE_CLOAK_TIMEZONE`. Both runtimes share the same private binary volume, not separate downloads. Existing sandboxes retain their selected image name; keep that image and binary volume available when resuming them. The initial locale/timezone is stored with each profile.

## Verify The Managed Integration

With the API configured and a free browser seat available, set `VERGE_BROWSER_URL` and `VERGE_BROWSER_TOKEN` in your shell, then run:

```bash
VERGE_TEST_CLOAK_MANAGED=1 PYTHONPATH=apps/api-server \
  pytest tests/integration/test_cloak_managed.py

# Run separately with a free seat; never run the two checks concurrently.
VERGE_TEST_CLOAK_MANAGED=1 VERGE_TEST_CLOAK_KIND=xpra PYTHONPATH=apps/api-server \
  pytest tests/integration/test_cloak_managed.py
```

This opt-in test creates its own sandbox through the API and checks screenshots, ticketed CDP, session assets/transport, pause/resume, browser restart, seed and localStorage persistence. For Xpra, the WebSocket check verifies transport only, not an HTML5 desktop connection. Complete acceptance by opening an Xpra session in the console, navigating with the keyboard/mouse, checking Chinese input and reconnecting after pause/resume. Confirm that a second sequential Cloak sandbox can obtain the released seat. Xpra's root-window screenshot without an attached HTML5 client is not sufficient evidence of a visible desktop; inspect the connected session and page screenshot too.

The test deletes only its own sandbox on success and preserves it on failure. Do not run `test_runtime_api.py` against a Docker daemon containing sandboxes you want to keep; its older fixture removes all managed containers.
