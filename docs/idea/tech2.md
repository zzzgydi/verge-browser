# Verge Browser 技术方案 v2

## 1. 文档定位

本文档基于 `docs/spec/req.md` 的产品愿景，对 `docs/spec/t1.md` 和 `docs/spec/t2.md` 两份技术方案进行辩证分析，取两者之长，形成一份可直接指导开发的综合性技术文档。

---

## 2. 愿景回顾

来自 `req.md` 的核心目标（按优先级排序）：

| 优先级 | 目标                | 关键要求                                      |
| ------ | ------------------- | --------------------------------------------- |
| P0     | 可自部署            | 单一 admin token，配置即用，拒绝匿名          |
| P0     | 可被人管理          | Vite + React 管理页，token 登录后查看所有实例 |
| P1     | 可被 agent 方便使用 | SDK/CLI，高度封装，可包装为 skills            |
| P1     | 人机协同            | VNC + agent 协作，扫码/登录等人工操作         |
| P2     | 自动化能力          | Playwright/CDP 集成，参考 agent-browser       |

---

## 3. 方案辩证分析

### 3.1 T1 方案特点

**优点：**

- 深度借鉴 agent-browser，提出 Semantic Locators、Accessibility Tree 等先进概念
- 关注 agent-first 体验，强调 snapshot + ref 操作模式
- 考虑 Skills/MCP 集成，面向 AI Agent 生态
- 详细的 CLI 命令设计（`verge find --role button --click`）

**不足：**

- 权限模型过于复杂（区分 admin/普通用户、owner 权限检查），与 req.md "简单鉴权" 诉求有冲突
- Phase 1 就做权限分级，实施成本较高
- Accessibility Tree 实现较重，依赖 CDP Accessibility domain
- CLI 命名 `verge` 与 req.md 要求的 `verge-browser` 不符

### 3.2 T2 方案特点

**优点：**

- 鉴权设计极简：单一 admin token，无 JWT、无多角色，符合 "简单部署即可用"
- 清晰的三层入口架构：部署者(admin token) → 人类(Web 控制台) → agent(SDK/CLI)
- 强调现状与愿景的差距分析，优先级判断合理
- 明确的实施顺序：先管理入口，再 agent 入口，再高级能力
- CLI 命名 `verge-browser`，支持 `VERGE_BROWSER_TOKEN` 环境变量，符合 req.md 要求

**不足：**

- 对 agent-first 体验的细节设计不如 T1 深入
- 未明确提及 Accessibility Tree/Semantic Locators 等高级能力
- CLI 命令设计相对简单，缺乏 agent-browser 风格的语义操作层

### 3.3 取舍与融合

| 维度         | 采用方案  | 理由                                                           |
| ------------ | --------- | -------------------------------------------------------------- |
| 鉴权模型     | **T2**    | 单一 admin token 最符合 req.md "简单鉴权" 诉求                 |
| 架构分层     | **T2**    | 三层入口（部署者→人类→agent）清晰合理                          |
| Agent 交互层 | **T1+T2** | 优先实现 T2 的基础 SDK/CLI，再逐步引入 T1 的 Semantic Locators |
| 实施顺序     | **T2**    | 先管理入口，再 agent 入口，符合 MVP 思维                       |
| CLI 命名     | **T2**    | `verge-browser` 符合 req.md 明确要求                           |
| Sandbox 标识 | **融合**  | 支持 `alias`，CLI/SDK 支持 `id_or_alias`                       |

---

## 4. 核心设计决策

### 4.1 鉴权：单一 Admin Token（极简设计）

**原则：** 只做最小实现，不追求产品级 IAM。

```python
# 服务端配置
VERGE_ADMIN_AUTH_TOKEN=your-secure-random-token  # 必填，无默认值

# 请求方式
Authorization: Bearer <admin-token>

# 校验规则
- Token 错误或缺失 → 401 Unauthorized
- 不再允许 anonymous 访问
- 仅 /healthz 允许匿名

# CLI/SDK 使用
export VERGE_BROWSER_TOKEN=<admin-token>  # 优先读取
verge-browser sandbox ls                   # 自动使用环境变量
verge-browser --token <token> sandbox ls   # 命令行覆盖
```

**明确不做：** JWT、账号体系、多 token、多角色、token 刷新。

### 4.2 三层产品入口

```
┌─────────────────────────────────────────────────────────────┐
│  第一层：部署者（DevOps/User）                                 │
│  ├── 配置 VERGE_ADMIN_AUTH_TOKEN                             │
│  └── 启动服务                                                 │
├─────────────────────────────────────────────────────────────┤
│  第二层：人类操作者（Web 控制台）                              │
│  ├── 访问 /admin，输入 token 登录                             │
│  ├── 查看所有 sandbox 列表                                    │
│  ├── 创建/暂停/恢复/删除 sandbox                              │
│  └── 一键打开 VNC（自动申请 ticket）                          │
├─────────────────────────────────────────────────────────────┤
│  第三层：Agent（SDK/CLI）                                     │
│  ├── SDK: verge-browser Python 包                            │
│  ├── CLI: verge-browser 命令行工具                           │
│  └── Skills: 可包装为 Claude Code skills                     │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Sandbox 标识：ID + Alias 双轨制

```python
# SandboxRecord 扩展字段
class SandboxRecord:
    id: str                    # 系统生成，如 "sb_abc123"
    alias: str | None          # 用户自定义，如 "shopping-session"
    name: str | None           # 人类可读名称
    owner: str = "admin"       # 单 admin 模式下固定
    status: SandboxStatus
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime
    viewport: Viewport
    default_url: str | None
    tags: list[str]
    # ... runtime 相关字段
```

**使用规则：**

- 所有面向用户的接口支持 `id_or_alias` 查询
- Alias 在实例范围内唯一（不强制全局唯一，简化实现）
- 未指定 alias 时，可自动分配如 "sandbox-1", "sandbox-2"

### 4.4 人机协同工作流

```
┌─────────┐    1.创建 sandbox     ┌─────────────────┐
│  Agent  │ ────────────────────> │ Verge Browser   │
│  (CLI)  │                       │  (API Server)   │
└────┬────┘                       └────────┬────────┘
     │                                      │
     │ 2.获取 CDP URL + VNC ticket          │
     │ <────────────────────────────────────┘
     │
     │ 3.通过 CDP 自动化操作（如到登录页）
     │ ────────────────────────────────────────>
     │
     │ 4.遇到验证码/扫码，输出 VNC URL 给人类
     │
     ▼
┌─────────┐    5.人工操作完成       ┌─────────────────┐
│  Human  │ ────────────────────> │  Browser (VNC)  │
│ (VNC)   │    登录/验证码/扫码     │                 │
└─────────┘                       └─────────────────┘
     │
     │ 6.通知 agent 继续
     ▼
┌─────────┐    7.继续自动化操作     ┌─────────────────┐
│  Agent  │ ────────────────────> │  Browser (CDP)  │
│  (恢复)  │                       │                 │
└─────────┘                       └─────────────────┘
```

---

## 5. 技术架构

### 5.1 项目结构

```
verge-browser/
├── apps/
│   ├── api-server/              # FastAPI 控制面
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py        # VERGE_ADMIN_AUTH_TOKEN 配置
│   │   │   ├── auth/
│   │   │   │   └── simple.py    # 极简 token 校验
│   │   │   ├── routes/
│   │   │   │   ├── sandboxes.py # 列表/创建/删除
│   │   │   │   ├── browser.py
│   │   │   │   ├── vnc.py
│   │   │   │   └── files.py
│   │   │   └── services/
│   │   └── tests/
│   │
│   ├── sandbox-runtime/         # Docker 运行时
│   │   ├── scripts/
│   │   └── supervisor/
│   │
│   └── web-console/             # 【新增】Vite + React 管理页
│       ├── package.json
│       ├── vite.config.ts
│       └── src/
│           ├── pages/
│           │   ├── Login.tsx
│           │   ├── SandboxList.tsx
│           │   └── SandboxDetail.tsx
│           ├── api/
│           └── components/
│
├── packages/
│   ├── verge-sdk/               # 【新增】Python SDK
│   │   ├── verge/
│   │   │   ├── __init__.py
│   │   │   ├── client.py        # VergeClient
│   │   │   ├── sandbox.py       # Sandbox 句柄
│   │   │   └── errors.py
│   │   └── pyproject.toml
│   │
│   └── verge-cli/               # 【新增】CLI 工具
│       ├── verge_cli/
│       │   ├── __init__.py
│       │   ├── main.py          # typer 入口
│       │   └── commands/
│       │       ├── sandbox.py
│       │       └── browser.py
│       └── pyproject.toml
│
├── examples/                    # 【新增】示例代码
│   ├── basic_sdk.py
│   ├── playwright_integration.py
│   └── human_handoff.py         # 人机协作示例
│
├── docker/
│   └── runtime-image.Dockerfile
│
└── docs/
    ├── spec/
    │   ├── req.md
    │   ├── t1.md
    │   ├── t2.md
    │   └── tech2.md             # 本文档
    ├── api.md
    └── deployment.md            # 【新增】部署指南
```

### 5.2 技术栈选择

| 组件        | 选择                    | 理由                                 |
| ----------- | ----------------------- | ------------------------------------ |
| 管理页构建  | Vite 5                  | req.md 明确要求，开发体验好          |
| 管理页框架  | React 18 + TypeScript   | req.md 明确要求，生态成熟            |
| 管理页 UI   | Ant Design 或 shadcn/ui | 组件丰富，管理页风格匹配             |
| 状态管理    | React Query             | 服务端状态管理，缓存友好             |
| HTTP 客户端 | axios/fetch             | 标准化                               |
| SDK/CLI     | Python                  | 与 API Server 同语言，agent 生态主流 |
| CLI 框架    | typer                   | 类型友好，自动生成帮助               |
| 权限校验    | 字符串比对              | 极简，无需 JWT 库                    |

### 5.3 API 演进

**新增接口：**

```
# Sandbox 管理
GET    /sandboxes                      # 列表（含 alias, status 等）
GET    /sandboxes/{id_or_alias}        # 详情
POST   /sandboxes                      # 创建（支持 alias）
DELETE /sandboxes/{id_or_alias}        # 删除
POST   /sandboxes/{id_or_alias}/pause
POST   /sandboxes/{id_or_alias}/resume

# 管理页专用
GET    /admin/sandboxes                # 同上，兼容路径
POST   /vnc/tickets                   # 申请 ticket（已有）
```

**保持不变的接口：**

```
/sandboxes/{id}/browser/*              # 浏览器操作
/sandboxes/{id}/vnc/*                  # VNC 相关
/sandboxes/{id}/files/*                # 文件操作
```

---

## 6. CLI 设计

### 6.1 命令结构

```bash
# 环境配置（推荐）
export VERGE_BROWSER_TOKEN=<admin-token>
export VERGE_BROWSER_URL=http://localhost:8000

# Sandbox 管理
verge-browser sandbox create --alias shopping --width 1440 --height 900
verge-browser sandbox ls                    # 列表
verge-browser sandbox get <id-or-alias>     # 详情
verge-browser sandbox pause <id-or-alias>
verge-browser sandbox resume <id-or-alias>
verge-browser sandbox rm <id-or-alias>

# VNC/CDP
verge-browser sandbox vnc <id-or-alias>     # 申请 ticket 并打开浏览器
verge-browser sandbox cdp <id-or-alias>     # 输出 CDP WebSocket URL

# 浏览器基础操作（基于现有 API）
verge-browser screenshot <id-or-alias> --output file.png
verge-browser action <id-or-alias> click --x 100 --y 200

# 输出格式（面向 agent）
verge-browser sandbox ls --json             # 机器可读输出
verge-browser sandbox get <id> --json
```

### 6.2 设计原则

1. **非交互优先**：所有命令可直接脚本调用，无需 TTY
2. **JSON 输出**：关键命令支持 `--json`，输出稳定结构
3. **环境变量**：`VERGE_BROWSER_TOKEN` 作为默认 token
4. **错误处理**：错误输出到 stderr，退出码非 0
5. **ID/Alias 兼容**：所有涉及 sandbox 的命令支持 `id_or_alias`

---

## 7. SDK 设计

### 7.1 基础使用

```python
from verge import VergeClient

# 自动读取环境变量 VERGE_BROWSER_TOKEN
client = VergeClient(base_url="http://localhost:8000")

# 创建 sandbox
sandbox = client.create_sandbox(alias="shopping", width=1440, height=900)

# 获取 CDP URL 给 Playwright
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(sandbox.cdp_url)
    page = browser.new_page()
    page.goto("https://example.com")

# 截图
screenshot = sandbox.take_screenshot()

# VNC 接管
vnc_url = sandbox.get_vnc_url()  # 自动申请 ticket
print(f"请打开: {vnc_url}")

# 清理
sandbox.delete()
```

### 7.2 上下文管理器

```python
# 自动清理（默认）
with client.sandbox(alias="temp") as sandbox:
    sandbox.goto("https://example.com")
    screenshot = sandbox.screenshot()
    # 退出时自动 delete

# 暂停保留状态
with client.sandbox(alias="persistent", pause_on_exit=True) as sandbox:
    sandbox.goto("https://github.com/login")
    # 用户可通过 VNC 登录，然后 resume
```

### 7.3 类结构

```python
class VergeClient:
    def __init__(self, base_url: str | None = None, token: str | None = None)
    def create_sandbox(self, alias: str | None = None, ...) -> Sandbox
    def list_sandboxes(self) -> list[Sandbox]
    def get_sandbox(self, id_or_alias: str) -> Sandbox

class Sandbox:
    id: str
    alias: str | None
    status: str
    cdp_url: str

    def pause(self) -> None
    def resume(self) -> None
    def delete(self) -> None
    def take_screenshot(self) -> bytes
    def get_vnc_url(self, mode: str = "reusable") -> str

    # 上下文管理器
    def __enter__(self) -> Sandbox
    def __exit__(self, ...) -> None
```

---

## 8. 管理页设计

### 8.1 页面结构

```
/login                          # 登录页（token 输入）
/sandboxes                      # Sandbox 列表
/sandboxes/:id                  # Sandbox 详情
```

### 8.2 登录页

- Token 输入框（密码类型）
- 登录按钮
- Token 本地存储（localStorage）
- 自动跳转（如已有 token）

### 8.3 Sandbox 列表页

- 统计卡片：总数、运行中、已暂停
- 表格：ID, Alias, 状态, 创建时间, 操作
- 操作按钮：查看详情、暂停/恢复、删除、打开 VNC
- 快速创建按钮
- 搜索/筛选

### 8.4 Sandbox 详情页

- 基本信息：ID, Alias, 状态, 创建时间, 视口
- CDP URL：复制按钮
- VNC：打开按钮（自动申请 ticket）
- 文件工作区：入口说明
- 操作：暂停、恢复、重启浏览器、删除

---

## 9. 实施路线图

### Phase 1: 管理入口成型（P0）

目标：人可以部署并使用 Web 控制台管理 sandbox

| 序号 | 任务                  | 验收标准                                                |
| ---- | --------------------- | ------------------------------------------------------- |
| 1.1  | 极简 admin token 鉴权 | 未带 token 请求返回 401；CLI 支持 `VERGE_BROWSER_TOKEN` |
| 1.2  | Sandbox 列表 API      | `GET /sandboxes` 返回包含 alias 的列表                  |
| 1.3  | Sandbox 元数据扩展    | 支持 alias, name, created_at 等字段                     |
| 1.4  | 管理页 MVP            | 登录页、列表页、详情页可用                              |
| 1.5  | VNC 快速接入          | 点击"打开 VNC"自动申请 ticket 并跳转                    |
| 1.6  | 部署文档              | 说明如何配置 token、启动服务、构建前端                  |

**交付标准：**

- 部署后配置 `VERGE_ADMIN_AUTH_TOKEN` 即可启动
- 通过 Web UI 完成：登录 → 创建 sandbox → 打开 VNC → 删除 sandbox

### Phase 2: Agent 入口成型（P1）

目标：agent 可以方便地使用 SDK/CLI

| 序号 | 任务                | 验收标准                                                    |
| ---- | ------------------- | ----------------------------------------------------------- |
| 2.1  | Python SDK 基础     | `create_sandbox`, `list_sandboxes`, `get_sandbox`, `delete` |
| 2.2  | CLI 基础            | `verge-browser sandbox` 子命令可用                          |
| 2.3  | CDP/Playwright 示例 | 官方示例代码可运行                                          |
| 2.4  | 人机协作文档        | 标准工作流文档化                                            |

**交付标准：**

- agent 不必手写 REST 请求
- 可被进一步包装为 skills

### Phase 3: 体验优化（P2）

目标：提升 agent 使用体验，逐步引入高级能力

| 序号 | 任务                       | 说明                                    |
| ---- | -------------------------- | --------------------------------------- |
| 3.1  | CLI JSON 输出              | 所有关键命令支持 `--json`               |
| 3.2  | Semantic Locators（可选）  | 借鉴 agent-browser，snapshot + ref 操作 |
| 3.3  | Accessibility Tree（可选） | `GET /browser/snapshot` 接口            |
| 3.4  | 可观测性                   | 结构化日志、基础指标                    |
| 3.5  | 自动清理策略               | 超时暂停/销毁、最大数量限制             |
| 3.6  | Skills 封装                | Claude Code skills 模板                 |

---

## 10. 借鉴 agent-browser 的关键点

| 借鉴项            | 应用方式                         | 优先级 |
| ----------------- | -------------------------------- | ------ |
| CLI 作为核心入口  | `verge-browser` 是主要交互方式   | P1     |
| `--json` 机器输出 | 所有命令支持稳定 JSON            | P2     |
| Session 概念      | sandbox = 持久会话，pause/resume | P0     |
| 人机协同          | VNC 接管作为标准工作流           | P0     |
| Snapshot/Refs     | 后续可选引入，非当前必需         | P3     |
| Skills 封装       | 基于稳定 CLI/SDK 包装            | P3     |

**不照搬的部分：**

- 本地守护进程模式 → 改为远程 sandbox API
- Rust CLI → Python 与 API Server 统一
- 纯 CLI 交互 → Web 控制台 + CLI 双入口

---

## 11. 风险与应对

| 风险                    | 应对策略                                     |
| ----------------------- | -------------------------------------------- |
| Admin Token 泄露        | 文档强调 HTTPS 部署；未来可升级多 token      |
| Web UI 构建复杂         | 提供预构建镜像或 docker-compose 一键启动     |
| SDK 维护成本            | 先实现核心功能（sandbox 生命周期），控制范围 |
| Accessibility Tree 性能 | 作为可选功能，不影响核心路径                 |

---

## 12. 环境变量汇总

```bash
# API Server（服务端）
VERGE_ADMIN_AUTH_TOKEN=xxx          # 【新增】必填，admin 鉴权 token
VERGE_JWT_SECRET=xxx                # 现有，用于 VNC ticket（可复用）

# CLI/SDK（客户端）
VERGE_BROWSER_TOKEN=xxx             # 【新增】CLI/SDK 默认 token
VERGE_BROWSER_URL=http://localhost:8000  # 【新增】API 地址

# Web Console（构建时）
VITE_API_BASE_URL=/api              # API 前缀
```

---

## 13. 关键判断

1. **鉴权必须极简**：单一 admin token 是 req.md 的核心诉求，不要过早引入多角色

2. **管理页先于高级 CLI**：让人能先用起来，比让 agent 用得爽更重要

3. **id_or_alias 是体验关键**：alias 让用户无需记忆随机 ID，CLI/SDK 必须全链路支持

4. **人机协同是差异化卖点**：VNC 接管能力是区别于 agent-browser 等纯自动化方案的核心优势

5. **Semantic Locators 可以缓行**：虽然先进，但当前坐标操作 + Playwright 已能满足基础需求，可作为 Phase 3 优化项

---

## 14. 下一步行动

立即开始 Phase 1.1：

1. 修改 `app/config.py`，添加 `admin_auth_token` 配置
2. 创建 `app/auth/simple.py`，实现字符串 token 校验
3. 修改 `app/deps.py`，替换现有 JWT 逻辑（或并行提供）
4. 确保未带 token 时返回 401，不再默认 anonymous
5. 更新测试用例

然后依次推进 1.2-1.6，完成 Phase 1 后进入 Phase 2。

---

**文档版本：** v2.0
**最后更新：** 2026-03-11
**基于：** req.md + t1.md + t2.md 综合
