# Environment Variables

This document summarizes the environment variables used by the project during deployment and runtime. It separates them into:

- API server settings read from `.env` or the process environment
- host variables required by Docker Compose
- runtime container variables
- SDK / CLI variables commonly used after deployment

[`apps/api-server/app/config.py`](/Users/bytedance/Projects/Github/verge-browser/apps/api-server/app/config.py) uses `pydantic-settings`, reads the repository root `.env` file automatically, and applies the `VERGE_` prefix to all server-side settings.

## 1. API Server

The variables below are read directly by the API server and can be set in the repository root `.env` file.

| Variable                               | Default                                    | Required        | Description                                                                                                                                    |
| -------------------------------------- | ------------------------------------------ | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `VERGE_APP_NAME`                       | `verge-browser`                            | No              | Service name.                                                                                                                                  |
| `VERGE_ENV`                            | `development`                              | No              | Runtime environment. Outside `development`, secret strength validation is enforced.                                                            |
| `VERGE_HOST`                           | `0.0.0.0`                                  | No              | Bind host for the API server.                                                                                                                  |
| `VERGE_PORT`                           | `8000`                                     | No              | Bind port for the API server.                                                                                                                  |
| `VERGE_LOG_LEVEL`                      | `info`                                     | No              | Log level.                                                                                                                                     |
| `VERGE_SANDBOX_BASE_DIR`               | `.local/sandboxes`                         | Recommended     | Root directory for sandbox metadata and workspace state. In Docker deployments this should usually be set explicitly to the mounted host path. |
| `VERGE_ADMIN_STATIC_DIR`               | `apps/api-server/app/static/admin`         | No              | Admin web static assets directory. Usually only overridden in development or tests.                                                            |
| `VERGE_WORKSPACE_SUBDIR`               | `workspace`                                | No              | Workspace directory name inside a sandbox.                                                                                                     |
| `VERGE_DOWNLOADS_SUBDIR`               | `downloads`                                | No              | Downloads directory name.                                                                                                                      |
| `VERGE_UPLOADS_SUBDIR`                 | `uploads`                                  | No              | Uploads directory name.                                                                                                                        |
| `VERGE_BROWSER_PROFILE_SUBDIR`         | `browser-profile`                          | No              | Browser profile directory name.                                                                                                                |
| `VERGE_SANDBOX_DEFAULT_KIND`           | `xvfb_vnc`                                 | No              | Default runtime kind when creating a sandbox.                                                                                                  |
| `VERGE_SANDBOX_RUNTIME_IMAGE`          | `verge-browser-runtime-xvfb:latest`        | No              | Generic runtime image setting. Current code paths prefer the kind-specific image settings below.                                               |
| `VERGE_SANDBOX_RUNTIME_IMAGE_XVFB_VNC` | `verge-browser-runtime-xvfb:latest`        | No              | Runtime image for `xvfb_vnc`.                                                                                                                  |
| `VERGE_SANDBOX_RUNTIME_IMAGE_XPRA`     | `verge-browser-runtime-xpra:latest`        | No              | Runtime image for `xpra`.                                                                                                                      |
| `VERGE_SANDBOX_RUNTIME_NETWORK`        | `bridge`                                   | No              | Docker network used by runtime containers.                                                                                                     |
| `VERGE_SANDBOX_RUNTIME_MODE`           | `docker`                                   | No              | Runtime launch mode. The current implementation uses Docker.                                                                                   |
| `VERGE_SANDBOX_DEFAULT_URL`            | `https://github.com/zzzgydi/verge-browser` | No              | Default URL opened by the browser.                                                                                                             |
| `VERGE_SANDBOX_DEFAULT_WIDTH`          | `1280`                                     | No              | Default browser window width.                                                                                                                  |
| `VERGE_SANDBOX_DEFAULT_HEIGHT`         | `1024`                                     | No              | Default browser window height.                                                                                                                 |
| `VERGE_SANDBOX_SESSION_PORT`           | `6080`                                     | No              | Generic default session port. Current code paths use the kind-specific values below.                                                           |
| `VERGE_SANDBOX_SESSION_PORT_XVFB_VNC`  | `6080`                                     | No              | Session port for `xvfb_vnc`.                                                                                                                   |
| `VERGE_SANDBOX_SESSION_PORT_XPRA`      | `14500`                                    | No              | Session port for `xpra`.                                                                                                                       |
| `VERGE_SANDBOX_DISPLAY`                | `:99`                                      | No              | Generic default display. Current code paths use the kind-specific values below.                                                                |
| `VERGE_SANDBOX_DISPLAY_XVFB_VNC`       | `:99`                                      | No              | Display for `xvfb_vnc`.                                                                                                                        |
| `VERGE_SANDBOX_DISPLAY_XPRA`           | `:100`                                     | No              | Display for `xpra`.                                                                                                                            |
| `VERGE_SANDBOX_DEFAULT_SESSION_PATH`   | `/`                                        | No              | Default session URL path.                                                                                                                      |
| `VERGE_ADMIN_AUTH_TOKEN`               | `dev-admin-token`                          | Production: Yes | Admin bearer token. Outside development it must be non-default and at least 16 characters long.                                                |
| `VERGE_TICKET_SECRET`                  | `ticket-secret`                            | Production: Yes | Session ticket secret. Outside development it must be non-default and at least 32 characters long.                                             |
| `VERGE_TICKET_TTL_SEC`                 | `60`                                       | No              | Default ticket lifetime in seconds.                                                                                                            |
| `VERGE_FILE_UPLOAD_LIMIT_BYTES`        | `104857600`                                | No              | File upload size limit.                                                                                                                        |
| `VERGE_SANDBOX_START_TIMEOUT_SEC`      | `60`                                       | No              | Sandbox startup timeout in seconds.                                                                                                            |

### Recommended minimal `.env`

Local development can use the defaults. For any non-trivial deployment, at minimum configure:

```dotenv
VERGE_ENV=production
VERGE_SANDBOX_BASE_DIR=/absolute/path/to/verge-browser/.local/sandboxes
VERGE_ADMIN_AUTH_TOKEN=replace-with-a-long-random-token
VERGE_TICKET_SECRET=replace-with-an-even-longer-random-secret
```

## 2. Docker Compose / Host Environment

These variables are not API server settings, but the current deployment assets depend on them.

| Variable       | Default | Required | Description                                                                                                                                                                                                                                    |
| -------------- | ------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PROJECT_ROOT` | None    | Yes      | Used by [`deployments/docker-compose.yml`](/Users/bytedance/Projects/Github/verge-browser/deployments/docker-compose.yml) for `working_dir`, source mounts, and `VERGE_SANDBOX_BASE_DIR`. It must be the absolute repository path on the host. |

The current Compose setup effectively injects this value into the API container:

```dotenv
VERGE_SANDBOX_BASE_DIR=${PROJECT_ROOT}/.local/sandboxes
```

## 3. Runtime Container Environment

These variables are used by the runtime images or injected by the API server when it launches runtime containers. In most cases they do not need to be set manually on the host, but they are part of the deployment chain and matter when customizing images or debugging runtime issues.

### 3.1 Variables injected by the API server

| Variable                | Runtime    | Source     | Description                                                 |
| ----------------------- | ---------- | ---------- | ----------------------------------------------------------- |
| `SANDBOX_ID`            | All        | API server | Sandbox identifier.                                         |
| `DISPLAY`               | All        | API server | Runtime display.                                            |
| `BROWSER_WINDOW_WIDTH`  | All        | API server | Browser window width.                                       |
| `BROWSER_WINDOW_HEIGHT` | All        | API server | Browser window height.                                      |
| `DEFAULT_URL`           | All        | API server | Initial browser URL.                                        |
| `XPRA_DISPLAY`          | `xpra`     | API server | Xpra display.                                               |
| `XPRA_PORT`             | `xpra`     | API server | Xpra HTML5 service port.                                    |
| `XVFB_WHD`              | `xvfb_vnc` | API server | Xvfb screen geometry and depth, for example `1280x1024x24`. |
| `WEBSOCKET_PROXY_PORT`  | `xvfb_vnc` | API server | noVNC / websockify exposed port.                            |

### 3.2 Defaults baked into runtime images

| Variable                        | `xvfb_vnc` default            | `xpra` default                | Description                                                 |
| ------------------------------- | ----------------------------- | ----------------------------- | ----------------------------------------------------------- |
| `BROWSER_REMOTE_DEBUGGING_PORT` | `9222`                        | `9222`                        | Internal Chromium CDP port.                                 |
| `EXPOSED_CDP_PORT`              | `9223`                        | `9223`                        | Exposed CDP relay port.                                     |
| `BROWSER_DOWNLOAD_DIR`          | `/workspace/downloads`        | `/workspace/downloads`        | Browser downloads directory.                                |
| `BROWSER_USER_DATA_DIR`         | `/workspace/browser-profile`  | `/workspace/browser-profile`  | Browser profile directory.                                  |
| `DEFAULT_URL`                   | `about:blank`                 | `about:blank`                 | Fallback initial URL when not overridden by the API server. |
| `VNC_SERVER_PORT`               | `5900`                        | N/A                           | x11vnc listen port.                                         |
| `WEBSOCKET_PROXY_PORT`          | `6080`                        | N/A                           | noVNC / websockify port.                                    |
| `NOVNC_WEB_ROOT`                | `/usr/share/novnc`            | N/A                           | noVNC static assets path.                                   |
| `XVFB_WHD`                      | `1280x1024x24`                | N/A                           | Xvfb screen geometry and depth.                             |
| `XPRA_BIND_HOST`                | N/A                           | `0.0.0.0`                     | Xpra bind address.                                          |
| `XPRA_PORT`                     | N/A                           | `14500`                       | Xpra HTML5 port.                                            |
| `XPRA_HTML5`                    | N/A                           | `on`                          | Enables the Xpra HTML5 client.                              |
| `XPRA_RUNTIME_DIR`              | N/A                           | `/run/user/0/xpra`            | Xpra runtime directory.                                     |
| `OPENBOX_CONFIG`                | `/opt/sandbox/openbox/rc.xml` | N/A                           | Openbox config path for `xvfb_vnc`.                         |
| `OPENBOX_RC`                    | N/A                           | `/opt/sandbox/openbox/rc.xml` | Openbox config path for `xpra`.                             |
| `XMODIFIERS`                    | `@im=fcitx`                   | `@im=fcitx`                   | Input method environment.                                   |
| `GTK_IM_MODULE`                 | `fcitx`                       | `fcitx`                       | GTK input method module.                                    |
| `QT_IM_MODULE`                  | `fcitx`                       | `fcitx`                       | Qt input method module.                                     |
| `LC_ALL`                        | `zh_CN.UTF-8`                 | `zh_CN.UTF-8`                 | Container locale.                                           |
| `LANG`                          | `zh_CN.UTF-8`                 | `zh_CN.UTF-8`                 | Container locale.                                           |

## 4. SDK / CLI Variables

These variables do not affect the server deployment itself, but they are commonly used by SDK clients, test scripts, and example commands after the service is up.

| Variable              | Default                 | Description                                        |
| --------------------- | ----------------------- | -------------------------------------------------- |
| `VERGE_BROWSER_URL`   | `http://127.0.0.1:8000` | Default API base URL for the Python and Node SDKs. |
| `VERGE_BROWSER_TOKEN` | None                    | Default bearer token for the Python and Node SDKs. |

## 5. Usage Notes

- For production, at minimum set `VERGE_ENV`, `VERGE_SANDBOX_BASE_DIR`, `VERGE_ADMIN_AUTH_TOKEN`, and `VERGE_TICKET_SECRET`.
- When using [`deployments/docker-compose.yml`](/Users/bytedance/Projects/Github/verge-browser/deployments/docker-compose.yml), export `PROJECT_ROOT` before starting Compose.
- If the API server runs inside a container, `VERGE_SANDBOX_BASE_DIR` must point to a path that is visible inside the API container and matches the host mount path, otherwise runtime workspace mounts will fail.
- When debugging session or CDP issues, start by checking `DISPLAY`, `XPRA_PORT`, `WEBSOCKET_PROXY_PORT`, and `EXPOSED_CDP_PORT`.
