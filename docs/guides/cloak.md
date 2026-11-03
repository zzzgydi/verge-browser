# CloakBrowser In The Admin Console

Chromium does not require a Cloak key. Start the normal Verge API to create Chromium sandboxes from `/admin`.
CloakBrowser is an optional engine in the same console. It uses the same session links, CDP tickets, file API, and lifecycle API.

**Validation:** unit tests cover the control-plane integration. They do not establish that the licensed browser works.
The experimental Xpra adapter still requires real GUI, CDP, and license-seat acceptance.
Test your selected runtime with your own key and a disposable profile. Do not use production data for acceptance tests.

## Enable CloakBrowser

The adapters target Linux amd64 with CPU rendering. They use Xvfb/noVNC or Xpra/HTML5.
A [free GitHub key](https://cloakbrowser.dev/free) permits one running browser across both runtimes.
Cloak does not support GPU rendering or authenticated proxies here. Chromium retains both desktop runtimes.

Read the [official Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md) before installation.
The public image contains the MIT wrapper, not the proprietary browser.
The explicit installation step downloads the official binary into a private volume for internal use.
Neither a free key nor a Pro subscription grants third-party hosted-browser or redistribution rights.

Configure non-default admin and ticket secrets before exposing the API. See [Linux deployment](headless-linux.md).
The stock Compose port binding exposes port 8000 beyond loopback.

Run these commands from the repository root on the Docker host:

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

For an existing service, keep its project name and deployment overrides when adding the overlay.
The API and Docker host must see the key at the same absolute path.
The API's read-only binary mount must use the installer's `VERGE_CLOAK_BINARY_VOLUME`.
Do not put keys in requests, browser workspaces, or Git.

Refresh `/admin`. The selector enables **CloakBrowser** when the server has the key, installed binary, and runtime image.
The selector does not validate the license or count free seats. The browser enforces the official license entitlement.
Before starting a browser with a free key, pause any other Cloak sandbox using that key.

The normal deployment works without this overlay or any Cloak variables. The older `docker-compose.cloak-experimental.yml` remains a low-level diagnostic fixture, not the console deployment path.

## API And CLI

`GET /runtime/engines` requires admin authentication. It reports engine availability without returning keys.
Its `kinds` list contains runtimes whose configured images declare a supported Cloak launcher.
The API checks each runtime independently. A missing Xpra image does not disable Xvfb, and a missing Xvfb image does not disable Xpra.

Images must declare both labels:

- `io.verge.browser.launcher-version="1"`.
- `io.verge.browser.experimental-engines` containing `cloakbrowser-linux-amd64`.

The API rejects images without these labels before creating a profile.
Rebuild images when upgrading. Do not relabel an old image as compatible.
These checks do not prove that the license or binary works.

Create a sandbox through the existing API:

```json
{"alias":"cloak-demo","kind":"xvfb_vnc","browser_engine":"cloakbrowser"}
```

For the experimental Xpra adapter, select **CloakBrowser** and **xpra** in the console, or use:

```json
{"alias":"cloak-xpra","kind":"xpra","browser_engine":"cloakbrowser"}
```

Both CLIs accept `--kind xpra --browser-engine cloakbrowser`.
If creation returns `STARTING`, wait for `RUNNING` before opening the session.
If your key permits only one running browser, pause the existing Cloak sandbox first.
A sandbox's runtime kind cannot change in place.

The default `browser_engine` is `chromium`, including records from older versions.
A sandbox's engine cannot change. Create a separate sandbox instead of reusing a Chromium profile.

Select Cloak with:

- CLI: `--browser-engine cloakbrowser`.
- Python SDK: `browser_engine="cloakbrowser"`.
- Node SDK: `browser_engine: "cloakbrowser"`.

Sandbox responses report the engine. License denials and stopped browser processes appear in `metadata.runtime_error`.
A desktop container alone does not establish `RUNNING` browser status.
Session and CDP access use the normal authenticated ticket endpoints. There are no separate public Cloak ports.

## Pause, Restart And Updates

Pause, delete, and browser restart request `Browser.close` through the runtime controller.
The controller has a bounded Supervisor fallback.
If it cannot confirm that the browser stopped, the operation fails. The container and profile remain available for inspection.

An already-exited browser can be removed or restarted, including after a license denial.
A confirmed stop does not prove that the official license seat is free.
If the service reports a denial, follow that diagnostic. Retry after the service releases the seat.

Each sandbox stores its seed and selected build in private state outside the workspace.
Sandbox pause and API restart preserve that state. Installing a newer official build changes the default only for new sandboxes.

If an old build loses authorization:

1. Install the current build.
2. Create a new sandbox.

This integration does not migrate profiles or guarantee indefinite access to old binaries.

Optional server settings:

| Setting | Purpose |
| --- | --- |
| `VERGE_CLOAK_RUNTIME_IMAGE` | Xvfb runtime and installer image. |
| `VERGE_CLOAK_RUNTIME_IMAGE_XPRA` | Xpra runtime image. |
| `VERGE_CLOAK_BINARY_VOLUME` | Shared private binary volume. |
| `VERGE_CLOAK_LOCALE` | Initial locale, stored with each profile. |
| `VERGE_CLOAK_TIMEZONE` | Initial timezone, stored with each profile. |

Both runtimes share one private binary volume. They do not require separate downloads.
Existing sandboxes retain their selected image name. Keep that image and binary volume available for resume.

## Verify The Managed Integration

Configure the API before running this test. Set `VERGE_BROWSER_URL` and `VERGE_BROWSER_TOKEN` in your shell.
Confirm that a browser license seat is free. Run the checks separately:

```bash
VERGE_TEST_CLOAK_MANAGED=1 PYTHONPATH=apps/api-server \
  pytest tests/integration/test_cloak_managed.py

# Run separately with a free seat; never run the two checks concurrently.
VERGE_TEST_CLOAK_MANAGED=1 VERGE_TEST_CLOAK_KIND=xpra PYTHONPATH=apps/api-server \
  pytest tests/integration/test_cloak_managed.py
```

This opt-in test creates its own sandbox through the API. It checks:

- Screenshots and ticketed CDP.
- Session assets and transport.
- Pause/resume and browser restart.
- Seed and localStorage persistence.

For Xpra, the WebSocket check verifies transport only. It does not verify an HTML5 desktop connection.
Complete manual acceptance:

1. Open an Xpra session in the console.
2. Navigate with the keyboard and mouse.
3. Test Chinese input.
4. Reconnect after pause/resume.
5. Inspect the connected desktop and page screenshot.
6. Stop the first Cloak sandbox.
7. Confirm that a second sandbox can use the released seat.

An Xpra root-window screenshot without an HTML5 client does not prove that the desktop is visible.

On success, the test deletes only its own sandbox. On failure, it preserves that sandbox for inspection.
Do not run `test_runtime_api.py` on a Docker daemon with sandboxes you want to keep.
Its older fixture removes all managed containers.
