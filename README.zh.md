# Verge Browser

[English](./README.md) | 中文

面向 AI Agent 的浏览器沙箱平台，把 CDP 自动化、GUI 级截图、共享文件和可视化人工接管放进同一个隔离运行时。

## 核心能力

- **真实 GUI Chromium**：不是 headless，支持多标签、下载、弹窗等完整浏览器行为
- **CDP 自动化**：可通过 WebSocket 与 Playwright、Puppeteer 兼容
- **GUI 级截图**：抓取完整浏览器窗口，而不只是页面内容
- **人工接管**：对 noVNC 和 Xpra 提供统一 session 入口
- **文件共享**：浏览器与 API 共用 `/workspace`，便于上传、下载和产物交换

## 两种桌面方案对比

| 特性     | `xvfb_vnc`                    | `xpra`                     |
| -------- | ----------------------------- | -------------------------- |
| 技术栈   | Xvfb + x11vnc + noVNC         | Xpra Server + HTML5 Client |
| 延迟     | 中等                          | 较低                       |
| 剪贴板   | 单向（手动同步）              | 双向自动同步               |
| 网络适应 | 较好                          | 优秀                       |
| 适用场景 | 以自动化为主，偶尔人工检查    | 频繁人工协作和远程调试     |
| 使用方式 | 创建时指定 `kind: "xvfb_vnc"` | 创建时指定 `kind: "xpra"`  |

如何选择：

- 以自动化为主，只偶尔人工查看：使用 `xvfb_vnc`
- 需要频繁人工接手或远程调试：使用 `xpra`

## 状态

该平台当前已可用于本地开发和单机部署。

当前代码库已经具备：

- 运行时容器启动，包含 Chromium、Xvfb/Openbox 或 Xpra，以及 CDP 中继
- 通过 API 创建沙箱
- 持久化沙箱元数据，并在服务启动时恢复为 `STOPPED`
- 复用工作目录的 `pause` / `resume`
- 真实窗口截图
- 通过 CDP 进行页面截图
- 通过 `xdotool` 执行 GUI 操作
- 面向 noVNC 和 Xpra 的基于票据的 session 入口

当前加固工作主要集中在基于健康检查的生命周期流转、浏览器崩溃恢复语义，以及更广泛的集成与 E2E 覆盖。

## 为何存在

多数浏览器自动化系统专注于无头页面控制，但这不足以支撑需要同时满足以下条件的 Agent 工作流：

- 通过 CDP 进行浏览器自动化
- 对整个浏览器窗口进行视觉推理
- 自动化卡住时由人接管
- 在同一环境里共享文件

Verge Browser 的目标，就是把浏览器、GUI 和文件都放进同一个隔离沙箱里，避免工作流被拆散到多个系统中。

## 架构

从高层次看，平台分为两部分：

1. API 服务器
   暴露 REST 和 WebSocket 端点，用于沙箱生命周期、浏览器控制、文件、CDP 代理和基于票据的 session 访问。
2. 沙箱运行时
   在单个隔离容器中运行 Chromium、桌面栈以及共享 `/workspace`。

```text
客户端 / Agent / 人工
        |
        v
+------------------------------+
| FastAPI 网关 / API 服务器    |
| 认证 + REST + WS + 票据      |
+------------------------------+
        |
        v
+-----------------------------------------------+
| 沙箱运行时容器                                |
| xvfb_vnc 或 xpra + Chromium + /workspace      |
+-----------------------------------------------+
```

## 当前能力

本仓库目前实现了：

- 基于 Docker 运行时启动的沙箱创建 / 获取 / 暂停 / 恢复 / 删除流程
- 工作目录元数据持久化，以及停止态沙箱的启动恢复
- 浏览器截图、操作、重启和 CDP 代理
- 基于票据的 session 入口，可下发 noVNC 或 Xpra 页面
- 工作空间范围的文件列表、读取、写入、上传、下载和删除操作
- 管理页构建为静态资源，并由 API 在 `/admin` 路径下提供
- 运行时 Dockerfile、supervisor 配置、启动脚本和基于 Docker 的集成测试

## 仓库结构

```text
apps/
  api-server/         FastAPI 应用程序
  admin-web/          Vite + React 管理页，构建后进入 API 静态资源目录
  runtime-xvfb/       Xvfb + VNC 运行时资源
  runtime-xpra/       Xpra 运行时资源
deployments/          本地部署资源
docker/               运行时与 API 容器构建文件
tests/                单元测试与集成测试
docs/                 产品、API 与技术文档
```

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
export PROJECT_ROOT="$PWD"
docker compose -f deployments/docker-compose.yml build api runtime-xvfb runtime-xpra
docker compose -f deployments/docker-compose.yml up api
```

打开 [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin) 开始使用。

本地开发时，如未覆盖 `VERGE_ADMIN_AUTH_TOKEN`，可直接使用默认 admin token `dev-admin-token` 登录。

部署相关环境变量可参考 [`docs/env.md`](./docs/env.md)。

### 方式二：本地开发

前置依赖：

- Python 3.11+
- Node.js 22+，并启用 Corepack / pnpm
- Docker

1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

2. 安装并构建管理页

```bash
corepack enable
pnpm --dir apps/admin-web install --frozen-lockfile
pnpm --dir apps/admin-web build
```

该命令会把静态产物输出到 `apps/api-server/app/static/admin`。

3. 构建运行时镜像

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
```

4. 启动 API 服务器

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

API 位于 [http://127.0.0.1:8000](http://127.0.0.1:8000)，管理页位于 [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)。

### 方式三：Docker 部署

在 Docker 中运行 API 服务，并通过宿主机 Docker socket 管理运行时容器。

```bash
# 构建运行时镜像
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .

# 构建 API 服务器镜像（同时打包管理页）
docker build -f docker/api-server.Dockerfile -t verge-browser-api:latest .

# 创建沙箱持久化目录
mkdir -p .local/sandboxes

# 对外暴露服务前请设置非默认鉴权密钥
export VERGE_ADMIN_AUTH_TOKEN="replace-with-a-long-random-token"
export VERGE_TICKET_SECRET="replace-with-a-long-random-ticket-secret"

# 运行 API 服务器容器
docker run -d \
  --name verge-api \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$(pwd):$(pwd)" \
  -e VERGE_SANDBOX_BASE_DIR="$(pwd)/.local/sandboxes" \
  -e VERGE_ADMIN_AUTH_TOKEN="$VERGE_ADMIN_AUTH_TOKEN" \
  -e VERGE_TICKET_SECRET="$VERGE_TICKET_SECRET" \
  -w "$(pwd)" \
  verge-browser-api:latest
```

这种方式要求 API 容器看到的项目绝对路径与宿主机一致，这样它在创建运行时容器时才能正确挂载沙箱工作目录。

完整的部署环境变量清单见 [`docs/env.md`](./docs/env.md)。

### 基本用法示例

安装 CLI：

```bash
npm install -g verge-browser
```

创建沙箱：

```bash
verge-browser sandbox create --alias test --width 1440 --height 900
```

截图：

```bash
verge-browser browser screenshot test --output ./screenshot.png
```

执行 GUI 动作：

```bash
verge-browser browser actions test --input ./actions.json
```

获取人工接管链接：

```bash
verge-browser sandbox session test
```

更多命令详见 [`docs/cli-sdk.md`](./docs/cli-sdk.md)。

## 开发指南

### 管理页开发

如果只改管理页，可单独启动 Vite 开发服务器：

```bash
pnpm --dir apps/admin-web dev
```

默认访问地址为 [http://127.0.0.1:5173](http://127.0.0.1:5173)。

### 运行测试

运行完整单元测试：

```bash
PYTHONPATH=apps/api-server pytest
```

运行运行时相关改动的推荐本地校验流程：

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
PYTHONPATH=apps/api-server pytest tests/unit tests/integration/test_runtime_api.py
```

### 手动冒烟脚本

人性化的冒烟脚本位于 [`tests/scripts`](./tests/scripts)。

常见流程：

- `tests/scripts/create-sandbox.sh`：创建沙箱并打印所需的 ID 和后续 URL
- `tests/scripts/get-session-url.sh`：创建或复用沙箱，并打印可直接打开的 session URL
- `tests/scripts/browser-smoke.sh`：将浏览器元数据以及窗口和页面截图保存到 `tests/scripts/.artifacts/`
- `tests/scripts/files-smoke.sh`：针对 `/workspace` 演练文件 API
- `tests/scripts/restart-browser.sh`：重启 Chromium 并在前后保存浏览器信息
- `tests/scripts/full-manual-tour.sh`：执行最有价值的创建 + 截图 + 文件 + session 端到端流程
- `tests/scripts/cleanup-sandbox.sh`：当传入 `SANDBOX_ID=...` 时删除沙箱

示例：

```bash
tests/scripts/full-manual-tour.sh
```

如果你的 API 服务器不在 `http://127.0.0.1:8000`，请设置：

```bash
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
```

业务 API 需要携带 admin bearer token。请设置：

```bash
export VERGE_BROWSER_TOKEN="<admin-token>"
```

### 清理开发容器

快速清理：

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
docker rm -f verge-api 2>/dev/null || true
```

完整清理，包括持久化数据：

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
rm -rf .local/sandboxes
```

使用 Docker Compose：

```bash
docker compose -f deployments/docker-compose.yml down
docker compose -f deployments/docker-compose.yml down -v
```

## 运行时镜像

运行时镜像包含：

- Chromium
- xdotool
- supervisor
- 一个小型 TCP 中继，用来稳定暴露 CDP 入口，即使 Chromium 自身监听的是容器内调试端口

当前支持两种运行时变体：

- `xvfb_vnc`：Xvfb + Openbox + x11vnc + noVNC / websockify
- `xpra`：Xpra server + HTML5 客户端资源

## API 接口

当前 API 采用 `/sandbox/{sandbox_id}/...` 路由模型。

详细端点文档位于 [`docs/api.md`](./docs/api.md)。

SDK 与 CLI 使用示例位于 [`docs/cli-sdk.md`](./docs/cli-sdk.md)。

## 范围

Verge Browser 聚焦于浏览器控制：

- 浏览器生命周期：create、pause、resume、delete
- 基于 CDP 的浏览器自动化
- GUI 截图与输入动作
- 基于 `xvfb_vnc` 或 `xpra` 的人工接管
- 通过沙箱工作区进行文件交换

不提供任意命令执行，这是刻意收窄的边界，用来控制系统复杂度和攻击面。

## 当前加固重点

- 更强的 Docker 生命周期管理和基于健康检查的状态转换
- 面向生产的浏览器崩溃恢复和降级状态处理
- 文件与浏览器的集成覆盖
- 更广泛的端到端与故障模式覆盖

## 开发说明

- 项目目标 Python 3.11+。
- API 服务器使用 FastAPI 实现。
- WebSocket 代理围绕 CDP 和 session 中继用例设计。
- 文件操作严格限制在沙箱工作区根目录内。
- 容器化 API 部署通过 `/var/run/docker.sock` 管理宿主机上的 sandbox 容器。
- 当前实现优先考虑务实的 MVP 结构，而非过早进入多租户编排。

## 许可证

本仓库中的原创源码采用 MIT 许可证。参见 [LICENSE](./LICENSE)。

但构建后的运行时产物可能包含按其他许可证发布的第三方组件。其中 `runtime-xpra` 镜像会安装 Xpra；Xpra 采用 GPL v2 或更高版本许可证，并继续受其自身许可证约束。

对外分发容器镜像前，请同时查看 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) 与 [docs/open-source-compliance.md](./docs/open-source-compliance.md)。
