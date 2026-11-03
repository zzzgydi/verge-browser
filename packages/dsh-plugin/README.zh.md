# Verge Browser 的 DeepSeek Harness 插件

[English](README.md) | 中文

本插件让 DSH 操作已有的 Verge 浏览器。
插件不在 DSH 主机安装或启动浏览器。

当前是预览包。尚未发布到 npm。

## 功能

| 功能 | 范围 |
| --- | --- |
| 网页操作 | 打开网页、读取页面、点击、输入和选择标签页。工具由浏览器内核决定。 |
| 截图 | 返回网页或完整浏览器窗口的 PNG。 |
| 人工接管 | 阻止本连接的自动化，返回临时操作链接。 |
| 远程文件 | 列出文件，读取或写入 `/workspace` 内的 UTF-8 文本。 |
| DSH 集成 | 使用 Agent 专属工具、工具策略、图片附件和程序化工具调用。 |

## 术语

| 术语 | 含义 |
| --- | --- |
| 沙箱 | 已有的 Verge 环境，包含浏览器和远程文件。 |
| Agent | 使用本插件浏览器工具的当前 DSH 智能体。 |
| Profile | 选择插件和工具策略的 DSH 配置。 |
| Provider | 占用 DSH `browserUse` 槽位的插件实例。 |
| 桥接进程 | 通过 MCP 协议提供浏览器工具的插件进程。 |
| CDP | 连接 Chromium 和 Cloak 的 Chrome DevTools Protocol。 |
| 快照 | 页面文本和元素引用，不是截图。 |
| PTC | 通过 DSH `run_code` 工具执行的程序化工具调用。 |

## 使用条件

| 项目 | 要求 |
| --- | --- |
| DSH | `^0.2.0`。`0.3.x` 需要显式版本豁免。依赖宿主的 Agent、MCP、工具、作用域、系统提示词和工作目录服务。 |
| Node | `>=22.12.0`。本地测试使用 `22.21.1`。 |
| Playwright MCP | 固定为 `0.0.80`。 |
| Verge | 可访问的 API、管理令牌，以及状态为 `RUNNING` 的已有沙箱。 |
| 图片 | 支持图像输入的模型，以及 DSH 附件存储。 |

`engines.dsh: "^0.2.0"` 接受 `0.2.0` 及之后所有 `0.2.x` 版本，包括预发布版。
它拒绝 `0.3.0` 及其预发布版。宿主 DSH 共享依赖使用同一范围。
未测试的 DSH 版本需要显式豁免：
`dsh plugin --profile YOUR_PROFILE allow-version dsh-plugin-verge-browser@0.1.1 --dsh-version <精确版本> --accept-risk`。
浏览器辅助模块按测试版本打入插件包。宿主服务继续共享，不打入插件包。
开发依赖继续固定版本，保证构建可重复。不得用 `latest` 替换开发依赖版本。

## 构建和安装

1. 打开完整的 Verge 仓库。
2. 在仓库根目录安装开发依赖。

   ```bash
   pnpm --dir packages/dsh-plugin install --ignore-scripts --registry=https://registry.npmjs.org
   ```

3. 构建插件。

   ```bash
   pnpm --dir packages/dsh-plugin build
   ```

4. 检查插件。

   ```bash
   pnpm --dir packages/dsh-plugin check
   pnpm --dir packages/dsh-plugin test
   ```

5. 生成安装包。

   ```bash
   cd packages/dsh-plugin
   npm pack
   ```

6. 将安装包加入目标 Profile。

   把 `YOUR_PROFILE` 替换为 Profile 名称。
   在 `packages/dsh-plugin` 目录执行：

   ```bash
   dsh plugin --profile YOUR_PROFILE add ./dsh-plugin-verge-browser-0.1.1.tgz --registry=https://registry.npmjs.org
   ```

安装包包含对应的 Verge SDK。运行时不依赖相邻 SDK 目录。
安装预构建包不编译插件，也不下载浏览器。
当前不支持从 Git 子目录安装源码。
开发工具缺少平台二进制时，必须完成该工具的批准安装流程。

### 从 0.1.0 升级

将新安装包加入同一个 Profile，然后重启 DSH。
无需授予版本豁免。npm 的旧版 `0.1.0` 仍要求 DSH `0.2.1-rc.2`。
已有配置项 ID 和连接配置保持不变。
如果 Profile 覆盖了 `verge-browser-registry` 的 `name`，将它改为
`dsh-plugin-verge-browser/registry`。作用域已有 `browserUse` 时，继续禁用该配置项。

### 从插件索引安装

版本发布到 npm 后，DSH 可以从本仓库的插件索引里找到它：

```text
https://raw.githubusercontent.com/zzzgydi/verge-browser/main/packages/dsh-plugin/market/index.json
```

1. 打开 **插件** 页，在 **实验插件** 里打开 **Custom plugin indexes**。
2. 打开 **Discover**，选择 **Add index source**，粘贴上面的地址。
3. 选择当前 DSH 接受的版本，确认安装来源。

索引只列出已发布到 npm 的版本。版本升级的维护步骤见
[market/README.md](https://github.com/zzzgydi/verge-browser/blob/main/packages/dsh-plugin/market/README.md)。

## 配置

安装后，两个插件配置项默认禁用。安装本身不访问 Verge。

1. 在启动 DSH 的环境中设置下列变量。

   | 变量 | 内容 |
   | --- | --- |
   | `VERGE_BROWSER_URL` | Verge API 地址。不得使用 CDP 或接管地址。 |
   | `VERGE_BROWSER_TOKEN` | Verge 管理令牌。不得使用 CDP 票据。 |
   | `VERGE_BROWSER_SANDBOX` | 已有沙箱的 ID 或别名。 |

2. 禁用目标作用域内其他浏览器 Provider。
3. 将下列配置加入目标 Profile 的 `cordis.patch.yml`。

   作用域内已有 `browserUse` 服务时，保持 `verge-browser-registry` 禁用。

   ```yaml
   - id: verge-browser-registry
     disabled: false
   - id: verge-browser
     disabled: false
     config:
       baseUrl: !!js process.env.VERGE_BROWSER_URL
       token: !!js process.env.VERGE_BROWSER_TOKEN
       sandbox: !!js process.env.VERGE_BROWSER_SANDBOX
   ```

4. 使用这些环境变量启动目标 DSH Profile。
5. 在插件启用后新建或恢复 Agent。

插件不向启用前已运行的 Agent 添加工具。
同一作用域只接受一个浏览器 Provider。

必须保持 API 私有，或通过隧道访问。
不得把凭证放入工具参数或报告。
API 地址与 CDP 端点必须使用相同主机和端口。
API 使用 HTTPS 时，CDP 端点必须使用 `wss:`。

### 超时与票据有效期

| 配置字段 | 默认值 | 允许范围 |
| --- | --- | --- |
| `requestTimeoutMs` | `30000` 毫秒 | 1 至 300000 的整数 |
| `toolCallTimeoutMs` | `60000` 毫秒 | 1 至 300000 的整数 |
| `cdpTicketTtlSec` | `300` 秒 | 1 至 3600 的整数 |
| `handoffTtlSec` | `300` 秒 | 1 至 3600 的整数 |

修改超时时，必须保留全部连接字段。
DSH 覆盖配置时会替换整个 `config` 对象。

## 使用工具

让 Agent 在操作前读取页面状态。
工具名称使用 `mcp__verge-browser__` 前缀。
服务端的 `browser_engine` 决定浏览器工具目录。

| 共用工具 | 功能 |
| --- | --- |
| `verge_status` | 读取所选沙箱的 ID、内核、状态、视口和自动化状态。 |
| `verge_screenshot` | 返回网页或完整窗口的 PNG。 |
| `verge_handoff` | 阻止本桥接进程的自动化，返回一次性接管链接。 |
| `verge_resume` | 在接管或操作中断后允许自动化。 |
| `verge_files_list` | 列出远程 `/workspace` 内的文件。 |
| `verge_file_read` | 读取最多 64 KiB 的 UTF-8 文本。 |
| `verge_file_write` | 写入最多 64 KiB 的 UTF-8 文本。覆盖已有文件必须指定 `overwrite: true`。 |

远程 `/workspace` 路径不是 DSH 主机路径。
网页截图和窗口截图使用不同坐标系。
缺少图片支持时，DSH 返回诊断信息，不宣称模型完成看图。

### 浏览器工具

Chromium 和 Cloak 使用 CDP 与部分 Playwright MCP 工具。
Camoufox 使用 Verge 命令 API，不使用 CDP。

| 用途 | Chromium / Cloak | Camoufox |
| --- | --- | --- |
| 导航 | `browser_navigate`、`browser_navigate_back` | `verge_open` |
| 读取页面 | `browser_snapshot` | `verge_snapshot`、`verge_text`、`verge_url`、`verge_title` |
| 输入 | `browser_click`、`browser_type`、`browser_press_key` | `verge_click`、`verge_fill`、`verge_press` |
| 表单 | `browser_hover`、`browser_select_option`、`browser_fill_form` | 使用点击和填写工具。 |
| 对话框与等待 | `browser_handle_dialog`、`browser_wait_for` | 不提供独立工具。 |
| 标签页 | `browser_tabs`：列出、新建、选择 | `verge_tabs`、`verge_switch` |
| 向网页上传 | 不开放 | `verge_upload`：选择远程 `/workspace` 内已有文件。 |

插件不开放下列操作：

- 安装或关闭浏览器。
- 关闭标签页。
- 执行任意 JavaScript。
- 上传 DSH 主机文件。
- 使用 Playwright 文件输出参数。

## 在右侧栏查看浏览器

Web profile 下，插件还会在右侧栏增加一个 **Verge 浏览器** 页签。
打开右侧栏，在向导里选择 **Verge 浏览器**。
该页签显示的浏览器画面与人从 Xpra 或 noVNC 看到的画面一致，并接受鼠标和键盘输入。

页签不需要二次登录。
DSH 主机用 `handoffTtlSec` 作为有效期申请可复用会话票据，再把会话页面、静态资源和 WebSocket 通过 DSH 自己的源转发。
浏览器拿不到管理端 token，也拿不到 Verge 会话 Cookie，同时不涉及第三方 Cookie。
点 **重新连接** 会丢弃当前画面并申请新的票据。

| 限制 | 行为 |
| --- | --- |
| 仅 Web | Headless 和桌面组合没有 HTTP 服务，只提供工具，不提供页签。 |
| 一个 sandbox | 本插件实例下的所有 Agent 显示同一个已配置 sandbox。 |
| 只转发配置目标 | 代理只访问已配置 sandbox 的会话地址，不转发到其他主机或路径。 |
| 仅限本机可信 | 页签由该 profile 的 HTTP 服务提供 `GET /verge-browser/session/`，不要把该服务绑定到不可信网络。 |

## 人工接管

不得把接管链接复制到报告。
链接授予临时访问权限，并会进入会话记录。

1. 让 Agent 调用 `verge_handoff`。
2. 打开返回的链接。
3. 完成人工操作。
4. 向 Agent 确认操作结束。
5. 让 Agent 调用 `verge_resume`。
6. 让 Agent 在操作前重新读取快照。

接管期间，本桥接进程只允许状态、接管和恢复工具。
其他客户端和人工仍能操作浏览器。
不得复用接管前的元素引用。

## 失败后恢复

不得在未检查浏览器时重复超时动作。
客户端停止等待后，服务端仍能完成动作。

1. 通过 Verge CLI 或管理端检查浏览器。
2. 确认远程动作结束。
3. 自动化中断时，调用 `verge_resume`。
4. 在下一次操作前重新读取快照。

插件不自动重放失败动作。
HTTP 取消不撤销远程命令，也不保证命令停止。
错误后申请人工接管前，必须确认远程动作结束。

取消 CDP 建连时，插件等待 Playwright 返回或超时。
随后插件断开客户端。
建连等待受 `requestTimeoutMs` 限制，默认 30 秒。
清理失败时，插件报告错误。
接管失败时，自动化继续受阻，直到显式恢复。

## 连接归属与限制

一个运行中的 Agent 占用当前 Provider 的沙箱连接。
其他 Agent 继续运行，但没有此 Provider 的浏览器工具。
连接释放后，新建或重新激活 Agent 才能获取连接。

卸载 Provider 只断开客户端。
插件不暂停、重启、删除或关闭远程浏览器。
连接占用不是跨进程锁。

首版不提供：

- 为每个 Agent 自动创建沙箱。
- 在 DSH 主机与沙箱之间传输二进制文件。
- 专用 DSH 接管卡片。
- 与其他浏览器客户端协调操作。

使用 Verge CLI 或管理端管理沙箱和传输二进制文件。
Cloak 仍依赖单独配置的内核与授权。

## DSH 行为

工具使用 DSH 标准的会话级 MCP 调用链。
PTC 可以读取结构化结果。
截图使用 DSH 图片附件链路。

必须用目标 Profile 的工具策略约束网站操作。
安装插件不代表批准全部操作。
必须把网页和文件视为不可信数据，而不是指令。

工具结构与使用指引在各轮调用间保持稳定。
浏览器内核决定可用工具目录。
插件不新建模型循环，也不单独调用模型。

## 验证

已验证：2026-11-01 的本地检查通过。
检查使用 DSH `0.2.1-rc.2`。

| 检查 | 通过范围 |
| --- | --- |
| 构建、类型与 14 项插件测试 | 构建产物、Agent 隔离、策略拒绝、参数限制和失败恢复。 |
| DSH 附件 | 缺少存储时的诊断，以及测试模型路由下的图片存储和读取。 |
| 安装包与 PTC | 独立 Profile、真实 DSH Loader、真实 Agent 和 `run_code`。不调用模型。 |
| Chromium 与 Camoufox | 两个真实 Docker 场景，并对独立安装包重复执行。 |

Docker 测试覆盖原生点击、PNG、文件和一次性会话入口。
测试也覆盖接管限制、GUI 输入、恢复和断连后保留。

未验证：Cloak、Xpra、Desktop 渲染和模型实际看图。
真实登录和 MFA 流程未验证。
测试未覆盖全部网络故障及全部 Agent fork/resume 路径。
不得把 Chromium 测试结果当作 Cloak 验证。

### 重复本地检查

在仓库根目录执行：

```bash
pnpm --dir packages/dsh-plugin check
pnpm --dir packages/dsh-plugin build
pnpm --dir packages/dsh-plugin test
```

### 重复 Docker 检查

执行前构建插件和运行时镜像。
把二进制路径替换为本机 Camoufox 目录。
在 Python 开发环境中，从仓库根目录执行：

```bash
VERGE_DSH_RUNTIME_TEST=1 \
VERGE_CAMOUFOX_BINARY_DIR=/absolute/path/to/camoufox \
PYTHONPATH=apps/api-server pytest tests/integration/test_dsh_plugin.py
```

### 重复 DSH Profile 检查

必须使用临时 `DSH_HOME`。
此检查创建真实 Agent，并保存测试会话数据。

1. 将安装包加入该目录下的 `verify` Profile。
2. 在仓库根目录执行下列命令。

   ```bash
   DSH_HOME=/absolute/path/to/disposable-home pnpm --dir packages/dsh-plugin test:profile
   ```

此检查使用模拟 Verge API 和真实 DSH PTC。
它不调用模型，也不修改保存的 Profile 配置。

## 许可

插件原始代码使用 MIT 许可。
依赖保持各自许可。
安装包不包含浏览器二进制或字体。
其他浏览器内核的分发限制保持不变。
