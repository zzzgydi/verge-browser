# 部署指南

[English](deployment.md) | 中文

[项目首页](../../README.zh.md) · [部署](deployment.zh.md) · [使用](usage.zh.md) · [开发](development.zh.md)

服务器部署请使用 [Linux 私有部署指南](headless-linux.md)。下列 Compose 示例用于本地体验，Docker 命令用于手动部署。

## 准备仓库

安装 Docker 和 Docker Compose，并获取源码：

```bash
git clone https://github.com/zzzgydi/verge-browser.git
cd verge-browser
```

后续命令均在仓库根目录执行。

## 本地体验：Docker Compose

下列命令仅用于可信的本地开发环境。
不得将这个开发示例直接暴露到公网。
它向全部网络接口发布 8000 端口，并使用开发密钥。
在仓库根目录执行。

```bash
export PROJECT_ROOT="$PWD"
docker compose -f deployments/docker-compose.yml build api runtime-xvfb runtime-xpra
docker compose -f deployments/docker-compose.yml up api
```

打开 [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin) 开始使用。

本地开发未覆盖 `VERGE_ADMIN_AUTH_TOKEN` 时，可以用 `dev-admin-token` 登录。

服务器部署使用 [Linux 私有部署指南](../../docs/guides/headless-linux.md)。

部署环境变量见 [`docs/env.md`](../../docs/env.md)。

## 手动 Docker 部署

必须保持 API 私有。命令向全部网络接口发布 8000 端口。
公网服务器使用[私有部署指南](../../docs/guides/headless-linux.md)。

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

> **说明**：Linux 主机使用 GPU 加速时，必须在 `docker run` 中加入设备参数。API 容器通过该参数检测显卡：
>
> - **Intel / AMD**：`--device /dev/dri:/dev/dri`
> - **NVIDIA**：`--gpus all`。宿主机必须先安装 [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)。

API 容器与宿主机必须使用相同的项目绝对路径。
运行时容器通过该路径挂载沙箱工作目录。

完整的部署环境变量清单见 [`docs/env.md`](../../docs/env.md)。

服务启动后，按[使用指南](usage.zh.md)创建沙箱。修改源码见[开发指南](development.zh.md)。
