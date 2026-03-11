# Verge Browser 技术方案 v1

## 1. 文档目标

本文档以 `docs/idea/req.md` 为最高约束，吸收 `docs/idea/t1.md` 与 `docs/idea/t2.md` 的有效部分，输出一份更适合作为后续实现依据的统一技术方案。

目标不是继续扩写愿景，而是回答 4 个实际问题：

1. 这个项目接下来到底要先做什么。
2. `t1` 和 `t2` 哪些判断是对的，哪些地方还不够。
3. 现有仓库能力应如何收敛成“人能用、agent 也能用”的产品。
4. 下一阶段的 API、鉴权、管理页、SDK/CLI 应怎么设计，才能小步落地且不把系统做重。

---

## 2. 需求基线

根据 `req.md`，本项目的核心不是做一个“大而全的浏览器平台”，而是做一个可自部署、agent-first、同时支持人类接管的 browser sandbox 系统。

不可偏离的需求有 6 条：

1. 用户可自部署，并在部署时配置单一 admin auth token。
2. 鉴权逻辑要简单、封装好，不做重产品化。
3. 需要一个管理页面，登录后可查看和管理全部 sandbox 实例。
4. 需要 SDK 和 agent 友好的 CLI，名称固定为 `verge-browser`。
5. `VERGE_BROWSER_TOKEN` 是 CLI/SDK 的默认 token 来源；请求不带 token 时应返回 `401`，不能默认为 anonymous。
6. 每个 sandbox 需要支持 `alias`，便于人类和 agent 以稳定名称访问。

补充理解：

- 人类主路径是 VNC 接管，用于扫码、登录、验证码等操作。
- agent 主路径是 Playwright/CDP 自动化。
- 产品方向应对齐 `agent-browser` 的 agent-first 使用体验，但底层形态仍是远程 sandbox 服务，而不是本地浏览器工具。

---

## 3. 对 t1 和 t2 的辩证结论

## 3.1 t1 的价值与不足

`t1` 的优点：

- 任务拆解直接，工程可执行性强。
- 能迅速把需求翻译成模块清单，例如 admin 鉴权、Web UI、SDK/CLI。
- 对 `agent-browser` 的借鉴方向是对的，特别是 semantic locator、snapshot、CLI/skills 这些点。

`t1` 的不足：

- 更像待办列表，不够像“技术决策文档”。
- 默认沿着“补功能模块”的思路展开，但没有足够强调优先级收口。
- 对现有代码现状的约束不够强，例如当前 API 仍以 `/sandboxes/{sandbox_id}` 为主轴，文档里有些地方已经提前滑向“平台化产品设计”。
- 对“先把入口做对，再补 agent 高层能力”的顺序论证不足。

判断：`t1` 适合作为实施 backlog 的素材，不适合作为最终技术基线。

## 3.2 t2 的价值与不足

`t2` 的优点：

- 对项目现状判断更准确，能看清当前强项在 runtime 和底层控制面，弱项在产品入口层与 agent 接入层。
- 明确指出当前匿名访问默认通过，这和 `req.md` 冲突。
- 把“人机协同”定义成同一个 sandbox 的两种控制面，而不是两个独立产品，这个判断正确。
- 优先级更清晰，知道下一步最缺的是统一入口，而不是继续增加零散 endpoint。

`t2` 的不足：

- 偏战略和诊断，缺少足够细的接口与模块落地方案。
- 对 SDK/CLI 的设计方向是对的，但与当前仓库的实现边界还差一层“怎么逐步接进去”。
- 讨论面较广，若直接照做，容易在 P1 阶段同时拉起过多工作面。

判断：`t2` 更适合作为路线判断依据，但仍需要补充工程收敛。

## 3.3 统一结论

最终方案应采用：

- `t2` 的优先级判断与问题定义
- `t1` 的任务拆解与能力设计

也就是说：

- 先用 `t2` 决定“先做什么”
- 再用 `t1` 决定“具体做成什么样”

---

## 4. 当前系统现状与差距

结合当前代码，现状可以明确分成两部分。

### 4.1 已有能力

仓库已经具备一个可运行的 browser sandbox MVP：

- Docker runtime 已打通，Chromium 运行在 Xvfb/Openbox 中。
- 支持 sandbox 的创建、删除、暂停、恢复、浏览器重启。
- 支持 VNC/noVNC 接管与 ticket 机制。
- 支持 CDP WebSocket 代理，可供 Playwright `connect_over_cdp` 使用。
- 支持 screenshot、GUI actions、文件读写/上传/下载。
- 支持 sandbox 元数据落盘与重启恢复。

这说明底层能力并不是当前瓶颈。

### 4.2 关键差距

当前与 `req.md` 的核心差距有 5 个：

1. 鉴权模型不对  
   当前 `apps/api-server/app/deps.py` 中，无 `Authorization` 时默认返回 `anonymous`，这与“业务 API 未带 token 直接 401”冲突。

2. 缺少管理入口  
   没有管理页，也没有面向 dashboard 的列表接口。

3. 缺少 alias 与实例管理视图  
   当前 `SandboxRecord` 没有正式的 `alias` 字段，只有 `metadata`，不利于统一管理和 CLI 访问。

4. 缺少 agent 入口层  
   目前只有 REST/WS 原子能力，没有 SDK、CLI、稳定 JSON 输出、也没有面向 LLM 的高层浏览器操作抽象。

5. 人机协同流程没有产品化  
   虽然技术上已经能申请 VNC ticket，但“agent 创建实例 -> 人类接管 -> agent 继续”的主工作流还没有被包装成简单路径。

---

## 5. 核心技术判断

本项目下一阶段应遵循以下判断。

### 5.1 不做复杂身份系统，只做极简固定 token

这是 `req.md` 的明确要求，也是当前阶段最合理的约束。

因此：

- 服务端只接受一个 admin token。
- 所有业务 API 默认要求 `Authorization: Bearer <token>`。
- 未携带或错误 token 一律返回 `401`。
- `/healthz` 是少数可匿名访问的接口。
- 不引入 JWT 登录流、用户表、刷新 token、RBAC。

结论：鉴权要“小而硬”，不是“灵活而复杂”。

### 5.2 继续保持 `/sandboxes/{sandbox_id}/...` 作为 API 主轴

AGENTS.md 已明确要求保持 `/sandboxes/{sandbox_id}/...` 路由模型，这个约束应保留。

新增能力应围绕这一主轴补齐，而不是另起一套资源模型。建议新增：

- `GET /sandboxes`
- `GET /sandboxes/{sandbox_id}`
- `PATCH /sandboxes/{sandbox_id}` 用于更新 alias / metadata
- 保持现有 browser / files / vnc 子路由不变

alias 是“查找入口”，不是替代主资源 ID 的底层主键。

### 5.3 管理页先做 MVP，不追求完整产品后台

管理页的任务只有一个：让用户部署后能立即管理自己实例。

MVP 只需要：

- token 登录页
- sandbox 列表页
- sandbox 详情页

不需要首版就引入：

- 多角色
- 多租户
- 复杂筛选面板
- 实时大盘
- 富文本日志系统

### 5.4 SDK/CLI 必须以 agent 使用成本最小为标准

SDK/CLI 不应只是 REST wrapper，而应把以下细节吞掉：

- token 注入
- alias 到 sandbox_id 的解析
- VNC ticket 申请
- CDP URL 组装
- 错误映射
- 适合 skills 消费的稳定 JSON 输出

结论：agent 入口层的价值在“缩短工作流”，不在“多一层封装”。

### 5.5 高层浏览器语义能力应分阶段引入

`t1` 中的 snapshot、semantic locator、引用式操作都值得做，但不应和 P0 的管理入口建设绑死。

因此建议分层：

- P0：先把 sandbox 生命周期管理、VNC/CDP 接入、alias、强制鉴权跑顺
- P1：再补 agent-first 浏览器语义层

这样风险更低，也更符合当前代码基础。

---

## 6. 统一方案

## 6.1 总体架构

下一阶段系统由 4 层组成：

### A. Runtime 层

继续沿用当前容器 runtime，不做架构重写。

职责：

- 启动 Chromium/Xvfb/Openbox
- 暴露 CDP / noVNC / 文件工作区
- 支撑 pause/resume/restart 等生命周期动作

### B. Control Plane API 层

继续使用 FastAPI，负责：

- token 校验
- sandbox 生命周期管理
- browser/files/vnc 入口
- 面向管理页与 CLI/SDK 的 JSON API

### C. Admin Web UI 层

新增 `Vite + React` 管理页，负责：

- token 登录与保存
- sandbox 列表与详情管理
- 一键进入 VNC
- 展示 CDP 与基础状态

### D. Agent Access 层

新增 SDK 与 CLI，负责：

- 面向脚本和 skills 暴露稳定接口
- 封装 VNC/CDP/文件/生命周期
- 后续承接 snapshot 与 semantic actions

这四层里，当前缺的是 C 和 D，A/B 基本已经成型。

---

## 6.2 数据模型调整

建议在 `SandboxRecord` 中正式增加以下字段：

- `alias: str | None`
- `owner: str | None`
- `default_url: str | None`
- `last_active_at: datetime | None`
- `last_runtime_error: str | None`
- `tags: list[str] = []`

设计原则：

- `id` 仍是系统主键。
- `alias` 是人类和 CLI 的主要可读标识。
- `owner` 当前可以固定为 `"admin"`，先为后续扩展留字段，但不做多用户逻辑。
- `metadata` 继续保留，用于非核心扩展字段。

别名约束：

- alias 在实例范围内必须唯一。
- 建议字符集限制为小写字母、数字、`-`，便于 CLI 与日志处理。
- 所有 CLI 命令支持 `id_or_alias` 输入。

---

## 6.3 鉴权方案

### 服务端配置

在配置中新增：

- `VERGE_ADMIN_AUTH_TOKEN`

行为要求：

- 生产和开发环境都可使用同一模式。
- 如果未配置 `VERGE_ADMIN_AUTH_TOKEN`，服务启动应失败。
- `jwt_secret` 不再作为主认证机制入口。

### 请求校验

统一规则：

- 请求头必须是 `Authorization: Bearer <token>`
- token 不存在、格式错误、值不匹配，均返回 `401`
- WebSocket 连接同样校验 Bearer token
- 所有业务 API 不允许匿名访问
- `/healthz` 可匿名，因为它属于存活探针而非业务接口

这会替代当前 `get_current_subject()` / `get_ws_subject()` 中的 anonymous fallback。

### 客户端约定

SDK/CLI 默认按以下优先级取 token：

1. 显式参数 `--token` 或构造参数
2. 环境变量 `VERGE_BROWSER_TOKEN`

若两者都没有，则本地直接报错，不发匿名请求。

---

## 6.4 API 方案

### P0 必需新增或调整的接口

#### 1. Sandbox 列表

`GET /sandboxes`

返回字段建议包括：

- `id`
- `alias`
- `status`
- `created_at`
- `updated_at`
- `viewport`
- `default_url`
- `last_runtime_error`
- `vnc_ready`
- `cdp_ready`

这个接口是管理页和 CLI 的核心入口。

#### 2. Sandbox 创建

`POST /sandboxes`

请求建议支持：

- `alias`
- `width`
- `height`
- `default_url`
- `metadata`

其中 alias 首次创建即可写入。

#### 3. Sandbox 更新

`PATCH /sandboxes/{sandbox_id}`

首版只允许更新：

- `alias`
- `default_url`
- `metadata`
- `tags`

避免为了改 alias 再设计额外 endpoint。

#### 4. Sandbox 详情

保留 `GET /sandboxes/{sandbox_id}`，但返回体应比当前更完整，至少补齐：

- alias
- metadata
- default_url
- readiness 信息
- runtime error

#### 5. VNC 入口保持不变

保持：

- `POST /sandboxes/{sandbox_id}/vnc/tickets`
- `GET /sandboxes/{sandbox_id}/vnc/?ticket=...`

但应在 Web UI 和 SDK/CLI 中封装为更易用的“open vnc”动作。

---

## 6.5 管理页面方案

前端路径建议：

`apps/admin-web`

技术栈：

- Vite
- React
- TypeScript

页面结构：

### 1. 登录页

功能：

- 输入 admin token
- 保存到 `localStorage`
- 注入后续请求头

### 2. Sandbox 列表页

展示：

- 总数 / 运行中 / 已停止
- 列表表格
- alias、id、状态、创建时间、分辨率
- 操作按钮：详情、VNC、暂停、恢复、删除

### 3. Sandbox 详情页

展示：

- 基本信息
- alias / id / 状态 / 创建时间
- CDP URL
- VNC 按钮
- 截图预览
- 文件区入口说明
- restart browser / pause / resume / delete 操作

前端原则：

- token 只做本地保存，不做复杂登录态。
- 页面只消费现有 API，不在前端引入业务状态机。
- 首版不追求 SSR，也不需要复杂 UI 框架绑定。

---

## 6.6 SDK 与 CLI 方案

### SDK

建议先做 Python SDK，路径可为：

`packages/verge-browser-py`

核心对象：

- `VergeClient`
- `SandboxHandle`

最小接口：

- `create_sandbox()`
- `list_sandboxes()`
- `get_sandbox(id_or_alias)`
- `update_sandbox()`
- `pause()`
- `resume()`
- `delete()`
- `create_vnc_url()`
- `cdp_url()`
- `screenshot()`
- `read_file() / write_file() / upload_file()`

### CLI

CLI 名称固定：

`verge-browser`

CLI 设计参考 `docs/idea/tech2.md`，采用“两层命令面”：

- `sandbox` 层：负责实例生命周期、VNC、CDP、alias 管理
- 直达操作层：负责 screenshot、action，以及后续的 page/element agent-first 命令

这样做的好处是：

- 人类和运维场景可以围绕 `sandbox` 操作
- agent 和脚本场景可以直接调用更短的动作命令
- 命令结构清晰，同时不把首版 CLI 做成过重的交互式工具

基础命令建议：

```bash
export VERGE_BROWSER_TOKEN=<admin-token>
export VERGE_BROWSER_SANDBOX=<id-or-alias>

verge-browser sandbox create --alias <alias>
verge-browser sandbox ls --json
verge-browser sandbox get <id-or-alias> --json
verge-browser sandbox update <id-or-alias> --alias <alias>
verge-browser sandbox vnc <id-or-alias>
verge-browser sandbox cdp <id-or-alias>
verge-browser sandbox pause <id-or-alias>
verge-browser sandbox resume <id-or-alias>
verge-browser sandbox rm <id-or-alias>

verge-browser screenshot <id-or-alias> --output <file>
verge-browser action <id-or-alias> click --x <x> --y <y>
verge-browser action <id-or-alias> type --text <text>

verge-browser screenshot --output <file>
verge-browser action click --x <x> --y <y>
```

CLI 设计约束：

- 默认以非交互式方式工作，适合脚本和 skills 调用
- 默认读取 `VERGE_BROWSER_TOKEN`
- 支持读取 `VERGE_BROWSER_SANDBOX` 作为默认 sandbox
- 支持 `--token` 覆盖环境变量
- 显式传入的 `<id-or-alias>` 优先级高于 `VERGE_BROWSER_SANDBOX`
- 支持 `--json`
- stdout 只输出结果，stderr 输出错误
- 退出码稳定
- 支持 `id_or_alias`

建议的命令分组：

- `verge-browser sandbox ...`
- `verge-browser screenshot ...`
- `verge-browser action ...`
- P1 再补 `verge-browser page ...`
- P1 再补 `verge-browser element ...`

其中：

- `sandbox vnc` 负责申请 ticket，并可选择输出 URL 或直接打开浏览器
- `sandbox cdp` 负责输出可供 Playwright 使用的 CDP WebSocket URL
- `screenshot` 和 `action` 先复用现有 API，优先解决“能方便调用”
- 当命令参数中省略 `<id-or-alias>` 时，CLI 尝试使用 `VERGE_BROWSER_SANDBOX`
- 若命令需要 sandbox 上下文，但参数和 `VERGE_BROWSER_SANDBOX` 都不存在，则本地直接报错

### P1 的 agent-first 能力

在 SDK/CLI 第二阶段再补：

- `page snapshot`
- `element click --ref`
- `element type --ref`
- 可供 LLM 使用的结构化页面摘要

这里应借鉴 `agent-browser`，但实现上可以建立在远程 Playwright/CDP 之上，而不是强行把所有能力都做成 FastAPI 原子接口。

---

## 6.7 人机协同主流程

这是本项目最关键的产品工作流，建议作为文档、SDK、CLI、UI 的统一主线。

标准流程如下：

1. agent 或用户创建 sandbox，并可选设置 alias。
2. agent 通过 CDP / Playwright 执行自动化。
3. 遇到扫码、登录、验证码等步骤时，申请 VNC ticket。
4. 人类打开 noVNC 页面完成接管操作。
5. 人类退出后，agent 继续通过同一 sandbox 会话执行。
6. 结束时按场景选择 delete 或 pause 保留状态。

这条主流程要在三处都能自然表达：

- Web UI 中有“Open VNC”按钮
- CLI 中有 `sandbox vnc`
- SDK 中有 `create_vnc_url()`

---

## 7. 分阶段实施计划

## 7.1 P0

必须先完成：

1. 强制 admin token 鉴权，移除 anonymous fallback。
2. 为 `SandboxRecord` 增加 alias 等关键字段。
3. 提供 `GET /sandboxes` 与 `PATCH /sandboxes/{sandbox_id}`。
4. 搭建管理页 MVP。
5. 打通“一键进入 VNC”的前端与 CLI 封装。
6. 补充部署文档，明确 token 配置与前后端启动方式。

P0 完成后，项目才能真正满足“用户能自己部署并管理实例”。

## 7.2 P1

紧随其后：

1. Python SDK。
2. `verge-browser` CLI。
3. Playwright 官方接入示例。
4. alias 解析、统一 JSON 输出、错误映射。
5. 初版 page snapshot / agent-first 高层浏览器操作。

P1 完成后，项目才能真正满足“agent 方便使用”。

## 7.3 P2

后续增强：

1. 自动清理与配额。
2. 结构化日志与指标。
3. 更细粒度 token。
4. 更强的会话/元素语义层。
5. skills 集成模板。

---

## 8. 非目标

本项目的长期边界也需要明确，不只是“当前阶段先不做”，而是产品方向上就不做以下事项：

- 多用户账号系统
- 多角色权限模型
- 复杂 RBAC
- OAuth / SSO
- 面向公有云 SaaS 的托管产品形态
- 云调度平台
- 大规模集群编排
- 先于 SDK/CLI 的复杂 MCP 设计

也就是说，这个项目的定位会长期保持为：

- 只做 self-hosted
- 默认单管理员模型
- 不演进为多租户平台

后续演进重点应放在 self-hosted 场景下的人机协同、agent-first 体验与部署可用性，而不是平台化账号体系。

---

## 9. 最终结论

如果只用一句话概括本方案：

Verge Browser 的下一阶段，不应继续把重点放在增加底层 browser endpoint，而应把现有 runtime 与控制面能力，收敛成一个“极简强制鉴权 + 管理页 + agent 入口层”的完整产品闭环。

具体采用的路线是：

- 用 `t2` 的判断收紧优先级
- 用 `t1` 的能力设计补足实施细节
- 以 `req.md` 中的 3 个关键词作为验收标准：`self-hosted`、`agent-first`、`human takeover`

当 P0 和 P1 落地后，这个项目才真正从“能工作的 sandbox API”升级为“用户可部署、可管理、可被 agent 高效使用的浏览器基础设施”。
