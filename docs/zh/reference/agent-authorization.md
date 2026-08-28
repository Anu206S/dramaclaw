# Agent 授权边界

浏览器会话保留现有成员与项目角色校验。Agent 会话还受服务端维护的
`current_scope_kind`、`current_project_id` 和操作 scopes 约束；母账号能访问某个
项目，不代表委托给当前项目的 Token 也能访问它。

项目校验覆盖 path、query、body 以及通过项目名称解析的调用。项目范围的 Agent
列举项目时只返回当前项目；home 范围保留首页导航能力。切换 Agent 当前项目由
已认证的编排器完成，不能通过请求正文自行改写。

| 操作 | Agent 所需 scope |
|---|---|
| 项目配置、风格、通用上传、画布与素材修改 | `projects:write` |
| 明确的任务提交、生成、校验、任务预检与取消 | `tasks:submit` |
| 聊天通知与持久化 UI 事件 | `projects:write`，且聊天 scope 匹配 |
| CE 网关配置修改 | `projects:write`，并保留现有 CE 专用守卫 |

原本已有更具体权限要求的接口保持原约定，例如同步剧集改写仍属于项目内容写入。
每个 HTTP 修改接口都声明精确依赖；通用的不安全方法校验仅作兜底，不表示
`projects:write` 与 `tasks:submit` 等价。浏览器登出仍是恢复操作，即使会话过期也
允许清理调用方自己的 Cookie。

仅持有 `tasks:submit` 的客户端不能再直接调用配置或通用上传接口。应由有权限的
调用方准备输入，或通过既有凭据发放流程取得需要的 scope；不要自动扩展存量 Token
权限。项目不匹配或缺失操作权限返回 HTTP 403，接口路径与 payload 不变。

CE 仍然是可信的免登录单用户服务，这些 Token 校验不能把它变成多人鉴权服务。
请继续遵守[自托管手册](../guides/self-hosting.md)中的网络边界要求。
