# AGENTS.md

## Project Scope

This repository implements a browser sandbox platform with:

- a FastAPI control plane in `apps/api-server`
- Docker-based runtimes in `apps/runtime-xvfb` and `apps/runtime-xpra`
- runtime image definitions in `docker/runtime-xvfb.Dockerfile` and `docker/runtime-xpra.Dockerfile`

## Working Rules

- Prefer small, verifiable changes over speculative refactors.
- Keep the API contract aligned with the `/sandbox/{sandbox_id}/...` routing model.
- Treat the runtime container and the API server as one integrated system. Do not change one without validating the other.
- Avoid introducing host-specific absolute paths into code, docs, tests, or examples.
- Use **Conventional Commits** for all `git commit` messages.
- Do not leak local developer information in generated code or `git commit` messages, including machine-specific paths, usernames, home directories, or other local environment details.

## Key Runtime Facts

- `xvfb_vnc` sandboxes run Chromium under Xvfb/Openbox and expose noVNC through the unified session URL.
- `xpra` sandboxes run Chromium under Xpra HTML5 and expose Xpra through the unified session URL.
- CDP is exposed through an internal relay on port `9223`.
- noVNC assets are served from `/usr/share/novnc` for `xvfb_vnc`.
- Browser GUI actions are executed through `xdotool`.
- Window screenshots are captured from X11 using ImageMagick `import`.

## Expected Validation

Before considering runtime-related work complete, run:

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
. .venv/bin/activate
PYTHONPATH=apps/api-server pytest tests/unit tests/integration/test_runtime_api.py
```

If Docker is unavailable, unit tests are still expected to pass.

## Files Worth Reading First

- `apps/api-server/app/services/browser.py`
- `apps/api-server/app/services/lifecycle.py`
- `apps/api-server/app/routes/`
- `apps/runtime-xvfb/scripts/`
- `apps/runtime-xpra/scripts/`
- `apps/runtime-xvfb/supervisor/supervisord.conf`
- `apps/runtime-xpra/supervisor/supervisord.conf`

## Common Pitfalls

- Chromium may fail to start if profile lock files are not cleared.
- VNC static asset paths differ by distro packaging; this repo currently uses Debian's `/usr/share/novnc`.
- CDP and noVNC should be validated through the actual runtime image, not only through mocked tests.
- When changing readiness logic, avoid raising hard failures during sandbox creation for transient startup conditions.
