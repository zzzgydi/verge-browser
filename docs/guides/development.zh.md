# 开发指南

[English](development.md) | 中文

[项目首页](../../README.zh.md) · [部署](deployment.zh.md) · [使用](usage.zh.md) · [开发](development.zh.md)

以下命令均在仓库根目录执行。只需运行服务时，使用[部署指南](deployment.zh.md)。

## 本地开发

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

必须保持开发服务器私有。`--host 0.0.0.0` 监听全部网络接口。

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

API 地址：[http://127.0.0.1:8000](http://127.0.0.1:8000)。
管理页地址：[http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)。

## 开发流程

### 管理页开发

只修改管理页时，可以单独启动 Vite 开发服务器：

```bash
pnpm --dir apps/admin-web dev
```

默认访问地址为 [http://127.0.0.1:5173](http://127.0.0.1:5173)。

### 运行测试

必须在没有业务沙箱的 Docker 环境中运行。
`test_runtime_api.py` 的清理逻辑会删除全部受管容器。

运行测试集：

```bash
PYTHONPATH=apps/api-server pytest
```

运行时改动使用下列本地验证命令：

```bash
docker build -f docker/runtime-xvfb.Dockerfile -t verge-browser-runtime-xvfb:latest .
docker build -f docker/runtime-xpra.Dockerfile -t verge-browser-runtime-xpra:latest .
PYTHONPATH=apps/api-server pytest tests/unit tests/integration/test_runtime_api.py
```

### 手动冒烟脚本

冒烟测试脚本位于 [`tests/scripts`](../../tests/scripts)。

常见流程：

- `tests/scripts/create-sandbox.sh`：创建沙箱并打印所需的 ID 和后续 URL
- `tests/scripts/get-session-url.sh`：创建或复用沙箱，并打印会话 URL
- `tests/scripts/browser-smoke.sh`：将浏览器元数据以及窗口和页面截图保存到 `tests/scripts/.artifacts/`
- `tests/scripts/files-smoke.sh`：针对 `/workspace` 演练文件 API
- `tests/scripts/restart-browser.sh`：重启 Chromium 并在前后保存浏览器信息
- `tests/scripts/full-manual-tour.sh`：运行创建、截图、文件和会话流程
- `tests/scripts/cleanup-sandbox.sh`：当传入 `SANDBOX_ID=...` 时删除沙箱

示例：

```bash
tests/scripts/full-manual-tour.sh
```

API 使用其他地址时，必须把下列变量改为实际地址：

```bash
export VERGE_BROWSER_URL="http://127.0.0.1:8000"
```

管理 API 必须携带管理令牌。设置：

```bash
export VERGE_BROWSER_TOKEN="<admin-token>"
```

### 清理开发容器

执行前，必须确认可以删除全部受管开发容器。
命令会强制删除当前 Docker 中标记为 `verge.managed=true` 的全部容器。

删除容器：

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
docker rm -f verge-api 2>/dev/null || true
```

执行完整清理前，必须备份数据。
下列命令还会删除 `.local/sandboxes` 中的 Profile 和共享文件。

删除容器与持久化数据：

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f
rm -rf .local/sandboxes
```

使用 `down` 停止 Compose 服务。
确认可以删除卷时，再使用 `down -v`：

```bash
docker compose -f deployments/docker-compose.yml down
docker compose -f deployments/docker-compose.yml down -v
```

### 开发说明

- 项目目标 Python 3.11+。
- API 服务器使用 FastAPI 实现。
- WebSocket 代理转发 CDP 和会话连接。
- 文件操作限制在沙箱工作目录内。
- 容器化 API 通过 `/var/run/docker.sock` 管理宿主机上的沙箱容器。
- 当前实现面向单节点使用，不提供多租户编排。

## 项目结构与运行时

### 整体架构

平台分为两部分：

1. API 服务器
   提供 REST 和 WebSocket 端点。端点管理沙箱、浏览器和文件。端点也转发 CDP 和带票据的会话。
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

### 技术说明

项目面向本地开发和单节点部署。

当前源码包含：

- 运行时容器启动，包含 Chromium、Xvfb/Openbox 或 Xpra，以及 CDP 中继
- 通过 API 创建沙箱
- 持久化沙箱元数据。服务启动时重新关联运行中的容器。其他记录保持 `STOPPED`。
- 复用工作目录的 `pause` / `resume`
- 真实窗口截图
- 通过 CDP 截取页面
- 通过 `xdotool` 执行 GUI 操作
- 面向 noVNC 和 Xpra 的票据会话入口
- 工作目录内的文件列表、读取、写入、上传、下载和删除操作
- 管理页构建为静态资源，并由 API 在 `/admin` 路径下提供
- 运行时 Dockerfile、supervisor 配置、启动脚本和基于 Docker 的集成测试

后续加固范围：

- 更强的 Docker 生命周期管理和基于健康检查的状态转换
- 面向生产的浏览器崩溃恢复和降级状态处理
- 文件与浏览器的集成覆盖
- 更广泛的端到端与故障模式覆盖

### 仓库结构

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

### 运行时镜像

运行时镜像包含：

- Chromium
- xdotool
- supervisor
- TCP 中继。它提供稳定的 CDP 入口，转发到 Chromium 的内部调试端口。

当前支持两种运行时变体：

- `xvfb_vnc`：Xvfb + Openbox + x11vnc + noVNC / websockify
- `xpra`：Xpra server + HTML5 客户端资源
