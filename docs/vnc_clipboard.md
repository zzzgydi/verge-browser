# noVNC 文本剪贴板

使用会话工具栏，在本机与远端浏览器之间传送文本。
跨端传输只在点击按钮时发生，不是自动同步。
本文适用于 `xvfb_vnc`，不适用于 Xpra。

## 术语

| 术语 | 含义 |
| --- | --- |
| 本机 | 打开 noVNC 页面的用户设备。 |
| 远端 | Verge 沙箱中的浏览器和 X11 桌面。 |
| 远端剪贴板 | 沙箱 X11 的 `CLIPBOARD` 选择区。 |
| 会话 | 通过临时链接打开的 noVNC 连接。 |

## 使用条件

- 沙箱使用 `xvfb_vnc`。
- 远端 X11 桌面与 VNC 连接可用。
- 当前浏览器持有该沙箱的有效会话 Cookie。
- 文本非空，UTF-8 编码后不超过 64 KiB。

本机 Clipboard API 受浏览器权限和安全上下文限制。
接口不可用时，页面提供手动文本框。
图片、文件和富文本不属于此功能范围。

## 在远端内部复制粘贴

1. 点击远端浏览器内的目标区域。
2. 使用 `Ctrl+C`、`Ctrl+X` 或 `Ctrl+V`。

noVNC 把这些按键直接发送到远端。
页面不拦截这些按键，也不读取本机剪贴板。
此流程不调用剪贴板 HTTP API。
当前页面只承诺远端 Ctrl 快捷键，不承诺 Cmd 快捷键映射。

## 从本机粘贴到远端

1. 在本机复制文本。
2. 点击远端浏览器中的目标输入框。
3. 点击 `Paste to remote`。
4. 本机剪贴板权限受限时，在弹窗内手动粘贴文本。
5. 使用手动框时，点击其中的 `Paste to remote`。

页面先写入远端剪贴板，再发送远端粘贴按键。
远端写入失败时，页面保留输入并显示错误。
写入失败后，页面不发送粘贴按键。

## 从远端复制到本机

1. 在远端浏览器中选中文本。
2. 按 `Ctrl+C`。
3. 点击 `Copy to local`。
4. 本机写入权限受限时，从弹窗中手动复制文本。

`Copy to local` 读取远端剪贴板，不替你执行远端复制。
本机写入失败时，弹窗显示本次读取的文本。
页面不为该弹窗再次读取远端剪贴板。

## 发送期间的限制

同一页面一次只执行一项跨端传输。
弹窗打开时，其他传输按钮禁用。
提交前可以取消。

不得把关闭窗口当作撤销远端写入。
请求发送后，关闭窗口不能保证撤销操作。

提交后，按钮显示 `Sending...` 或 `Copying...`。
发送期间，页面禁用编辑、重复提交和关闭弹窗。
Escape 也不能关闭正在发送的弹窗。
失败后，页面恢复操作并保留文本。
成功后，页面关闭弹窗。

多个会话共享同一远端剪贴板。
必须协调其他客户端的复制粘贴操作。
本功能不提供跨会话锁。

## 故障处理

| 现象 | 操作 |
| --- | --- |
| 显示手动框 | 在框内粘贴或复制文本。 |
| 远端剪贴板为空 | 在远端重新选中文本并按 `Ctrl+C`。 |
| 会话过期 | 重新申请会话链接并打开。 |
| VNC 断线 | 恢复连接后再传输文本。 |
| 写入失败 | 保留输入，检查错误后决定是否重试。 |
| 仍显示旧工具栏 | 核对 API 部署版本并重新打开会话。只重建运行时镜像不能更新此页面。 |

会话 HTTP 鉴权与已有 VNC 连接不是同一检查。
剪贴板 HTTP 请求过期，不代表已有连接的远端按键同步失效。
本功能不延长任何鉴权有效期。

## HTTP 接口

两个接口使用该沙箱的 `sandbox_session` Cookie。
它们不是管理令牌接口。

| 接口 | 请求 | 成功响应 |
| --- | --- | --- |
| `GET /sandbox/{sandbox_id}/clipboard` | 无请求体 | `{"status":"ok","text":"hello"}` |
| `POST /sandbox/{sandbox_id}/clipboard` | `Content-Type: application/json`，正文 `{"text":"hello"}` | `{"status":"ok"}` |

剪贴板响应不使用管理 API 的 `{code,message,data}` 格式。
剪贴板服务错误返回 `status`、`code` 和 `message`。
鉴权错误由会话验证逻辑返回。

| 错误码 | 含义 |
| --- | --- |
| `clipboard_empty` | 没有可读取的远端文本。服务层也用此码拒绝空文本。 |
| `display_unavailable` | 沙箱状态或 X11 桌面不可用。 |
| `clipboard_unavailable` | 沙箱不是 `xvfb_vnc`。 |
| `clipboard_unsupported` | 文本内容或剪贴板类型不支持。 |
| `payload_too_large` | 文本超过 64 KiB。 |
| `rate_limited` | 同一沙箱的同类请求间隔不足 0.1 秒。 |
| `clipboard_timeout` | 剪贴板命令超时。 |
| `clipboard_exec_failed` | 命令失败或返回无效数据。 |
| `unsupported_media_type` | 写入请求不是 JSON。 |
| `invalid_request` / `invalid_json` | 请求字段或 JSON 无效。 |

HTTP 写入空文本时，请求校验返回 `invalid_request`。
字符数超限也在请求校验阶段返回 `invalid_request`。
通过校验后，UTF-8 字节数超限返回 `payload_too_large`。

`xclip` 的执行上限为 5 秒。
外层 Docker 命令的执行上限为 10 秒。
具体 HTTP 状态与校验见 [接口源码](../apps/api-server/app/routes/clipboard.py)。
服务限制见 [服务源码](../apps/api-server/app/services/clipboard.py)。

## 验证

在 Python 开发环境中，从仓库根目录执行：

```bash
node --test tests/unit/vnc_session.test.cjs
PYTHONPATH=apps/api-server pytest tests/unit/test_clipboard.py tests/unit/test_vnc_session.py
```

单元测试不读取用户真实剪贴板。
集成测试检查 X11 文本通过 `Ctrl+V` 进入 Chromium 输入框。
集成测试依赖 Docker 和构建后的运行时镜像。

单元测试不能证明所有本机浏览器的权限行为。
对外使用前，必须在目标浏览器中验证两个传输方向。
