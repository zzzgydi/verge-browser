# 使用指南

[English](usage.md) | 中文

[项目首页](../../README.zh.md) · [部署](deployment.zh.md) · [使用](usage.zh.md) · [开发](development.zh.md)

本指南假设服务已经启动。首次安装请先阅读[部署指南](deployment.zh.md)。

## 手机与异地访问

把 Verge Browser 部署到持续运行的服务器后，个人电脑关机不会停止服务器上的浏览器。
手机可以向已接入 Verge Browser 的 Agent 下达任务；支持远程 API 工具的手机端 Agent 也可以直接接入。
具体接入方式取决于 Agent 客户端，Verge Browser 提供浏览器服务，不自带手机 Agent 应用。

要在个人电脑离线时使用，Agent 的执行环境和访问链路也不能依赖这台电脑。让 Agent 在服务器、云端或受支持的手机端运行，并为它配置可达的服务地址和凭证。只在个人电脑上运行的 Agent 或 SSH 隧道会随电脑离线而中断。

服务器访问配置见 [Linux 部署指南](headless-linux.md#access-from-your-computer)，工具接入见 [SDK / CLI](../cli-sdk.md)与 [API](../api.md)。
手机端 Agent 的兼容性需按所用客户端验证。

## 基本用法

按 [CLI 指南](../../docs/cli-sdk.md)配置 `VERGE_BROWSER_URL` 和 `VERGE_BROWSER_TOKEN`。
示例依赖运行中的 API。

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

把目标动作写入 `actions.json`。格式见 [API 文档](../../docs/api.md)。

执行 GUI 动作：

```bash
verge-browser browser actions test --input ./actions.json
```

获取人工接管链接：

```bash
verge-browser sandbox session test
```

更多命令详见 [`docs/cli-sdk.md`](../../docs/cli-sdk.md)。

## 兼容性与边界

| 能力 | 支持范围与限制 |
| --- | --- |
| Linux 自托管 / Docker | 支持单节点部署。宿主机不依赖桌面。容器内运行图形界面 Chromium。 |
| Playwright / Puppeteer | 通过带票据的 CDP WebSocket 连接，不是 Playwright 协议服务 |
| Codex / Playwright MCP | 通过 CDP 连接外部工具。必须配置客户端和更新票据。不内置 Codex 任务编排。 |
| 人工接管 | noVNC 或 Xpra 操作同一浏览器。接管前，调用方必须停止 Agent 操作。 |
| Profile 与文件持久化 | 暂停和恢复保留磁盘数据。删除沙箱会删除数据。不保证网站登录始终有效。 |
| 多沙箱 | 使用独立容器和工作目录，不是经过强化隔离的非互信多租户服务 |
| GUI 截图 | 支持浏览器窗口截图，也支持通过 CDP 截取页面 |

本地页面自动化不需要远程桌面时，可以直接使用 Playwright。
自动化与人工操作必须共用远程浏览器时，使用 Verge Browser。

## 集成指南

DSH 插件提供[中文安装说明](../../packages/dsh-plugin/README.zh.md)。
预览版适配 DSH `0.2.1-rc.2`。
插件提供 Chromium/Camoufox 的会话工具和人工接管。

以下指南目前以英文维护：

- [Codex 连接自托管浏览器](../../docs/integrations/codex.md)：配置 Playwright MCP、使用限定沙箱的 CDP 票据，并交给人接管。
- [Playwright 和 Playwright MCP 连接 CDP](../../docs/integrations/playwright-mcp.md)：连接现有浏览器，而不是另起一个浏览器。
- [无桌面的 Linux 服务器部署](../../docs/guides/headless-linux.md)：通过 SSH 隧道访问，不直接暴露 API。
- [人工接管](../../docs/guides/human-handoff.md)：停止自动化、完成手动步骤、重新读取页面后继续。
- [浏览器 Profile 持久化](../../docs/guides/persistent-profiles.md)：说明暂停、恢复、重启和删除分别保留什么。
- [CloakBrowser 内核](../../docs/guides/cloak.md)：配置许可证密钥并私有安装。未验证：真实授权内核的运行。
- [Camoufox 内核](../../docs/guides/camoufox.md)：使用命令 API，不使用 CDP。浏览器必须单独安装。

## Agent Skills

仓库提供面向 AI Agent 的 Skills，位于 [`skills/`](../../skills)：

- [`skills/verge-browser-deploy`](../../skills/verge-browser-deploy)：用于部署 Verge Browser、配置环境变量、验证服务健康状态以及排查启动问题
- [`skills/verge-browser-usage`](../../skills/verge-browser-usage)：管理已有服务中的沙箱，并结合 `agent-browser` 执行自动化

## 桌面方案对比

| 特性 | `xvfb_vnc` | `xpra` |
| --- | --- | --- |
| 桌面组件 | Xvfb + Openbox + x11vnc + noVNC | Xpra Server + HTML5 客户端 |
| 剪贴板 | 显式文本传输按钮。见[剪贴板用法](../../docs/vnc_clipboard.md)。 | Xpra 客户端剪贴板功能。必须在目标浏览器验证。 |
| 创建字段 | `kind: "xvfb_vnc"` | `kind: "xpra"` |

本文不提供延迟或网络性能基准测试。

如何选择：

- 以自动化为主，只偶尔人工查看：使用 `xvfb_vnc`
- 频繁人工接管或远程调试：使用 `xpra`

## API 接口说明

当前 API 采用 `/sandbox/{sandbox_id}/...` 路由模型。

详细端点文档位于 [`docs/api.md`](../../docs/api.md)。

SDK 与 CLI 使用示例位于 [`docs/cli-sdk.md`](../../docs/cli-sdk.md)。

### 接口范围

Verge Browser 聚焦于浏览器控制：

- 浏览器生命周期：create、pause、resume、delete
- 基于 CDP 的浏览器自动化
- GUI 截图与输入动作
- 基于 `xvfb_vnc` 或 `xpra` 的人工接管
- 通过沙箱工作目录交换文件

API 不提供任意 Shell 命令执行。
