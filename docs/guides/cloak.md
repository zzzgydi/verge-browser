# CloakBrowser In The Admin Console

Chromium needs no Cloak key. Start the normal Verge API and create Chromium sandboxes from `/admin`. CloakBrowser is an optional engine in the same console, using the same session links, CDP tickets, files and lifecycle API.

**Validation:** the control-plane integration has unit tests. Real Cloak download, startup, GUI/CDP and license-seat behavior still require verification with your key. Start with a disposable profile, not production data.

## Enable CloakBrowser

This integration supports Linux amd64, Xvfb/noVNC and CPU rendering. A [free GitHub key](https://cloakbrowser.dev/free) works; it allows one running browser at a time. Xpra, GPU and authenticated proxies are not supported for Cloak yet. Ordinary Chromium retains both desktop runtimes.

Read the [official Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md). The public image contains only the MIT wrapper, not the proprietary browser. The explicit installation step downloads the binary from official channels into a private volume for your internal use. Neither a free key nor a Pro subscription grants third-party hosted-browser or redistribution rights.

From the repository root on the Docker host:

```bash
export PROJECT_ROOT="$PWD"
export COMPOSE_PROJECT_NAME=verge-browser
export VERGE_CLOAK_LICENSE_FILE="$HOME/.config/verge-browser/cloak-license"
# Write your key to this file using your normal secret-management process.
chmod 600 "$VERGE_CLOAK_LICENSE_FILE"

docker compose -f deployments/docker-compose.yml build api runtime-xvfb

docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.cloak.yml \
  --profile install run --rm cloak-install --accept-binary-license

docker compose -f deployments/docker-compose.yml -f deployments/docker-compose.cloak.yml \
  up -d api
```

Keep your existing project name and deployment overrides when adding this overlay to an existing service. The API must see the key at the same absolute path as the Docker host, and its read-only binary mount must refer to the same `VERGE_CLOAK_BINARY_VOLUME` used by the installer. Do not put keys in requests, browser workspaces or Git. Configure non-default admin/ticket secrets before exposing the API; see [Linux deployment](headless-linux.md).

Refresh `/admin`. The browser selector enables **CloakBrowser** once the server has its key, installed binary and runtime image. It does not claim to validate your license or count free seats; the actual browser enforces the official entitlement. Pause another Cloak sandbox before starting one with the same free key.

The normal deployment works without this overlay or any Cloak variables. The older `docker-compose.cloak-experimental.yml` remains a low-level diagnostic fixture, not the console deployment path.

## API And CLI

`GET /runtime/engines` (admin authentication required) reports engine availability without returning keys. Create a sandbox through the existing API:

```json
{"alias":"cloak-demo","kind":"xvfb_vnc","browser_engine":"cloakbrowser"}
```

The default `browser_engine` is `chromium`, including records saved by older versions. Engine selection is immutable for a sandbox; create a separate sandbox rather than reusing a Chromium profile. Use `--browser-engine cloakbrowser` with either CLI, or `browser_engine="cloakbrowser"` in the Python SDK / `browser_engine: "cloakbrowser"` in the Node SDK.

Sandbox responses report the engine. License denials and stopped browser processes appear in `metadata.runtime_error`, rather than leaving a healthy-looking desktop container marked RUNNING. Session and CDP access still use the normal authenticated ticket endpoints; there are no separate public Cloak ports.

## Pause, Restart And Updates

Pause, delete and browser restart request `Browser.close` through the runtime controller, with a bounded Supervisor fallback. If the controller cannot confirm the browser stopped, the operation fails and preserves the container/profile. An already exited browser can be removed or restarted even if its last exit was a license denial. A confirmed stop does not guarantee the official seat is already released; follow the reported denial and retry after the service releases the seat.

Each sandbox stores its seed and selected build in private state beside, not inside, its workspace. Pausing or restarting the API preserves that state. Reinstalling a newer official build changes the default for new sandboxes only. If an old build is no longer authorized, install the current build and create a new sandbox; this integration does not migrate profiles or promise indefinite access to old binaries.

Optional server settings are `VERGE_CLOAK_RUNTIME_IMAGE`, `VERGE_CLOAK_BINARY_VOLUME`, `VERGE_CLOAK_LOCALE` and `VERGE_CLOAK_TIMEZONE`. Do not change the binary volume or runtime-image configuration while resuming existing Cloak profiles. The initial locale/timezone is stored with each profile.

## Verify The Managed Integration

With the API configured and a free browser seat available, set `VERGE_BROWSER_URL` and `VERGE_BROWSER_TOKEN` in your shell, then run:

```bash
VERGE_TEST_CLOAK_MANAGED=1 PYTHONPATH=apps/api-server \
  pytest tests/integration/test_cloak_managed.py
```

This opt-in test creates its own sandbox through the API and checks screenshots, ticketed CDP/noVNC, pause/resume, browser restart, seed and localStorage persistence. It deletes only its own sandbox on success and preserves it on failure. Do not run `test_runtime_api.py` against a Docker daemon containing sandboxes you want to keep; its older fixture removes all managed containers.
