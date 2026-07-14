# 本机 Codex / Claude 使用 DramaClaw MCP

本文档说明如何让用户本机安装的 Codex、Claude、OpenClaw 等外部 Agent 操作本机运行的 `dramaclaw-ce`。

## 设计目标

本机模式不需要复杂的外部网关。推荐链路是：

```text
Codex / Claude / OpenClaw
  -> 本机 MCP server
  -> http://127.0.0.1:8780
  -> dramaclaw-ce API
  -> 现有任务系统 / Freezone 画布 bridge
```

MCP 只作为本机工具适配层；真正的项目、任务、画布操作仍由 `dramaclaw-ce` API 和前端画布执行。

## 启动 dramaclaw-ce

先启动本机 API：

```bash
cd /path/to/dramaclaw-ce
DRAMACLAW_LOCAL_AGENT_TRUST=1 novelvideo api --host 127.0.0.1 --port 8780
```

`DRAMACLAW_LOCAL_AGENT_TRUST=1` 表示允许本机 `127.0.0.1` / `::1` / `localhost` 来源的本地 Agent 请求跳过 token。

注意：

- 只建议绑定 `127.0.0.1`。
- 不建议在监听 `0.0.0.0` 或局域网可访问时开启。
- 画布写操作仍走前端审批。
- 覆盖、删除、重摄入等高风险业务操作仍应保留业务确认。

## MCP Server

合并版 MCP 入口：

```bash
python -m novelvideo.chat.agent_mcp
```

它会同时暴露两类工具：

- `dramaclaw_*`：虾导项目、任务、剧集、媒体、生成流程。
- `freezone_*`：虾画画布、节点、连线、工作流、节点动作。

底层复用 `.hermes/plugins/dramaclaw` 和 `.hermes/plugins/freezone` 的现有工具实现。

默认环境会自动补齐：

- `DRAMACLAW_API_URL=http://127.0.0.1:8780`
- `DRAMACLAW_LOCAL_AGENT_TRUST=1`
- `DRAMACLAW_USER=local`
- `DRAMACLAW_CANVAS_COMMAND_BRIDGE_DIR=state/<user>/.hermes-freezone/tmp/supertale_canvas_command_bridge`

其中 bridge 目录使用共享根目录，方便当前浏览器中的 Freezone 会话监听并弹出审批。只有在调试特定 Agent profile 时，才需要手动覆盖 `DRAMACLAW_CANVAS_COMMAND_BRIDGE_DIR`。

## Codex 配置示例

推荐使用仓库虚拟环境里的 Python：

```json
{
  "mcpServers": {
    "dramaclaw": {
      "command": "/path/to/dramaclaw-ce/.venv/bin/python",
      "args": ["-m", "novelvideo.chat.agent_mcp"],
      "cwd": "/path/to/dramaclaw-ce",
      "env": {
        "DRAMACLAW_API_URL": "http://127.0.0.1:8780",
        "DRAMACLAW_LOCAL_AGENT_TRUST": "1",
        "DRAMACLAW_USER": "local"
      }
    }
  }
}
```

如果要操作虾画画布，建议补充当前画布上下文：

```json
{
  "DRAMACLAW_CHAT_SURFACE": "freezone",
  "DRAMACLAW_CANVAS_ID": "当前画布 ID"
}
```

没有 `DRAMACLAW_CANVAS_ID` 时，部分 Freezone 工具会要求调用时显式传 `canvas_id`。

## Token 模式

如果不想开启本机 trust，可以使用 token：

```json
{
  "env": {
    "DRAMACLAW_API_URL": "http://127.0.0.1:8780",
    "DRAMACLAW_AGENT_TOKEN": "xxx"
  }
}
```

有 token 时，插件会发送：

```http
Authorization: Bearer xxx
```

没有 token 且未开启 `DRAMACLAW_LOCAL_AGENT_TRUST=1` 时，工具会拒绝调用。

## 画布操作说明

外部 Agent 不能直接修改浏览器里的画布状态。Freezone 写操作仍使用现有 bridge：

```text
MCP freezone 工具
  -> 写 pending canvas command
  -> 浏览器前端显示审批
  -> 用户确认
  -> 前端执行节点/连线/工作流操作
  -> 回写 result
  -> MCP 工具返回结果
```

因此，使用 Codex/Claude 操作虾画时，需要浏览器中打开对应 Freezone 页面。
