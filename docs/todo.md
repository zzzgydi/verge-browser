# Verge Browser 待办清单

本文档是基于 `docs/tech-0311.md` 的执行清单，按优先级组织。

## P0: 收口到可部署可管理

### 1. 强制 admin token 鉴权

- [ ] 在配置中引入固定 admin token。
- [ ] 移除业务 API 的匿名访问默认路径。
- [ ] 统一未授权返回 `401`。
- [ ] 仅保留探活等少量匿名接口。
- [ ] 为鉴权逻辑补充单元测试。

### 2. 提供 sandbox 列表与详情接口

- [ ] 新增 `GET /sandboxes` 列表接口。
- [ ] 新增 `GET /sandboxes/{sandbox_id}` 详情接口。
- [ ] 补齐状态、时间戳、浏览器/VNC/CDP 基础信息输出。
- [ ] 为列表和详情接口补充测试。

### 3. 引入 alias

- [ ] 在 sandbox 记录模型中增加 `alias` 字段。
- [ ] 支持创建时设置 alias（`POST /sandboxes`）。
- [ ] 支持更新 alias（`PATCH /sandboxes/{sandbox_id}`）。
- [ ] 对 alias 冲突和非法值做校验。
- [ ] 在 API 输出中稳定返回 alias 字段。
- [ ] CLI/SDK 支持使用 `id_or_alias` 访问 sandbox。

### 4. 实现管理页 MVP

- [ ] 新建 `Vite + React` 前端工程。
- [ ] 实现 token 登录页。
- [ ] 实现 sandbox 列表页。
- [ ] 实现 sandbox 详情页。
- [ ] 接入创建、暂停、恢复、删除、打开 VNC。
- [ ] 处理 token 存储与统一错误展示。

## P1: 建立 agent 入口层

### 5. Python SDK

- [ ] 提供 `VergeClient`。
- [ ] 封装 sandbox 创建、查询、删除、暂停、恢复。
- [ ] 封装 alias 解析。
- [ ] 封装 CDP URL 和 VNC URL 获取。
- [ ] 提供稳定异常类型。

### 6. CLI

- [ ] 新建 `verge-browser` CLI。
- [ ] 默认从 `VERGE_BROWSER_TOKEN` 读取 token。
- [ ] 支持 `--json` 输出。
- [ ] 覆盖 sandbox 生命周期、信息查询、VNC/CDP 获取。
- [ ] 提供清晰的退出码与错误信息。

### 7. Agent 工作流示例

- [ ] 补充 Playwright `connect_over_cdp` 示例。
- [ ] 补充人机协同工作流示例（创建 → 自动化 → VNC 接管 → 继续自动化）。
- [ ] 补充 CLI 和 SDK 快速上手文档。

## P2: 增强 agent-first 能力

### 8. 页面快照与语义操作

- [ ] 设计 snapshot 数据结构。
- [ ] 评估 accessibility tree 或等价页面表示方案。
- [ ] 设计 semantic locator API。
- [ ] 设计引用式元素操作协议。

### 9. Skills 集成

- [ ] 设计适合 skills 调用的 CLI 子命令。
- [ ] 补充稳定 JSON 输出样例。
- [ ] 整理常用工作流模板。

## 持续性任务

### 10. 测试与验证

- [ ] 为新增 API 和鉴权逻辑补齐单元测试。
- [ ] 为 alias、列表、管理动作补齐集成测试。
- [ ] 涉及 runtime 行为时执行 runtime 镜像构建与集成测试。

### 11. 文档维护

- [ ] 保持 `docs/tech-0311.md` 与实现一致。
- [ ] 管理页、SDK、CLI 落地后补齐对应使用文档。
