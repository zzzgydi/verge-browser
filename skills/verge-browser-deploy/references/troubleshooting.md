# Troubleshooting

## Startup looks healthy but sandbox creation fails

Check:

- the API service can access `/var/run/docker.sock`
- runtime images were built successfully
- `VERGE_SANDBOX_BASE_DIR` points to a real writable path
- if the API runs in Docker, the mounted repo path inside the container matches the host path

## Session or CDP proxy behaves incorrectly behind a gateway

Check:

- WebSocket upgrade support is enabled
- upstream timeout values are not too low
- the gateway preserves the original host and scheme if you rely on externally visible URLs

## Browser startup is flaky

Known issues:

- Chromium may fail if profile lock files remain in the browser profile directory
- sandbox creation returns before every browser probe is fully ready, so a short retry loop is normal

