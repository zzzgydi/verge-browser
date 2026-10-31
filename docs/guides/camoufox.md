# Camoufox (experimental)

Camoufox is an optional Firefox-based engine in the existing Verge sandbox. The worker embeds the upstream **Python** `camoufox-cli` command/ref and identity implementation; it is not a new standalone CLI or a fork of `agent-browser`. Both Verge CLIs call the authenticated command API. Chromium and CloakBrowser continue using ticketed CDP with `agent-browser`.

The initial adapter targets **Linux ARM64, Xvfb/noVNC, CPU rendering**, with a persistent headed context. Xpra, GPU, proxies, stock Firefox and CDP/BiDi access are not supported. The runtime can be built for other architectures, but they require their own acceptance tests. Anti-detection effectiveness is not an acceptance guarantee.

## Local setup

Use a matching source checkout for the API and CLI until a release includes these changes. Build the optional image on the Docker host:

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-camoufox.Dockerfile -t verge-browser-runtime-camoufox:local .
```

The image pins `camoufox-cli==0.7.6`, `camoufox==0.4.11` and `playwright==1.52.0`, plus the resolved Python dependencies in `docker/camoufox-requirements.txt`. Do not independently upgrade one component. The npm package is not used. No browser binary or downloaded fonts are bundled into this image.

Obtain the official browser archive **separately**, after reviewing its terms. The locally tested ARM64 tuple is [Camoufox v156.0.1-beta.36](https://github.com/daijro/camoufox/releases/tag/v156.0.1-beta.36), asset `camoufox-156.0.1-beta.36-lin.arm64.zip` (1,284,863,246 bytes), SHA-256:

```text
8b5fd083721c807ee2a752265683482477105052fa0e21739388b527ae067c15
```

Example from the repository root (about 1.2 GiB compressed; allow additional extraction space):

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

Start the API with those settings and your existing auth secrets. `VERGE_CAMOUFOX_BINARY_DIR` must be an absolute Docker-host path containing the complete extracted browser, including executable permissions. The API must see the directory at the **same path** as the Docker host. The sandbox mounts it read-only at `/root/.cache/camoufox`. For Compose with the standard `PROJECT_ROOT` bind mount, keep it below that root and add the three variables to the API environment (or its `.env` in the configured working directory). Do not expose new debug ports. GeoIP lookups, default addon downloads, native daemon idle shutdown and automatic browser recovery are disabled in the managed worker.

`GET /runtime/engines` reports `browser_engine: camoufox`, `automation: commands` and whether configuration is available. Availability is a configuration check; creation still verifies the actual worker, display and session server. A running container alone is not a ready browser.

## Operate the existing sandbox

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

See [the usage skill](../../skills/verge-browser-usage/SKILL.md) for routing and [Camoufox commands](../../skills/verge-browser-usage/references/camoufox.md) for refs, tabs, upload and GUI handoff. `sandbox cdp fox` intentionally returns 409. Commands never fall back to a local browser, automatically restart the worker, or retry a mutating operation.

The profile and `camoufox-cli.json` identity live together under `/workspace/browser-profile`. Pause/resume and explicit browser restart preserve both; delete removes both. Stop waits for the context to close before container removal. If that cannot be confirmed, the API fails and leaves the container/profile for inspection. An already-exited worker/browser can be explicitly restarted or removed. Avoid replacing the mounted browser beneath active profiles; stop first, back up the profile and test a separate sandbox when upgrading.

## Acceptance tests

```bash
PYTHONPATH=apps/api-server .venv/bin/pytest tests/unit
pnpm --dir packages/node test
pnpm --dir apps/admin-web test
VERGE_CAMOUFOX_BINARY_DIR="$PWD/.local/camoufox/binary" \
  PYTHONPATH=apps/api-server .venv/bin/pytest tests/integration/test_camoufox_runtime.py
```

The real smoke serves a local fixture and exercises both Verge CLIs, native trusted clicks, stale-ref errors, tabs, X11 clipboard input, noVNC entry, upload/download, PNG pixels, profile/identity persistence and lifecycle. It uses a distinct Docker label and deletes only its own sandbox. Set `VERGE_SMOKE_ARTIFACT_DIR` to retain screenshots and result metadata. The fixture uses `host.docker.internal` (Docker Desktop/OrbStack); Linux hosts must resolve that name to the host gateway for this fixture. On hosts with system HTTP proxies, add the runtime addresses to `NO_PROXY`; a proxy returning 502 is not a browser failure. OrbStack may use `VERGE_TEST_RUNTIME_HOST_TEMPLATE='{name}.orb.local'` in this test only.

## License boundary

- [Camoufox browser](https://github.com/daijro/camoufox) is MPL-2.0, not wholly MIT. Its browser modifications and distribution obligations remain separate from Verge's original MIT code.
- The Python Camoufox wrapper and [Python camoufox-cli](https://github.com/Bin-Huang/camoufox-cli) are MIT. Preserve their notices and the licenses of installed Python dependencies. The upstream CLI revision reviewed for 0.7.6 is `2b1e24b6b6081549df8ed050502492cfb735acf2`.
- Browser artifacts include other components, including LGPL-covered Cursory and font bundles with separate terms. Font redistribution rights have **not** been cleared by this implementation. GeoIP database/addon downloads are not enabled.
- This integration supports a separately obtained, locally mounted browser. It does **not** authorize publishing browser-containing images or clear commercial redistribution. Review the exact artifact's notices, corresponding-source obligations and font terms before distribution. Even a binary-free runtime has its existing distro-package obligations; do not call the entire image MIT.

These are engineering boundaries, not a legal opinion. License review remains a release gate for public prebundled browser images, not a claim that MPL prevents this local integration.

To exercise the original upstream 30-minute idle boundary without keepalive requests, add `VERGE_TEST_CAMOUFOX_IDLE_SEC=1810`. The test checks that the browser PID is unchanged and a real GUI click still works afterward. To verify the Chromium route with the same fixture, set `VERGE_TEST_AGENT_BROWSER` to your installed executable; the test obtains a Verge ticket through the Python CLI, then performs snapshot/fill/native-click through `agent-browser --cdp`.

Local acceptance on 2026-10-30: Linux ARM64 under OrbStack, both engine smoke tests passed, including 1,810 seconds without worker requests/keepalives and the same browser PID afterward. Xvfb/Xpra regression plus unit tests: 260 passed; Node CLI: 17; admin UI: 26. Chromium routing was tested with agent-browser 0.41.0's ARM64 native binary; its npm Node wrapper requires Node >=24. Cloak's actual licensed binary and other Camoufox architectures were not tested in this run.
