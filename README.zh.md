# Verge Browser

[English](./README.md) | 中文

Verge Browser 是一个面向智能体工作流的浏览器沙箱平台。

它提供了一个单会话隔离运行时环境，包含：

- 真实的 GUI Chromium 浏览器实例
- Chrome 开发者协议（CDP）访问
- VNC / noVNC 人工接管
- GUI 级截图和输入自动化
- 共享的 `/workspace` 文件系统
- 统一的 REST 和 WebSocket 控制平面

## 状态

本仓库正在积极开发中。

当前代码库包含一个可运行的运行时镜像，以及主浏览器沙箱循环的端到端控制路径：

- 运行时容器启动，包含 Chromium、Xvfb、Openbox、x11vnc、websockify 和 CDP 中继
- 通过 API 创建沙箱
- 持久化沙箱元数据，并在服务启动时恢复为 `STOPPED`
- 支持复用现有工作目录的 `pause` / `resume`
- 真实窗口截图
- 通过 CDP 进行真实页面截图
- 通过 `xdotool` 执行 GUI 操作
- 基于票据的 VNC 入口，支持 noVNC 资源代理

某些部分尚未达到生产级成熟度，尤其是基于健康检查的生命周期流转、浏览器崩溃恢复语义以及更广泛的集成/E2E 覆盖率。

## 为何存在

大多数浏览器自动化系统专注于无头页面控制。这对于需要结合以下功能的智能体工作流来说是不够的：

- 通过 CDP 进行浏览器自动化
- 对整个浏览器窗口进行视觉推理
- 自动化卡住时的人工接管
- 在同一环境内共享文件

Verge Browser 旨在通过一种运行时模型来弥合这一差距，该模型将浏览器、GUI 和文件整合在一个隔离的沙箱中。

## 架构

从高层次看，平台分为两部分：

1. API 服务器
   暴露 REST 和 WebSocket 端点，用于沙箱生命周期、浏览器控制、文件、CDP 代理和基于票据的 VNC 访问。

2. 沙箱运行时
   在单个隔离容器中运行 Chromium、Xvfb、Openbox、x11vnc、websockify 和 supervisor，并共享 `/workspace`。

```text
客户端 / 智能体 / 人工
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
| Xvfb + Openbox + Chromium + x11vnc            |
| websockify + supervisor + /workspace          |
+-----------------------------------------------+
```

## 当前能力

本仓库目前实现了：

- 基于 Docker 运行时启动的沙箱创建/获取/暂停/恢复/删除流程
- 工作目录元数据持久化，以及停止态沙箱的启动恢复
- 浏览器信息、视口、截图、操作、重启和 CDP 代理
- 基于票据的 VNC 入口，支持 noVNC 资源代理
- 工作空间范围的文件列表、读取、写入、上传、下载和删除操作
- 运行时 Dockerfile、supervisor 配置、启动脚本和基于 Docker 的集成测试

## 仓库结构

```text
apps/
  api-server/         FastAPI 应用程序
  sandbox-runtime/    运行时脚本和 supervisor 配置
deployments/          本地部署资源
docker/               运行时容器构建文件
tests/                单元测试
```

## 快速开始

### 方式一：本地开发

**前置依赖：**

- Python 3.11+
- Docker（用于构建和运行运行时镜像）

**1. 安装依赖**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**2. 构建运行时镜像**

```bash
docker build -f docker/runtime-image.Dockerfile -t verge-browser-runtime:latest .
```

**3. 启动 API 服务器**

```bash
uvicorn app.main:app --app-dir apps/api-server --host 0.0.0.0 --port 8000 --reload
```

API 会监听在 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

### 方式二：Docker 部署（推荐）

完全使用 Docker 运行 API 服务和运行时。

```bash
# 构建运行时镜像（包含 Chromium、VNC 等）
docker build -f docker/runtime-image.Dockerfile -t verge-browser-runtime:latest .

# 构建 API 服务器镜像
docker build -f docker/api-server.Dockerfile -t verge-browser-api:latest .

# 创建沙箱持久化目录
mkdir -p .local/sandboxes

# 运行 API 服务器容器
docker run -d \
  --name verge-api \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$(pwd)/.local/sandboxes:/app/.local/sandboxes" \
  -e VERGE_SANDBOX_BASE_DIR=/app/.local/sandboxes \
  verge-browser-api:latest
```

API 会监听在 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

### 方式三：Docker Compose

使用提供的 compose 文件快速启动：

```bash
export PROJECT_ROOT="$PWD"
docker compose -f deployments/docker-compose.yml build api runtime-image
docker compose -f deployments/docker-compose.yml up api
```

### 清理开发容器

在本地开发过程中，你可能会积累大量沙箱容器。以下是几种清理方法：

**快速清理 - 移除所有 verge sandbox 容器：**

```bash
# 列出所有受管理的 verge sandbox 容器
docker ps -a --filter "label=verge.managed=true" --format "table {{.ID}}\t{{.Image}}\t{{.Names}}\t{{.Status}}\t{{.Label \"verge.sandbox.id\"}}"

# 停止并移除所有受管理的 verge sandbox 容器
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f

# 如果使用 Docker 运行 API 服务器，也一并清理
docker rm -f verge-api 2>/dev/null || true
```

**完整清理 - 移除容器和持久化数据：**

```bash
# 移除所有受管理的运行时容器
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f

# 移除持久化的沙箱数据（⚠️ 警告：这会删除所有沙箱文件）
rm -rf .local/sandboxes
```

**使用 Docker Compose：**

```bash
# 停止并移除所有容器
docker compose -f deployments/docker-compose.yml down

# 同时移除卷和持久化数据
docker compose -f deployments/docker-compose.yml down -v
```

**⚠️ 一键重置开发环境（危险操作）：**

> **警告：此命令会永久删除 `.local/sandboxes/` 目录下的所有沙箱文件，包括下载文件、上传文件和浏览器配置文件。运行前请确保已备份重要数据。**

```bash
docker ps -aq --filter "label=verge.managed=true" | xargs -r docker rm -f && rm -rf .local/sandboxes
```

### 运行测试

```bash
PYTHONPATH=apps/api-server pytest
```

包含基于 Docker 的集成测试：

```bash
PYTHONPATH=apps/api-server pytest -m integration
```

### 手动冒烟脚本

人性化的冒烟脚本位于 [`tests/scripts`](./tests/scripts)。

常见流程：

- `tests/scripts/create-sandbox.sh`
  创建沙箱并打印所需的 ID 和后续 URL。
- `tests/scripts/get-vnc-url.sh`
  始终创建一个新沙箱并打印可直接打开的浏览器就绪 noVNC URL。
- `tests/scripts/browser-smoke.sh`
  将浏览器元数据以及窗口和页面截图保存到 `tests/scripts/.artifacts/`。
- `tests/scripts/restart-browser.sh`
  重启 Chromium 并在重启前后保存浏览器信息。
- `tests/scripts/full-manual-tour.sh`
  运行最有用的创建 + 截图 + 文件 + VNC 端到端流程。
- `tests/scripts/cleanup-sandbox.sh`
  当传入 `SANDBOX_ID=...` 时删除沙箱。

示例：

```bash
tests/scripts/full-manual-tour.sh
```

如果你的 API 服务器不在 `http://127.0.0.1:8000`，请设置：

```bash
export BASE_URL="http://127.0.0.1:8000"
```

业务 API 现在要求携带 admin bearer token。请设置：

```bash
export AUTH_TOKEN="<admin-token>"
```

## 运行时镜像

运行时镜像包含：

- Chromium
- Xvfb
- Openbox
- x11vnc
- noVNC / websockify
- xdotool
- supervisor

它还包含一个小型 TCP 中继，使平台能够暴露一个稳定的 CDP 入口点，即使 Chromium 本身在内部调试端口上监听。

## API 接口

API 遵循 [`docs/tech.md`](./docs/tech.md) 中的 `/sandboxes/{sandbox_id}/...` 路由模型。

详细的端点文档位于 [`docs/api.md`](./docs/api.md)。

SDK 和 CLI 的使用示例位于 [`docs/cli-sdk.md`](./docs/cli-sdk.md)。

## 仍在进行中的工作

在 [`docs/tech.md`](./docs/tech.md) 中描述的完整 V1 目标之前，以下领域仍需要更深入的实现工作：

- 更强的 Docker 生命周期管理和基于健康检查的状态转换
- 生产就绪的浏览器崩溃恢复和降级状态处理
- 文件/浏览器集成覆盖
- 更广泛的端到端和故障模式覆盖

## 开发说明

- 项目目标 Python 3.11+。
- API 服务器使用 FastAPI 实现。
- WebSocket 代理围绕 CDP 和 VNC 中继用例设计。
- 文件操作限制在沙箱工作空间根目录内。
- 容器化 API 部署通过挂载 `/var/run/docker.sock` 来管理宿主机上的 sandbox 容器。
- 当前实现优先考虑实用的 MVP 结构，而非过早的分布或多租户编排。

## 路线图

预期的实现顺序仍然是：

1. 强化运行时容器，直到 Chromium、CDP 和 VNC 稳定可靠。
2. 将 Playwright / CDP 兼容性验证扩展到低级冒烟检查之外。
3. 加强 VNC 会话管理和 WebSocket 生命周期行为。
4. 扩展文件和集成测试覆盖。
5. 为浏览器重启和运行时降级添加故障注入测试。
6. 添加部署优化、可观测性和生产加固。

## 许可证

本项目采用 MIT 许可证。参见 [LICENSE](./LICENSE)。
