# Browser Sandbox 技术方案文档

## 1. 文档目的

本文档定义一个可直接落地实现的 Browser Sandbox 系统，用于在单个隔离环境中同时提供：

- Chromium GUI 浏览器运行环境
- CDP（Chrome DevTools Protocol）程序化控制能力
- VNC / noVNC 人工接管能力
- GUI 级截图与鼠标键盘动作注入能力
- 共享文件系统
- 面向 Agent 的统一 REST / WebSocket / MCP 接口

目标是让 Claude Code 或其他编程 Agent 可以依据本文档，直接完成第一版完整项目实现。

范围约束：

- 本文档中的 MCP 仅指“未来可追加的一层工具封装接口”。
- V1 必须先完成 REST / WebSocket 能力；MCP 适配层不作为阻塞上线条件。

---

## 2. 产品定义与范围

### 2.1 核心能力

系统必须支持以下能力：

1. 创建隔离的 sandbox 会话。
2. 在 sandbox 内启动可视化 Chromium 浏览器。
3. 通过 CDP 暴露 Playwright / Puppeteer 可连接的控制接口。
4. 通过 noVNC 暴露人工接管界面。
5. 提供浏览器窗口级截图接口。
6. 提供 GUI 动作注入接口（移动、点击、滚动、输入、热键、等待）。
7. 提供统一共享工作目录 `/workspace`。
8. 提供浏览器重启、健康检查、状态查询。
10. 提供 JWT 鉴权与短时票据机制。

### 2.2 第一版非目标

V1 不强制实现以下能力：

- 多租户混部调度
- 容器热迁移
- 浏览器 session 快照恢复
- 音视频设备透传
- GPU 加速
- 操作录制回放
- 全量云原生编排

这些能力可在 V2 继续扩展。

---

## 3. 设计原则

### 3.1 单容器单会话

V1 采用“一容器一会话一浏览器”模型。每个 sandbox 对应一个容器实例，容器内运行浏览器、VNC、API 代理等所有组件。

好处：

- 隔离边界清晰
- 文件系统天然共享
- 调试简单
- 生命周期清晰
- 易于后续上 Kubernetes / Nomad

### 3.2 GUI 浏览器优先

系统不是单纯 headless browser。必须提供真实 GUI 浏览器，这样才能统一支持：

- VNC 可视化接管
- GUI 自动化
- 文件选择器与下载栏
- 多 tab / 多窗口
- 更接近真实用户行为的交互

### 3.3 控制面分层

浏览器控制分为三层：

1. **CDP 层**：高能力程序控制
2. **GUI 动作层**：更拟真的视觉动作控制
3. **人工接管层**：VNC / noVNC

### 3.4 统一工作区

浏览器和文件接口都共享 `/workspace`，保证下载、上传、代码生成、文件处理形成闭环。

### 3.5 显式会话管理

所有浏览器入口、VNC 入口、CDP 入口必须绑定 sandbox_id，并且通过鉴权网关统一暴露，不能裸露内部 5900 / 9222。

---

## 4. 系统总架构

```text
Client / Agent / Human Operator
        |
        v
+-------------------------------+
| API Gateway / Session Router  |
| REST + WS + Auth + Tickets    |
+-------------------------------+
        |
        +-----------------------------+
        |                             |
        v                             v
+--------------------+      +----------------------+
| Browser APIs       |      | File APIs            |
| screenshot/actions |      | read/write/upload    |
+--------------------+      +----------------------+
        |
        +-----------------------------+
        |
        v
+-----------------------------------------------+
| Sandbox Container                              |
|                                               |
|  +------------------+   +-------------------+ |
|  | Xvfb / X11       |   | Window Manager    | |
|  +------------------+   +-------------------+ |
|             |                    |            |
|             +--------+-----------+            |
|                      |                        |
|               +-------------+                 |
|               | Chromium    |<----CDP Proxy   |
|               +-------------+                 |
|                      |                        |
|               +-------------+                 |
|               | x11vnc      |---->websockify  |
|               +-------------+                 |
|                                               |
|  +------------------+  +-------------------+ |
|  | /workspace       |  | supervisord        | |
|  +------------------+  +-------------------+ |
|                                               |
+-----------------------------------------------+
```

V1 职责约定：

- 为降低实现复杂度，V1 默认由同一个 FastAPI 服务同时承担 `API Server` 与 `Gateway` 职责。
- 文中提到的鉴权、sandbox 路由、ticket 校验、WebSocket 代理，默认均在该服务内实现。
- 若后续拆分独立 Gateway，应保持外部 API 路径和鉴权模型不变。

---

## 5. 技术选型

### 5.1 语言与框架

后端主服务：Python 3.11+

理由：

- FastAPI / Starlette 非常适合 REST + WebSocket
- 对 Playwright / CDP 生态友好
- 与 Agent 工具、MCP、自动化脚本集成成本低
- 适合快速实现 MVP

### 5.2 Web 框架

- FastAPI：REST API
- Uvicorn：ASGI Server
- httpx：HTTP 客户端
- websockets / anyio：WebSocket 转发与保活

### 5.3 浏览器与 GUI

- Chromium 或 Google Chrome Stable
- Xvfb：虚拟显示
- Openbox：轻量窗口管理器
- x11vnc：VNC 服务
- noVNC + websockify：浏览器内 VNC 接管

### 5.4 GUI 自动化与观测

- xdotool：鼠标键盘动作注入
- wmctrl / x11-utils：窗口发现与状态读取
- ImageMagick：窗口级截图

### 5.5 进程管理

- supervisord

选择理由：

- V1 目标是快速落地、易调试、配置直观，`supervisord` 足够满足多进程编排需求。
- `s6-overlay`、`runit` 等方案并非不能用，但会提高镜像与启动脚本复杂度，不作为第一版阻塞项。
- 为避免僵尸进程和依赖顺序问题，仍需通过 `stopsignal`、`priority`、前置等待脚本补齐工程细节。

### 5.6 反向代理

本地开发可直接 Uvicorn。
生产环境建议：

- Caddy 或 Nginx
- TLS 终止
- WebSocket 透传
- 限流
- Header 转发

### 5.7 容器运行时

- Docker（开发 / 单机）
- 后续可迁移至 Kubernetes

---

## 6. 仓库结构设计

建议采用单仓多模块结构：

```text
browser-sandbox/
  apps/
    api-server/
      app/
        main.py
        config.py
        deps.py
        auth/
        routes/
        services/
        models/
        schemas/
        utils/
    sandbox-runtime/
      scripts/
        start_all.sh
        start_x.sh
        start_browser.sh
        start_vnc.sh
        healthcheck.sh
      supervisor/
        supervisord.conf
      browser/
        policies/
    novnc/
  packages/
    common/
      logging.py
      errors.py
      settings.py
      types.py
    browser_control/
      cdp_proxy.py
      screenshot.py
      gui_actions.py
      window_info.py
    file_control/
      file_service.py
    sandbox_manager/
      lifecycle.py
      registry.py
      health.py
      docker_adapter.py
    auth/
      jwt.py
      tickets.py
  docker/
    runtime-image.Dockerfile
  deployments/
    docker-compose.yml
    caddy/
    kubernetes/
  tests/
    unit/
    integration/
    e2e/
  docs/
    openapi/
    tech.md
    architecture.md
  pyproject.toml
  Makefile
  README.md
```

---

## 7. 容器内部运行时设计

### 7.1 容器职责

每个 sandbox 容器内部应运行以下进程：

1. Xvfb
2. Openbox
3. Chromium
4. x11vnc
5. websockify
6. supervisord

### 7.2 容器内部目录规范

```text
/workspace                # 用户共享工作目录
/workspace/downloads      # 浏览器下载目录
/workspace/uploads        # 用户上传目录
/workspace/browser-profile# Chromium user-data-dir
/var/log/sandbox          # 运行日志
/run/sandbox              # pid/socket/state files
/opt/sandbox              # 脚本和内置资源
```

说明：

- `/workspace/*` 位于宿主机沙盒目录挂载的工作区内，用于保留下载、上传和浏览器 profile。
- 每个沙盒宿主机根目录额外保存一个 `meta.json`，不挂载进容器，用于服务重启后的控制面恢复。

### 7.3 环境变量规范

```text
SANDBOX_ID=
DISPLAY=:99
XVFB_WHD=1280x1024x24
BROWSER_REMOTE_DEBUGGING_PORT=9222
VNC_SERVER_PORT=5900
WEBSOCKET_PROXY_PORT=6080
BROWSER_WINDOW_WIDTH=1280
BROWSER_WINDOW_HEIGHT=1024
BROWSER_DOWNLOAD_DIR=/workspace/downloads
BROWSER_USER_DATA_DIR=/workspace/browser-profile
DEFAULT_URL=about:blank
HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=
ALLOWED_DOMAINS=
BLOCKED_DOMAINS=
JWT_PUBLIC_KEY=
TICKET_SECRET=
```

---

## 8. 浏览器运行时实现

### 8.1 Xvfb 启动

示例命令：

```bash
Xvfb :99 -screen 0 1280x1024x24 -ac +extension RANDR
```

说明：

- `:99` 为显示号
- 24-bit 色深足够支持截图与浏览器渲染
- 可选启用 RANDR，便于动态分辨率调整

### 8.2 窗口管理器启动

示例命令：

```bash
DISPLAY=:99 openbox
```

选择 openbox 的原因：

- 体积小
- 依赖少
- 足够稳定
- 不需要复杂桌面组件

运行时约束：

- Chromium 窗口必须由 openbox 规则固定在 `(0,0)` 并启动即最大化
- 必须禁用会导致整窗拖拽/缩放的窗口管理器鼠标绑定，避免 noVNC 人工接管时把浏览器窗口本身拖离视口

### 8.3 Chromium 启动参数

推荐参数：

```bash
google-chrome \
  --display=:99 \
  --no-first-run \
  --no-default-browser-check \
  --disable-background-networking \
  --disable-dev-shm-usage \
  --disable-popup-blocking \
  --disable-features=TranslateUI \
  --window-position=0,0 \
  --window-size=1280,1024 \
  --start-maximized \
  --user-data-dir=/workspace/browser-profile \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --disk-cache-dir=/tmp/chrome-cache \
  --force-color-profile=srgb \
  --lang=en-US \
  about:blank
```

可选参数，视容器权限情况决定：

```bash
--no-sandbox
--disable-gpu
```

注意：

- 若容器权限和内核特性允许，优先不要使用 `--no-sandbox`
- `/dev/shm` 建议分配至少 1GB，避免浏览器崩溃

### 8.4 浏览器配置注入

浏览器启动前需生成以下策略：

1. 默认下载目录
2. 是否允许多文件下载
3. 是否自动恢复 session
4. URL 访问 allowlist / blocklist
5. 可选代理配置

实现方式：

- 通过预置 Chromium profile 偏好文件实现部分设置
- 通过启动参数实现代理
- 通过外层网络层实现域名策略

### 8.5 浏览器健康检查

健康检查逻辑：

1. 检查 Chromium pid 是否存在
2. 请求 `http://127.0.0.1:9222/json/version`
3. 解析返回的 `Browser` 和 `webSocketDebuggerUrl`
4. 失败则标记浏览器异常

建议区分两类检查：

- `liveness`：进程是否还活着，供 supervisor / runtime 自愈使用
- `readiness`：CDP、窗口系统、VNC 是否可服务，供 API 对外放量使用

只有当以下条件同时满足时，sandbox 才应进入 `RUNNING`：

1. Xvfb 可连接
2. Chromium `/json/version` 返回成功
3. Chromium 顶层窗口已被探测到
4. x11vnc 与 websockify 监听就绪

---

## 9. VNC / noVNC 实现

### 9.1 x11vnc 启动

示例命令：

```bash
x11vnc \
  -display :99 \
  -forever \
  -shared \
  -rfbport 5900 \
  -nopw \
  -localhost \
  -xkb
```

说明：

- `-localhost` 表示只允许容器内访问，外部必须通过网关转发
- `-forever` 确保客户端断开后服务不退出
- `-shared` 支持多客户端观察

### 9.2 websockify 启动

```bash
websockify --web /opt/novnc 6080 localhost:5900
```

### 9.3 API Gateway 暴露方式

外部访问路径示例：

- `GET /sandboxes/{sandbox_id}/vnc/` -> noVNC 静态资源
- `WS /sandboxes/{sandbox_id}/vnc/websockify` -> WebSocket 代理

### 9.4 VNC 鉴权

VNC 浏览器页面无法稳定带 Authorization Header，因此推荐短时票据：

- 主 API 先签发 ticket，TTL 60 秒
- ticket 必须绑定 `sandbox_id`、访问路径 scope、过期时间、nonce
- ticket 最好绑定一次性使用语义；至少要在首个 WebSocket 握手成功后失效
- 页面 URL 格式：

```text
/sandboxes/{sandbox_id}/vnc/?ticket=xxxxx
```

网关校验 ticket 后，允许建立 noVNC 页面与 WebSocket 通道。

额外要求：

- `GET /vnc/` 与 `WS /vnc/websockify` 必须校验同一张 ticket 或同一条已建立的短时会话
- 不应仅凭 query string 中的 sandbox_id 放行 WebSocket
- ticket 校验失败应返回明确的 401/403，而不是静默断链

推荐消费流程：

1. 用户访问 `GET /sandboxes/{id}/vnc/?ticket=...`
2. 服务端校验 ticket，并在服务端创建一个短时 `vnc_session`
3. 服务端通过 HttpOnly Cookie 或等价短时会话标识返回 noVNC 页面
4. 页面后续访问 `WS /sandboxes/{id}/vnc/websockify` 时，仅校验该短时会话
5. 初始 ticket 在首个成功消费后立即失效，避免 URL 泄露重放

### 9.5 VNC 安全要求

- 不允许直接暴露 5900
- 票据一次性或短时有效
- WebSocket 连接绑定 sandbox_id
- 限制单会话并发连接数
- 日志记录接入来源与时长

---

## 10. CDP Proxy 实现

### 10.1 为什么不能直接暴露 9222

直接暴露问题包括：

- 安全性差
- 内部地址泄露
- 无统一鉴权
- 难以做重连和保活
- 容器重启后外部连接失效不可恢复

### 10.2 外部 CDP 暴露模型

内部 Chromium：

- `http://127.0.0.1:9222/json/version`
- `ws://127.0.0.1:9222/devtools/browser/<id>`

外部对用户暴露：

- `GET /sandboxes/{sandbox_id}/browser/cdp/info`
- `WS /sandboxes/{sandbox_id}/browser/cdp/browser`

### 10.3 获取浏览器 ws 地址

服务端逻辑：

1. 请求内部 `/json/version`
2. 解析 `webSocketDebuggerUrl`
3. 不直接返回该 URL
4. 返回平台自有 URL

返回示例：

```json
{
  "cdp_url": "wss://api.example.com/sandboxes/sb_123/browser/cdp/browser",
  "browser_version": "Chrome/123.0.x",
  "protocol_version": "1.3"
}
```

### 10.4 WebSocket 代理逻辑

代理必须实现：

1. 外部 client 建立 WS
2. 服务端内部再连接 Chromium 原生 WS
3. 双向转发消息
4. 服务端周期性 ping/pong
5. 浏览器异常断开时，主动通知 client
6. 连接关闭时清理上下文
7. 保留 close code / reason，避免 client 误判为网络抖动
8. 对慢客户端做背压控制，避免无限缓存导致网关内存泄漏

建议实现：

- 为每个方向维护有限长度的异步队列，例如 `asyncio.Queue(maxsize=100)`
- 当下游持续消费不过来时，优先关闭连接并返回明确 reason，而不是无限堆积消息
- 日志中记录被动断开的方向、累计积压条数和最终 close code

### 10.5 重连策略

V1 建议：

- 不对外提供无感重连
- 浏览器重启后要求 client 主动重新建立 WebSocket 连接

服务端仍需：

- 发现 Chromium 重启后，旧连接标记失效
- 新连接可自动解析最新 `webSocketDebuggerUrl`

补充说明：

- 对外暴露的 `cdp_url` 应是平台稳定 URL，例如 `/sandboxes/{id}/browser/cdp/browser`。
- 变化的是其背后映射的 Chromium `webSocketDebuggerUrl`，而不是平台 URL 本身。

### 10.6 Playwright 兼容

为兼容 `connect_over_cdp`：

- 必须提供标准浏览器级 websocket 入口
- 不要只提供 page target 入口
- 确保二进制消息、文本消息都能透传

---

## 11. GUI 动作执行系统

### 11.1 目标

通过 API 执行浏览器窗口级动作，而不是页面 DOM 级动作。

### 11.2 支持的动作类型

- MOVE_TO
- CLICK
- DOUBLE_CLICK
- RIGHT_CLICK
- MOUSE_DOWN
- MOUSE_UP
- DRAG_TO
- SCROLL
- TYPE_TEXT
- KEY_PRESS
- HOTKEY
- WAIT

### 11.3 输入协议

建议采用动作数组：

```json
{
  "actions": [
    { "type": "MOVE_TO", "x": 320, "y": 420 },
    { "type": "CLICK", "button": "left" },
    { "type": "TYPE_TEXT", "text": "hello" },
    { "type": "WAIT", "duration_ms": 1000 }
  ]
}
```

补充约定：

- 若某个动作包含 `x/y`，则坐标应直接作用于该动作，不依赖前一个 `MOVE_TO`。
- 若 `CLICK/DOUBLE_CLICK/RIGHT_CLICK/MOUSE_DOWN/MOUSE_UP` 未提供 `x/y`，则默认作用于当前鼠标位置。
- `TYPE_TEXT` 仅负责输入，不隐式聚焦输入框；聚焦应通过前置点击或热键显式完成。
- 整个 action batch 默认串行执行；任一步失败时默认中止，除非请求显式指定 `continue_on_error=true`。

### 11.4 底层执行方式

推荐使用 `xdotool`，因为：

- 容器内稳定
- 对 X11 兼容好
- 简单易调试

示例命令：

```bash
xdotool mousemove 320 420 click 1
xdotool type --delay 20 "hello"
xdotool key ctrl+l
```

### 11.5 坐标系设计

必须区分两个概念：

1. `window_viewport`
   - 整个浏览器窗口截图坐标
   - 包含标签栏、工具栏

2. `page_viewport`
   - 网页内容区域
   - 不包含浏览器 UI

V1 统一约定：

- `/browser/screenshot` 返回 `window_viewport`
- 动作坐标默认基于 `window_viewport`

### 11.6 浏览器窗口位置获取

需实现一个窗口探测模块：

1. 找到 Chromium 顶层 X11 window
2. 获取绝对坐标、宽高
3. 记录窗口边框与内容区偏移

可用工具：

- `wmctrl -lpG`
- `xwininfo`
- `xdotool search --name`

### 11.7 动作执行返回

返回结构建议包括：

```json
{
  "ok": true,
  "executed": 4,
  "screenshot_after": false,
  "errors": []
}
```

可选支持：动作执行后自动回传截图。

建议补充一个只读端点：

- `GET /sandboxes/{id}/browser/viewport`

用于显式返回：

- 当前 `window_viewport`
- 当前 `page_viewport`
- 当前激活窗口和坐标偏移信息

---

## 12. 截图系统

### 12.1 截图类型

必须支持两类截图：

1. **窗口级截图**
   - 用于 VLM 识别与人工理解
   - 带浏览器 UI

2. **页面级截图**
   - 通过 CDP `Page.captureScreenshot`
   - 只包含页面内容

### 12.2 窗口级截图实现

建议优先通过 X11 window id 精确截取，而不是全屏裁切。

实现路径：

1. 找到 Chromium 窗口 id
2. 使用 `xwd` / `import` / `imagemagick` 截取窗口
3. 转为 PNG
4. 返回 binary / base64 / 文件路径

### 12.3 页面级截图实现

通过 CDP target 执行：

- `Page.enable`
- `Page.captureScreenshot`

target 选择规则必须明确：

- 默认对当前激活 tab 对应的 page target 截图
- 若请求包含 `target_id`，则按指定 target 截图
- 若当前不存在 page target，应返回 409 或明确业务错误，而不是返回空图

### 12.4 API 设计

- `GET /sandboxes/{id}/browser/screenshot?type=window`
- `GET /sandboxes/{id}/browser/screenshot?type=page`
- `GET /sandboxes/{id}/browser/screenshot?type=page&target_id=...`

建议支持的可选参数：

- `format=png|jpeg|webp`
- `quality=1..100`，仅对有损格式生效
- `width` / `height`，用于等比缩放返回图像

V1 默认值建议：

- `format=png`
- 不传 `quality`
- 不传缩放参数

返回可选：

- `image/png`
- JSON + base64
- 临时下载 URL

### 12.5 截图元数据

建议同时返回：

```json
{
  "width": 1280,
  "height": 1024,
  "page_viewport": { "x": 0, "y": 80, "width": 1280, "height": 944 },
  "window_viewport": { "x": 0, "y": 0, "width": 1280, "height": 1024 }
}
```

---

## 13. 文件系统与文件 API

### 14.1 根目录

统一根目录：`/workspace`

### 14.2 API 列表

- `GET /sandboxes/{id}/files/list?path=/workspace`
- `GET /sandboxes/{id}/files/read?path=/workspace/a.txt`
- `POST /sandboxes/{id}/files/write`
- `POST /sandboxes/{id}/files/upload`
- `GET /sandboxes/{id}/files/download?path=/workspace/report.pdf`
- `DELETE /sandboxes/{id}/files?path=/workspace/a.txt`

### 14.3 路径安全

所有路径必须：

1. 归一化
2. 解析真实路径
3. 校验位于 `/workspace` 下
4. 拒绝路径逃逸 `..`
5. 拒绝符号链接逃逸
6. 对写入操作使用原子写或临时文件替换，避免部分写入
7. 明确覆盖策略：默认拒绝覆盖，或显式 `overwrite=true`

### 14.4 上传策略

上传文件默认保存到：

```text
/workspace/uploads
```

上传限制建议：

- V1 默认单文件大小上限应明确，例如 `100MB`
- 超过限制时返回 `413 Payload Too Large`
- 上传接口应在响应中返回最终保存路径与实际写入大小

### 14.5 浏览器下载策略

浏览器默认下载目录设为：

```text
/workspace/downloads
```

---

## 15. Sandbox 生命周期管理

### 15.1 状态机

每个 sandbox 必须有明确状态：

- CREATING
- STARTING
- RUNNING
- DEGRADED
- STOPPING
- STOPPED
- FAILED

### 15.2 创建流程

1. 接收创建请求
2. 分配 sandbox_id
3. 创建工作目录卷
4. 持久化沙盒元数据
5. 启动容器
6. 等待健康检查通过
7. 返回访问端点

### 15.3 暂停 / 恢复流程

V1 当前实现支持显式暂停与恢复：

- `pause`：删除运行时容器，但保留工作目录和浏览器 profile
- `resume`：重新创建容器并挂载现有工作目录
- API 服务重启后，会从磁盘重建 registry，并将已恢复的记录统一标记为 `STOPPED`

这解决的是“控制面重启后找回沙盒”和“保留登录态后继续使用”的问题，不等同于浏览器进程级快照恢复。

### 15.4 销毁流程

1. 阻止新连接
2. 关闭 VNC/CDP/WS 连接
3. 停止容器
4. 收集日志
5. 清理临时文件
6. 删除或归档卷

当前代码路径中，`destroy` 表示硬删除：既删除容器，也删除沙盒目录及其 `meta.json`。

### 15.5 浏览器重启

`restart` API 应只表示真正发生了服务端状态变更的重启动作。

因此 V1 建议仅支持：

- `hard`：通过 supervisor 重启 Chromium 主进程，并使旧 CDP / VNC 连接失效

不建议把“提示客户端重连”定义为 `soft restart`，因为它不构成真正的重启，会让 API 语义混乱。若需要，可另提供：

- `POST /sandboxes/{id}/browser/reconnect-hint`
- 或由网关在检测到浏览器短暂抖动时下发事件通知

客户端感知要求：

- 旧 CDP WebSocket 应收到明确 close code / reason
- VNC 会话断开时应在页面层展示“browser restarted”或等价提示
- 若系统已存在状态通知通道，可增加 `browser_restarted` 事件；若没有，不应为此单独引入新的消息总线

API：

`POST /sandboxes/{id}/browser/restart`

请求：

```json
{
  "level": "hard"
}
```

---

## 16. API Gateway 设计

### 16.1 责任

Gateway 负责：

- 鉴权
- sandbox 路由
- 外部 URL 统一封装
- ticket 校验
- WebSocket 入口收敛
- 审计日志

### 16.2 路由风格

统一使用：

```text
/sandboxes/{sandbox_id}/...
```

### 16.3 主要接口清单

#### Sandbox

- `POST /sandboxes`
- `GET /sandboxes/{id}`
- `POST /sandboxes/{id}/pause`
- `POST /sandboxes/{id}/resume`
- `DELETE /sandboxes/{id}`

#### Browser

- `GET /sandboxes/{id}/browser/info`
- `GET /sandboxes/{id}/browser/screenshot`
- `POST /sandboxes/{id}/browser/actions`
- `POST /sandboxes/{id}/browser/restart`
- `GET /sandboxes/{id}/browser/cdp/info`
- `WS /sandboxes/{id}/browser/cdp/browser`

#### VNC

- `POST /sandboxes/{id}/vnc/tickets`
- `GET /sandboxes/{id}/vnc/`
- `WS /sandboxes/{id}/vnc/websockify`

#### Files

- `GET /sandboxes/{id}/files/list`
- `GET /sandboxes/{id}/files/read`
- `POST /sandboxes/{id}/files/write`
- `POST /sandboxes/{id}/files/upload`
- `GET /sandboxes/{id}/files/download`
- `DELETE /sandboxes/{id}/files`

---

## 17. 鉴权与安全设计

### 17.1 主鉴权

所有 REST / WS API 默认使用 JWT Bearer Token。

JWT 负载至少包含：

- `sub`
- `sandbox_ids` 或项目权限
- `exp`
- `scope`

### 17.2 Ticket 机制

适用于：

- noVNC 页面
- 一次性文件下载
- 临时分享入口

Ticket 结构：

- sandbox_id
- sub
- path/scope
- exp
- nonce
- HMAC 签名

补充要求：

- ticket 必须包含 `type`，至少区分 `vnc`、`file_download`、`share_link`
- ticket 应包含 `jti` 或等价唯一 ID，便于一次性消费和审计
- ticket 校验通过后，网关应记录消费状态，防止重放

### 17.3 容器隔离

建议配置：

- 限制 CPU / Memory / Pids
- 默认只挂载工作目录
- 只开放必要端口给宿主
- 禁止 privileged 模式
- 尽量收紧 seccomp / capabilities

可参考的 Docker 运行参数：

```bash
--cap-drop=ALL \
--security-opt=no-new-privileges:true \
--pids-limit=512 \
--read-only=false
```

说明：

- Chromium / X11 运行时通常仍需可写目录，因此不建议在文档中把 `--read-only` 作为默认要求。
- `cap-add` 与自定义 seccomp 配置应在实际验证 Chrome 运行需求后再收紧，避免先写出无法启动的“安全配置样板”。

### 17.4 网络隔离

推荐：

- sandbox 容器位于独立 bridge 网络
- 对外流量可经 egress proxy
- 禁止访问内网保留地址
- 阻断 metadata endpoint

### 17.5 文件安全

- 限制单文件大小
- 上传文件名净化
- 可选恶意文件扫描
- 文件下载需鉴权

### 17.6 审计日志

必须记录：

- sandbox 创建 / 销毁
- 浏览器重启
- VNC ticket 签发
- 文件上传下载
- WebSocket 建连断连

建议日志字段统一结构化，至少包含：

- `timestamp`
- `sandbox_id`
- `user_id` 或 `subject`
- `request_id`
- `remote_ip`
- `action`
- `result`
- `duration_ms`

---

## 18. Docker 设计

### 18.1 运行时镜像基础依赖

需要安装：

- Python 3.11+
- Chromium / Google Chrome
- Xvfb
- openbox
- x11vnc
- novnc
- websockify
- xdotool
- wmctrl
- x11-utils
- imagemagick
- curl
- supervisor
- fonts-noto / 常见字体包

### 18.2 Dockerfile 原则

- 尽量多阶段构建
- 将 noVNC 静态资源放到固定目录
- 创建非 root 用户 `sandbox`
- 仅 supervisor 入口为容器主进程

### 18.3 运行参数建议

```bash
docker run \
  --shm-size=1g \
  --memory=4g \
  --cpus=2 \
  -e SANDBOX_ID=sb_123 \
  image:tag
```

---

## 19. Supervisor 编排

### 19.1 进程顺序

建议由 supervisord 管理以下 program：

1. xvfb
2. openbox
3. chromium
4. x11vnc
5. websockify

依赖约束：

- `chromium` 启动前必须确认 Xvfb 和 Openbox 已就绪
- `x11vnc` 启动前必须确认显示和浏览器窗口可见
- `websockify` 可在 `x11vnc` 就绪后启动
- 若 `xvfb` 被重启，应视为图形会话整体失效，并触发其余图形相关进程重启

### 19.2 重启策略

- xvfb: unexpected 退出自动重启
- openbox: 自动重启
- chromium: 自动重启，但限制重启频率
- x11vnc/websockify: 自动重启

### 19.3 示例 supervisord.conf 思路

每个 program 应定义：

- command
- autorestart=true
- priority
- stdout_logfile
- stderr_logfile
- environment=DISPLAY=:99
- 配合前置检查脚本，例如 `wait_for_x.sh`

---

## 20. 实现模块分解（供 Claude Code 逐步完成）

### 20.1 阶段 A：Runtime 容器

任务：

1. 编写 Dockerfile
2. 安装 Chromium + Xvfb + openbox + x11vnc + websockify + xdotool
3. 编写 supervisor 配置
4. 编写 `start_browser.sh`
5. 验证容器内部 `/json/version` 可访问
6. 验证 noVNC 页面可打开

验收标准：

- 容器启动后 Chromium 可见
- VNC 可连接
- `curl 127.0.0.1:9222/json/version` 返回成功

### 20.2 阶段 B：API Server 基础

任务：

1. 初始化 FastAPI 项目
2. 实现 healthz
3. 实现 sandbox registry（先用内存或本地 docker）
4. 实现 `POST /sandboxes`
5. 实现 `GET /sandboxes/{id}`
6. 实现 `DELETE /sandboxes/{id}`

验收标准：

- 可通过 API 创建和销毁 sandbox

### 20.3 阶段 C：Browser APIs

任务：

1. 实现 `GET /browser/info`
2. 实现 `GET /browser/screenshot`
3. 实现 `POST /browser/actions`
4. 实现 `POST /browser/restart`
5. 实现窗口信息探测

验收标准：

- 可返回截图
- 可通过坐标点击页面
- Chromium 崩溃后能重启

### 20.4 阶段 D：CDP Proxy

任务：

1. 实现 `/browser/cdp/info`
2. 实现 `/browser/cdp/browser` WebSocket 代理
3. 加入 ping/pong 保活
4. 用 Playwright `connect_over_cdp` 验证

验收标准：

- Playwright 可连接并操作页面

### 20.5 阶段 E：VNC Ticket 与网关

任务：

1. 实现 ticket 签发
2. 实现 noVNC 路由转发
3. 实现 WS ticket 校验
4. 完成浏览器内接管链路

验收标准：

- 用户通过带 ticket 的 URL 可接管浏览器

### 20.6 阶段 F：Files

任务：

1. 实现 files list/read/write/upload/download
2. 完成路径安全检查

验收标准：

- 浏览器下载文件后 API 可读
- 上传文件后浏览器能访问

---

## 21. 关键伪代码

### 21.1 获取浏览器信息

```python
async def get_browser_info(sandbox: SandboxRuntime) -> BrowserInfo:
    version = await http_get(f"http://{sandbox.host}:{sandbox.cdp_port}/json/version")
    return BrowserInfo(
        cdp_url=f"wss://api.example.com/sandboxes/{sandbox.id}/browser/cdp/browser",
        vnc_ticket_endpoint=f"https://api.example.com/sandboxes/{sandbox.id}/vnc/tickets",
        vnc_entry_base_url=f"https://api.example.com/sandboxes/{sandbox.id}/vnc/",
        browser_version=version["Browser"],
        protocol_version=version["Protocol-Version"],
    )
```

说明：

- `browser/info` 不应直接返回带临时 ticket 的最终 VNC URL，因为该 URL 具有短时效性，不适合被缓存或写入持久状态。
- 更合理的契约是返回稳定入口和 ticket 签发端点，由客户端在需要接管时再申请票据。

### 21.2 CDP WebSocket 代理

```python
@app.websocket("/sandboxes/{sandbox_id}/browser/cdp/browser")
async def cdp_browser_proxy(ws: WebSocket, sandbox_id: str):
    await authenticate_ws(ws)
    sandbox = registry.get(sandbox_id)
    await ws.accept()

    try:
        version = await fetch_json(f"http://{sandbox.host}:{sandbox.cdp_port}/json/version")
        upstream_url = version["webSocketDebuggerUrl"]

        async with websockets.connect(upstream_url, ping_interval=20, ping_timeout=20) as upstream:
            async def client_to_upstream():
                while True:
                    msg = await ws.receive()
                    if "text" in msg:
                        await upstream.send(msg["text"])
                    elif "bytes" in msg:
                        await upstream.send(msg["bytes"])
                    else:
                        break

            async def upstream_to_client():
                async for msg in upstream:
                    if isinstance(msg, bytes):
                        await ws.send_bytes(msg)
                    else:
                        await ws.send_text(msg)

            await run_concurrently(client_to_upstream(), upstream_to_client())
    except Exception:
        await ws.close(code=1011, reason="browser proxy error")
```

### 21.3 GUI 动作执行

```python
async def execute_action(action: BrowserAction):
    if action.type == "MOVE_TO":
        await run(["xdotool", "mousemove", str(action.x), str(action.y)])
    elif action.type == "CLICK":
        button = {"left": "1", "middle": "2", "right": "3"}[action.button]
        await run(["xdotool", "click", button])
    elif action.type == "TYPE_TEXT":
        await run(["xdotool", "type", "--delay", "20", action.text])
    elif action.type == "HOTKEY":
        key = "+".join(action.keys)
        await run(["xdotool", "key", key])
    elif action.type == "WAIT":
        await asyncio.sleep(action.duration_ms / 1000)
```

### 21.4 路径安全检查

```python
from pathlib import Path

WORKSPACE = Path("/workspace").resolve()

def safe_path(user_path: str) -> Path:
    raw = Path(user_path)
    candidate = raw if raw.is_absolute() else (WORKSPACE / raw)
    p = candidate.resolve()

    try:
        p.relative_to(WORKSPACE)
    except ValueError:
        raise ValueError("path escapes workspace")

    return p
```

说明：

- 不应使用 `str.startswith()` 判断目录归属，否则 `/workspace-evil/a.txt` 会被误判为合法路径。
- 写接口还应额外校验父目录存在且可写，必要时限制允许创建的层级。

---

## 22. OpenAPI 数据模型建议

### 22.1 SandboxInfo

```json
{
  "id": "sb_123",
  "status": "RUNNING",
  "created_at": "2026-03-10T10:00:00Z",
  "browser": {
    "cdp_url": "wss://...",
    "vnc_entry_base_url": "https://...",
    "vnc_ticket_endpoint": "https://...",
    "viewport": { "width": 1280, "height": 1024 }
  }
}
```

### 22.2 BrowserAction

```json
{
  "type": "CLICK",
  "x": 320,
  "y": 400,
  "button": "left"
}
```

### 22.3 FileEntry

```json
{
  "name": "report.pdf",
  "path": "/workspace/downloads/report.pdf",
  "size": 12345,
  "is_dir": false,
  "modified_at": "2026-03-10T10:02:00Z"
}
```

---

## 23. 测试方案

### 23.1 单元测试

覆盖：

- 路径安全
- ticket 签名与过期
- ticket 重放与单次消费
- JWT 校验
- 动作参数校验
- sandbox 状态机

### 23.2 集成测试

覆盖：

1. 创建 sandbox
2. 获取 browser info
3. 截图成功
4. 执行 GUI 点击
5. 获取 CDP URL
6. Playwright 连接成功
7. 文件上传下载成功
8. 多 tab 场景下 page screenshot 命中正确 target
9. hard restart 后恢复
10. 上传超限返回 413

### 23.3 E2E 测试

编写脚本自动完成：

1. 创建 sandbox
2. 用 Playwright 连接 CDP
3. 打开 `example.com`
4. 新开第二个 tab 并切换激活页
5. 调 screenshot API 验证 page target 选择
6. 用 noVNC 访问页面
7. 用 files API 查看下载目录
8. 销毁 sandbox

### 23.4 故障测试

需要模拟：

- Chromium 进程被 kill
- x11vnc 崩溃
- websockify 崩溃
- `/json/version` 超时
- WebSocket 断链
- 路径为 `/workspace-evil/...` 的越权访问
- 符号链接指向 `/etc/passwd` 的逃逸访问
- 慢客户端导致 CDP 代理队列堆积

### 23.5 性能测试

建议补充最小性能基准：

1. 单机可稳定承载的 sandbox 数量
2. `browser/screenshot` 的平均延迟与 P95
3. CDP / VNC WebSocket 并发连接数
4. 浏览器 hard restart 的平均恢复时间

---

## 24. 性能与容量预估

V1 粗略估算：

每个 sandbox：

- CPU：1~2 vCPU
- 内存：2~4 GB
- `/dev/shm`：1 GB
- 磁盘：2~10 GB

并发 10 个 sandbox 的单机建议：

- 16 vCPU
- 32~64 GB RAM
- SSD

---

## 25. 生产部署建议

### 25.1 单机部署

- API Gateway 与 Docker 守护进程同机
- Gateway 创建 / 销毁 runtime 容器
- Caddy/Nginx 负责 TLS

### 25.2 K8s 部署（后续）

- 每个 sandbox 映射为 Pod
- Gateway 通过 K8s API 创建 Pod
- Service 不直接暴露 9222/5900
- Gateway 通过端口转发或 sidecar 访问

### 25.3 日志

必须采集：

- API 访问日志
- supervisord 日志
- Chromium stderr
- VNC / websockify 日志

---

## 26. Claude Code 实施指令建议

可将整个项目分批交给 Claude Code：

### 批次 1：初始化仓库

要求 Claude Code：

- 初始化 Python monorepo
- 生成 FastAPI 工程骨架
- 生成 Dockerfile 与 supervisord 配置骨架
- 建立 lint / test / format 工具链

### 批次 2：实现 runtime 容器

要求 Claude Code：

- 安装所有运行时依赖
- 编写启动脚本
- 编写 healthcheck 脚本
- 验证 Chromium + VNC + CDP 可启动

### 批次 3：实现 API Server

要求 Claude Code：

- 完成 sandbox CRUD
- 完成 browser info / screenshot / restart
- 完成 GUI actions

### 批次 4：实现 CDP Proxy 与 VNC ticket

要求 Claude Code：

- 完成 WebSocket 双向转发
- 完成票据签名校验
- 完成 noVNC 代理路由

### 批次 5：实现 files

要求 Claude Code：

- 完成文件服务
- 增加路径安全和测试

### 批次 6：测试与文档

要求 Claude Code：

- 完成集成测试
- 生成 OpenAPI 文档
- 生成本地开发说明

---

## 27. 第一版验收标准

当以下场景全部通过时，V1 即可视为完成：

1. 调用 API 创建 sandbox 成功。
2. 返回 browser info，包含可用的 cdp_url 和 vnc_url。
3. 用户可在浏览器打开 noVNC 页面并看到 Chromium。
4. Playwright 可通过 cdp_url 成功连接并导航网页。
5. `/browser/screenshot` 返回窗口截图。
6. `/browser/actions` 可以点击和输入。
7. files API 可以列出 `/workspace` 内容。
8. 浏览器下载的文件可通过 files API 读取。
9. `browser/restart hard` 后仍可恢复服务。
10. 删除 sandbox 后所有连接关闭、容器清理完成。

---

## 28. 后续增强建议

V2 可以继续做：

- 录屏与会话回放
- 操作审计可视化
- 域名策略与出网代理增强
- 基于 VLM 的视觉定位 API
- 多浏览器支持（Firefox）
- Session snapshot / restore
- Kubernetes 调度器与资源池
- MCP 工具总线

---

## 29. 最终实施建议

如果目标是尽快做出可用系统，建议严格按以下顺序推进：

1. 先把 runtime 容器跑通。
2. 再做 sandbox CRUD。
3. 再做 screenshot + actions。
4. 再做 CDP proxy。
5. 再做 VNC ticket。
6. 最后补 files / tests。

不要一开始就设计多租户、分布式调度、复杂权限模型。先把单容器单会话做到稳定，再向上扩展。

这套方案的关键成败点不在概念，而在以下工程细节：

- Chromium 稳定运行
- CDP WebSocket 稳定转发
- VNC 鉴权与接入体验
- GUI 截图与动作坐标一致性
- 共享文件系统闭环
- 浏览器崩溃后的恢复能力

只要这 6 点做扎实，这个项目就能成为一套真正可供 Agent 使用的 Browser Sandbox 基础设施。
