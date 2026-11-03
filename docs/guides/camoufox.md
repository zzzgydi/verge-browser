# Camoufox (experimental)

Camoufox is an optional Firefox-based engine in Verge sandboxes.
The worker embeds the upstream **Python** `camoufox-cli` commands, element references (refs), and identity implementation.
It is not a standalone CLI or an `agent-browser` fork.

Both Verge CLIs call the authenticated command API.
Chromium and CloakBrowser continue to use `agent-browser` with ticketed CDP.

The initial adapter targets **Linux ARM64, Xvfb/noVNC, and CPU rendering**. It uses a persistent browser context with a graphical interface.

Unsupported features:

- Xpra and GPU rendering.
- Proxies.
- Stock Firefox.
- CDP or BiDi access.

Other architectures require separate acceptance tests, even if the runtime builds successfully.
Acceptance tests do not guarantee anti-detection effectiveness.

## Local setup

Until a release includes these changes, use a matching source checkout for the API and CLI.
Build the optional image on the Docker host:

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-camoufox.Dockerfile -t verge-browser-runtime-camoufox:local .
```

The image pins these packages:

- `camoufox-cli==0.7.6`.
- `camoufox==0.4.11`.
- `playwright==1.52.0`.
- Resolved dependencies in `docker/camoufox-requirements.txt`.

Do not upgrade one component independently. The image does not use the npm package.
It contains no browser binary or downloaded fonts.

Review the browser terms before obtaining the official archive **separately**.
The locally tested ARM64 artifact is:

- Release: [Camoufox v156.0.1-beta.36](https://github.com/daijro/camoufox/releases/tag/v156.0.1-beta.36).
- Asset: `camoufox-156.0.1-beta.36-lin.arm64.zip`.
- Size: 1,284,863,246 bytes.
- SHA-256:

```text
8b5fd083721c807ee2a752265683482477105052fa0e21739388b527ae067c15
```

Run the following commands from the repository root.
Allow space for the compressed archive, about 1.2 GiB, and the extracted files.
Before `unzip`, compare the reported SHA-256 with the value above. Stop if they differ; the shell example does not compare them automatically.

```bash
mkdir -p .local/camoufox/binary
curl -fL -o .local/camoufox/browser.zip \
  https://github.com/daijro/camoufox/releases/download/v156.0.1-beta.36/camoufox-156.0.1-beta.36-lin.arm64.zip
# Compare this output exactly with the SHA-256 above before extracting.
shasum -a 256 .local/camoufox/browser.zip
unzip -q .local/camoufox/browser.zip -d .local/camoufox/binary
printf '%s\n' '{"version":"156.0.1","release":"beta.36"}' > .local/camoufox/binary/version.json
export VERGE_CAMOUFOX_ENABLED=true
export VERGE_CAMOUFOX_BINARY_DIR="$PWD/.local/camoufox/binary"
export VERGE_CAMOUFOX_RUNTIME_IMAGE=verge-browser-runtime-camoufox:local
```

Start the API with those settings and your existing authentication secrets.
`VERGE_CAMOUFOX_BINARY_DIR` must be an absolute Docker-host path. It must contain the complete extracted browser with executable permissions.
The API must see that directory at the **same path**. The sandbox mounts it read-only at `/root/.cache/camoufox`.

For standard Compose deployments:

1. Keep the binary directory below `PROJECT_ROOT`.
2. Add the three variables to the API environment or its working directory's `.env`.

Do not expose new debug ports. The managed worker disables:

- GeoIP lookups.
- Default addon downloads.
- Native daemon idle shutdown.
- Automatic browser recovery.

`GET /runtime/engines` reports `browser_engine: camoufox` and `automation: commands`.
It also reports configuration availability. This is not a runtime readiness check.
Sandbox creation checks the worker, display, and session server. A running container alone does not prove browser readiness.

## Operate the existing sandbox

Wait for `RUNNING` before issuing browser commands. Pause ends the live browser session; save work before running it.

```bash
verge-browser sandbox create --alias fox --browser-engine camoufox --default-url https://example.com --json
verge-browser sandbox get fox --json
verge-browser browser snapshot fox -i --json
verge-browser browser open fox https://example.org --json
verge-browser browser screenshot fox --type page --format png --output ./fox.png --json
verge-browser sandbox session fox --json
verge-browser sandbox pause fox --json
verge-browser sandbox resume fox --json
```

See the [usage skill](../../skills/verge-browser-usage/SKILL.md) for engine routing.
See [Camoufox commands](../../skills/verge-browser-usage/references/camoufox.md) for refs, tabs, uploads, and GUI handoff.
`sandbox cdp fox` intentionally returns 409.

Commands do not start a local browser as a fallback. They do not automatically restart the worker or retry a mutating operation.

The profile and `camoufox-cli.json` identity use `/workspace/browser-profile`.
Pause/resume and explicit browser restart preserve both. Delete removes both.

Stop waits for the browser context to close before container removal.
If the API cannot confirm closure, it fails and preserves the container and profile for inspection.
An already-exited worker or browser can be explicitly restarted or removed.

Do not replace the mounted browser while profiles are active. For an upgrade:

1. Stop the browser.
2. Back up the profile.
3. Test the new build in a separate sandbox.

## Acceptance tests

```bash
PYTHONPATH=apps/api-server .venv/bin/pytest tests/unit
pnpm --dir packages/node test
pnpm --dir apps/admin-web test
VERGE_CAMOUFOX_BINARY_DIR="$PWD/.local/camoufox/binary" \
  PYTHONPATH=apps/api-server .venv/bin/pytest tests/integration/test_camoufox_runtime.py
```

The runtime smoke test serves a local fixture. It covers:

- Both Verge CLIs, trusted native clicks, stale-ref errors, and tabs.
- X11 clipboard input and noVNC entry.
- Uploads, downloads, and PNG pixels.
- Profile and identity persistence through lifecycle operations.

The test uses a distinct Docker label. It deletes only its own sandbox.
Set `VERGE_SMOKE_ARTIFACT_DIR` to retain screenshots and result metadata.

The fixture uses `host.docker.internal` on Docker Desktop or OrbStack.
On Linux, resolve that name to the host gateway for this fixture.
If the host uses an HTTP proxy, add runtime addresses to `NO_PROXY`.
A proxy response of 502 is not a browser failure.
On OrbStack, this test supports `VERGE_TEST_RUNTIME_HOST_TEMPLATE='{name}.orb.local'`.

## License boundary

- The [Camoufox browser](https://github.com/daijro/camoufox) uses MPL-2.0, not only MIT. Browser modifications and distribution obligations remain separate from Verge's original MIT code.
- The Python Camoufox wrapper and [Python camoufox-cli](https://github.com/Bin-Huang/camoufox-cli) use MIT. Preserve their notices and installed dependency licenses. The reviewed 0.7.6 CLI revision is `2b1e24b6b6081549df8ed050502492cfb735acf2`.
- Browser artifacts include LGPL-covered Cursory and font bundles with separate terms. This implementation does **not** establish font redistribution rights. GeoIP database and addon downloads are disabled.
- This integration supports a separately obtained, locally mounted browser. It does **not** authorize browser-containing images or commercial redistribution.
- Before distribution, review the exact artifact's notices, corresponding-source obligations, and font terms. Distribution-package obligations also apply to a runtime without a browser binary. Do not call the entire image MIT.

These are engineering boundaries, not a legal opinion.
Public images with a bundled browser require license review before release. This does not mean that MPL prevents the local integration.

## Recorded validation

To test the upstream 30-minute idle boundary, add `VERGE_TEST_CAMOUFOX_IDLE_SEC=1810`.
The test sends no keepalive requests during that interval. It then checks the browser PID and a real GUI click.

To test Chromium routing with the same fixture, set `VERGE_TEST_AGENT_BROWSER` to your installed executable.
The test gets a Verge ticket through the Python CLI. It then runs snapshot, fill, and native-click actions through `agent-browser --cdp`.

Local acceptance record for 2026-10-30:

| Check | Result and scope |
| --- | --- |
| Runtime environment | Linux ARM64 under OrbStack. |
| Camoufox and Chromium smoke tests | Both passed. |
| Camoufox idle interval | 1,810 seconds without worker requests or keepalives. Browser PID stayed unchanged. |
| Xvfb/Xpra regressions and unit tests | 260 passed. |
| Node CLI tests | 17 passed. |
| Admin UI tests | 26 passed. |
| Chromium routing | Used the ARM64 native binary of agent-browser 0.41.0. Its npm Node wrapper requires Node >=24. |
| Outside this run | Real licensed Cloak binary and other Camoufox architectures. |
