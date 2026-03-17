# VNC Clipboard

## 需求

本方案仅针对 `xvfb_vnc` 沙盒类型，为 noVNC 会话增加文本剪切板能力。

目标行为：

- 用户在 noVNC 中操作远端 Chromium 时，执行 `Ctrl+C` 后，可以将沙盒浏览器中的文本同步到用户本地浏览器剪切板。
- 用户在本地执行 `Ctrl+V` 时，可以将本地浏览器剪切板中的文本写入沙盒，并在远端 Chromium 中完成粘贴。
- 只要求“文本剪切板可用”，不要求图片、文件、富文本或完全无感的系统级同步。

非目标：

- 不修改 `xpra` 会话链路。
- 不保证所有浏览器和所有部署场景下都无权限提示。
- 不保证与原生桌面远程软件一致的剪切板体验。

## 现状

当前 `xvfb_vnc` 会话链路如下：

- 运行时通过 `x11vnc` 暴露 VNC。
- 通过 `websockify` 将 VNC 转为 WebSocket。
- API 服务将用户重定向到 noVNC 的 `vnc.html` 页面。

相关位置：

- `apps/runtime-xvfb/scripts/start_x11vnc.sh`
- `apps/runtime-xvfb/scripts/start_websockify.sh`
- `apps/api-server/app/services/session.py`

这些文件在方案中的角色分别是：

- `start_x11vnc.sh`：启动 VNC 服务端
- `start_websockify.sh`：将 VNC 服务暴露为浏览器可连接的 WebSocket
- `session.py`：生成并代理用户进入 noVNC 会话的入口

当前实现没有项目自定义的 noVNC 会话页，因此无法在前端挂接本地浏览器剪切板读写逻辑。

虽然 noVNC 和 x11vnc 本身支持 RFB clipboard 消息，但当前项目直接重定向到发行版自带的 `vnc.html`，页面行为不受项目代码控制。仅依赖默认页面存在几个问题：

- 无法稳定插入本地浏览器 `navigator.clipboard` 读写逻辑
- 无法针对权限失败、时序问题和降级交互做项目级处理
- 无法增加项目需要的日志、重试和多标签页协调逻辑

因此本方案不是否定 noVNC 的 clipboard 能力，而是不直接依赖发行版默认页面来完成最后一跳的浏览器剪切板同步。

## 约束

本需求的主要约束不在 VNC 协议本身，而在浏览器安全模型：

- 浏览器本地系统剪切板读写通常依赖 `navigator.clipboard`。
- `navigator.clipboard.readText()` 和 `navigator.clipboard.writeText()` 通常要求安全上下文，并可能要求用户手势触发。
- 单纯转发 `Ctrl+C` 和 `Ctrl+V` 按键，不足以保证本地和远端剪切板同步，因为网页不能仅凭键盘事件直接读写用户系统剪切板，仍需通过 Clipboard API 并满足浏览器安全约束。

此外，远端 Chromium 复制后的内容需要先进入 X11 的 `CLIPBOARD` 选择区，后端才能稳定读取。

运行时还依赖 `DISPLAY` 对应的 X11 会话可用。这里真正依赖的是容器内 X server，而不是 `x11vnc` 进程本身：

- 如果 X server 尚未就绪，`xclip` 会失败
- 如果 `DISPLAY` 配置错误，`xclip` 会失败
- 如果 VNC 代理异常但 X server 仍在运行，理论上 `xclip` 仍可能可用

因此 clipboard API 需要对“X11 不可用”和“剪切板为空”做区分，而不是统一视为无内容。

## 解法

采用“前端桥接 + API 桥接 + X11 剪切板工具”的最小可行方案。

### 1. 在 `runtime-xvfb` 镜像中增加 X11 剪切板工具

在 `docker/runtime-xvfb.Dockerfile` 中通过系统包安装 `xclip`。

当前镜像基于 Debian slim，因此建议直接使用：

- `apt-get install -y --no-install-recommends xclip`

建议锁定 Debian 仓库中的稳定包，不额外引入源码安装或手工下载。若后续需要版本说明，应以镜像实际解析出的发行包版本为准，而不是在文档中先行写死最小版本号。

不建议使用 `pip install`，因为 `xclip` 是系统级 X11 命令行工具，不是 Python 库。

本方案不考虑 Alpine 变体，因为当前项目的 `runtime-xvfb` 基础镜像不是 Alpine。

用途：

- 读取远端剪切板：`xclip -selection clipboard -o`
- 写入远端剪切板：`xclip -selection clipboard`

这样可以直接与 X11 `CLIPBOARD` 交互，不依赖 Chromium 私有机制。

可选地可以保留 `xsel` 作为后备方案，但最小实现先以 `xclip` 为准，避免同时维护两套命令行为。

### 2. 在 API 服务增加远端剪切板读写接口

新增仅面向 `xvfb_vnc` 的文本剪切板接口，例如：

- `GET /sandbox/{sandbox_id}/clipboard`
- `POST /sandbox/{sandbox_id}/clipboard`

行为建议：

- `GET`：
  - 在容器内执行 `DISPLAY=:99 xclip -selection clipboard -o`
  - 返回 `application/json`
- `POST`：
  - 接收 `application/json`
  - 将请求中的文本写入容器内 X11 `CLIPBOARD`

安全约束建议：

- 只支持纯文本，不支持 HTML、图片、文件或任意二进制负载
- 对请求体增加大小限制，最小方案建议上限 `64 KiB`
- 对响应内容增加大小限制，最小方案建议上限 `64 KiB`
- 对空文本和超长文本返回显式错误
- 接口复用现有 sandbox 会话鉴权，避免未授权读取远端剪切板
- 为接口增加基础 rate limit，避免高频轮询或恶意刷写；若项目当前没有通用限流设施，至少在服务层增加简单节流

错误分类建议：

- `clipboard_empty`：X11 可访问，但当前 `CLIPBOARD` 没有可读文本
- `display_unavailable`：`DISPLAY` 不可访问或 X server 未就绪
- `clipboard_unsupported`：读到的内容不属于本方案支持的纯文本范围
- `payload_too_large`：请求或响应超过限制
- `clipboard_exec_failed`：命令执行失败，但不属于上面可识别类别

接口返回建议保留结构化状态，避免前端只能从 HTTP 状态码猜原因。

API 契约建议：

- `GET /sandbox/{sandbox_id}/clipboard`
  - 成功时返回 `200 OK`
  - `Content-Type: application/json`
  - 响应示例：`{"status":"ok","text":"hello"}`
- `POST /sandbox/{sandbox_id}/clipboard`
  - 请求头要求 `Content-Type: application/json`
  - 请求示例：`{"text":"hello"}`
  - 成功时返回 `200 OK`
  - 响应示例：`{"status":"ok"}`

HTTP 状态码建议：

- `400 Bad Request`
  - 请求体缺失、JSON 非法、文本为空、文本包含本方案明确拒绝的内容
- `401 Unauthorized` / `403 Forbidden`
  - 会话无效或未授权
- `409 Conflict`
  - sandbox 状态不允许访问，或远端 display 尚未就绪
- `413 Payload Too Large`
  - 请求或响应超过大小限制
- `415 Unsupported Media Type`
  - 非 `application/json`
- `429 Too Many Requests`
  - 触发节流或限流
- `500 Internal Server Error`
  - 未归类的服务端异常
- `502 Bad Gateway`
  - 容器执行路径失败，或远端 runtime 异常

对于可恢复错误，建议返回机器可读错误码，例如：

- `{"status":"error","code":"clipboard_empty"}`
- `{"status":"error","code":"display_unavailable"}`
- `{"status":"error","code":"payload_too_large"}`

可观测性建议：

- 记录 clipboard 读写成功、失败、权限错误和超限错误
- 日志中不要打印完整剪切板内容，最多记录长度、sandbox id、会话 id 和错误类型
- 对连续失败场景保留足够上下文，便于排查浏览器权限、X11 剪切板和容器执行问题
- 如需辅助排查重复同步问题，可记录文本摘要或哈希，而不是原文
- 默认按敏感数据处理，不做正文落盘，也不尝试依赖高误报的“密码识别”策略

实现建议：

- 新增 `apps/api-server/app/services/clipboard.py`
- 新增 `apps/api-server/app/routes/clipboard.py`
- 复用现有容器执行模式和会话鉴权方式

### 3. 用项目自定义页面承载 noVNC 会话

不要继续直接使用发行版自带的 `vnc.html` 作为最终入口，而是新增一个项目自定义会话页。

该页面负责：

- 初始化 noVNC `RFB` 连接
- 优先监听 `keydown`
- 使用 `copy`、`paste` 作为补充事件
- 调用浏览器 Clipboard API
- 调用服务端 clipboard 接口完成双向同步

这样可以将剪切板逻辑控制在项目代码中，而不是依赖 noVNC 发行版页面行为。

实现建议：

- 新增一个简单静态页或模板页，例如 `apps/api-server/app/static/vnc_session.html`
- `session.py` 中将 `xvfb_vnc` 的重定向地址从 `vnc.html` 改为项目自定义页面
- 自定义页面再连接 `/sandbox/{sandbox_id}/session/websockify`

说明：

- 页面内部仍然使用 noVNC `RFB`，不是重写 VNC 客户端
- 变化点只在“承载页”和“项目自定义交互逻辑”，不是替换 noVNC 协议实现
- noVNC 已具备 clipboard 相关能力；实现阶段应确认当前接入版本的 `RFB` 可复用事件或方法，再决定是否在项目承载页中接入这些 hook，但这不是本方案成立的前提

前端事件策略建议：

- 优先监听 `keydown` 中的 `Ctrl+C`、`Ctrl+V`、`Ctrl+X` 以及 macOS 上的 `Meta+C`、`Meta+V`、`Meta+X`
- `copy`、`paste` 事件仅作为补充，不应作为唯一入口
- 对 noVNC 焦点区域和页面级快捷键进行约束，避免事件被外层 DOM 吃掉
- 若 noVNC `RFB` 已提供 clipboard 相关 hook，可在该层补充同步逻辑，但不直接依赖发行版 `vnc.html`

## 交互流程

### 本地粘贴到远端

当用户在 noVNC 页面中执行 `Ctrl+V` 或触发 `paste` 时：

1. 前端读取本地浏览器剪切板文本。
2. 前端调用 `POST /sandbox/{sandbox_id}/clipboard`，将文本写入远端 X11 `CLIPBOARD`。
3. 前端将粘贴热键继续发送给 noVNC。
4. 远端 Chromium 从 X11 剪切板完成粘贴。

该流程优先保证“可用”，而不是完全透明。

### 远端复制到本地

当用户在 noVNC 页面中执行 `Ctrl+C` 或触发 `copy` 时：

1. 先让复制热键正常发送给远端 Chromium。
2. 前端等待一个很短的初始延迟，然后调用 `GET /sandbox/{sandbox_id}/clipboard`。
3. 如果读取失败、内容为空或疑似尚未刷新，则在有限时间窗口内重试。
4. 读取到文本后，前端调用 `navigator.clipboard.writeText()` 写入本地浏览器剪切板。

时序策略建议：

- 不将 `100-300ms` 写死为唯一方案，这个数值只作为初始退避参考
- 推荐使用“短延迟 + 有上限的重试”而不是单次等待
- 可选地在前端做轮询，直到读取到非空文本、内容变化，或达到超时上限
- 为了避免把旧剪切板内容误认为新内容，前端可以缓存上一次成功同步的文本摘要并参与判定
- 需要考虑 Chromium 内部从复制动作到 X11 `CLIPBOARD` 更新存在异步延迟，尤其是较大文本时，因此不应把第一次读取失败直接视为最终失败

可以将这一机制理解为“先触发远端复制，再轮询等待远端剪切板就绪”。

最小实现可以采用：

- 初始延迟 `150ms`
- 重试间隔 `150ms`
- 最多重试 `3-5` 次

这里的核心目标是提高可靠性，而不是追求实时性。

## 浏览器兼容性

本方案的最佳支持目标应明确为 Chromium 系浏览器。

兼容性说明：

- Chromium 系浏览器通常对 `navigator.clipboard` 支持最好
- Firefox 可能出现更严格的权限提示或交互限制
- Safari 对 Clipboard API 的限制通常更严格，可靠性不应作为首要承诺
- 在非 HTTPS 或非安全上下文中，Clipboard API 可能不可用或行为受限

因此产品层面应明确：

- 推荐使用 Chromium 系浏览器访问 noVNC 会话
- 对 Firefox 和 Safari 仅提供尽力支持
- 在 HTTP 环境下必须预期降级交互更常出现

## 并发与多标签页

同一个 sandbox 被多个标签页同时打开时，剪切板天然存在冲突风险，因为远端 X11 `CLIPBOARD` 本身就是共享状态。

最小方案建议不解决跨标签页强一致性，只明确约束行为：

- 同一时刻以“最后一次写入”为准
- 多标签页同时监听 `Ctrl+C` / `Ctrl+V` 时，可能出现覆盖
- 文档和实现中应明确该能力面向单活跃会话场景优化
- API 层不引入乐观锁或事务语义；并发写入按最后成功写入生效

可选增强：

- 在前端基于 `BroadcastChannel` 或 `localStorage` 实现同 sandbox 标签页间协调
- 约定只有当前活跃标签页负责执行本地剪切板同步
- 在服务端记录最近一次 clipboard 写入来源，帮助排查覆盖问题

## 降级策略

由于浏览器可能拒绝本地剪切板权限，方案必须包含降级路径。

建议行为：

- 本地读取剪切板失败时：
  - 弹出文本框，允许用户手动粘贴后再提交到远端
- 本地写入剪切板失败时：
  - 展示远端读取到的文本，允许用户手动复制

降级方案存在时，即使 Clipboard API 权限不足，功能仍可用。

降级交互建议：

- 优先使用轻量模态框或侧边浮层，而不是新窗口
- 手动粘贴场景中保留本次输入，避免权限失败后用户再次输入
- 手动复制场景中展示只读文本框，并提供明确的“复制失败，请手动复制”提示
- 当焦点落在降级文本框内时，应暂停全局 `Ctrl/Cmd + C/V/X` 拦截，避免与页面级 clipboard 逻辑冲突

## 风险

- 远端 Chromium 复制后，内容进入 X11 `CLIPBOARD` 可能存在时序延迟。
- X11 中 `PRIMARY` 与 `CLIPBOARD` 可能不一致；最小方案先只处理 `CLIPBOARD`。
- 浏览器 Clipboard API 在非安全上下文或权限不足时会失败。
- 直接复用 noVNC 自带页面较难插入项目自定义逻辑，因此建议改为自定义承载页。
- 多标签页同时连接同一 sandbox 时，剪切板内容可能被相互覆盖。
- 高频 clipboard 读取重试如果没有节流，会给 API 和容器执行带来额外压力。

## 协议与传输选择

本方案优先使用独立 HTTP clipboard API，而不是复用现有 `websockify` 通道。

原因：

- `websockify` 当前只承载 VNC WebSocket 转发，服务端不解析或增强 clipboard 语义
- 虽然 VNC 协议本身支持 `ClientCutText` / `ServerCutText`，但当前项目没有位于 `websockify` 和 noVNC 之间的协议增强层
- 单独 HTTP 接口更容易增加鉴权、大小限制、日志和错误处理
- 实现复杂度更低，便于先落地最小能力

权衡上可以理解为：

- HTTP API：多一条网络路径，但实现成本更低，调试手段更直接
- 复用 WebSocket / VNC 原生 clipboard：协议路径更短，但需要更深地介入 noVNC 和 VNC 消息处理

基于当前目标“先可用”，优先选择 HTTP API 是工程折中，而不是否定 VNC 原生能力。

后续如果需要减少请求数或做更实时的状态同步，再考虑基于项目自定义 WebSocket 通道承载 clipboard 事件。更明确地说，只有当单会话 clipboard 操作频率已经高到 HTTP 轮询和重试成为明显负担时，才值得推进基于 WebSocket 的迁移。

## 文本与编码

本方案只处理文本内容，并假定主路径使用 UTF-8。

编码约束建议：

- API 输入输出统一使用 UTF-8 JSON
- 对包含 `NUL` 等明显不适合文本剪切板桥接的控制字符内容直接拒绝
- 对无法按 UTF-8 处理的内容按 `clipboard_unsupported` 处理
- 不尝试桥接图片、富文本或任意二进制内容

## 验收标准

最小验收标准如下：

1. 启动一个 `xvfb_vnc` sandbox。
2. 在远端 Chromium 输入框中输入文本并执行 `Ctrl+C`。
3. 回到本地浏览器，能够粘贴出相同文本。
4. 在本地复制一段文本。
5. 在 noVNC 中聚焦远端 Chromium 输入框并执行 `Ctrl+V`。
6. 文本能够成功粘贴到远端。
7. 当浏览器拒绝剪切板权限时，仍可通过降级交互完成复制或粘贴。
8. 在重复 `Ctrl+C` 的情况下，系统不会因单次时序抖动而频繁读取失败。

## 实施顺序

建议按以下顺序落地：

1. 在 `runtime-xvfb` 镜像中安装 `xclip`
   优先级最高，工作量低
2. 为 API 服务增加远端剪切板读写接口
   优先级最高，工作量中等
3. 增加项目自定义 noVNC 会话页
   优先级最高，工作量中等
4. 将 `xvfb_vnc` 会话入口改为该自定义页面
   工作量低
5. 补充单元测试和集成验证
   工作量中等，必须覆盖成功、权限失败、display 不可用和超限场景

## 结论

只改 `xvfb_vnc` 的前提下，为 noVNC 增加“文本剪切板可用”能力是可行的。

该能力不应设计为纯按键转发，而应实现为：

- 浏览器本地剪切板
- API 中转
- 容器内 X11 剪切板

三者之间的桥接方案。

这个方案的目标不是达到原生远程桌面级别体验，而是在当前项目结构内，以较小改动获得稳定、可验证的文本剪切板能力。
