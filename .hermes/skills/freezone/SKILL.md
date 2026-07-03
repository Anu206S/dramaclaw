---
name: freezone
description: "Use when the active chat surface is 虾画/Freezone/canvas, or when the user asks about canvas nodes, visual boards, selections, graph edits, canvas actions, layout, or Freezone short-video workflow work."
compatibility: Requires Freezone/虾画 chat surface with frontend-injected current project, canvas, resource, and node context for canvas-scoped operations.
---

# Freezone 虾画 Skill

## 定位

- 这个 skill 是虾画/Freezone 的总入口，负责判断当前是不是画布场景、用户意图属于咨询还是画布操作，以及用户可见回复应该怎么说。
- 具体节点职责、连线语义、视频节点和合成节点的产品建模，读取 `references/canvas-modeling-guide.md`。
- 具体前端命令格式、注入块读取、批量/单步工具、校验、`client_id` 和 JSON 示例，读取 `references/canvas-command-guide.md`。

## 意图判断

- 解释/咨询类请求：用户问“怎么 / 如何 / 什么是 / 介绍 / 说明 / 教我 / how to / what is / explain / show me how”时，只用自然语言回答步骤、概念或可选项；不要创建、修改、连接、布局、运行节点。
- 画布操作类请求：用户明确要求在画布上创建、生成、搭建、添加、连接、修改、删除、布局、选择、打开工具、运行、应用或执行时，进入画布命令模式。
- 创意咨询、找思路、风格建议：可以自然语言回答；如果用户希望“搭一个框架 / 落到画布 / 在画布里做”，可以使用画布工具创建可继续工作的画布材料。
- 全局画布请求：用户说“看看画布”“整理当前画布”“基于现有节点继续做”时，优先使用当前注入的画布上下文；上下文不足时再读取画布。
- 运行/生成已有工作流、选中工作流、工作流组或一组已连接节点时，复用已有节点、内容和连线，优先运行已有工作流；不要重新规划一套重复节点，除非用户明确要求新增、重写或替换。

## 注入上下文

- `[SUPERTALE_CANVAS_ONTOLOGY_CONTEXT]` 是当前画布的只读 overview，用来理解已有 nodes、links、slots、actions 和 current selection；不要把它当执行结果。
- `[SUPERTALE_CANVAS_NODE_REFERENCES]` 是本轮明确目标节点。若 overview 和 node references 同时存在，优先以 node references 作为操作目标。
- `[SUPERTALE_CANVAS_CHAT_COMMANDS]` 表示前端已经注入画布命令规则。需要真实修改画布时，不要在聊天里写协议 JSON，按 `references/canvas-command-guide.md` 使用 Freezone 工具。

## 建模原则

- 画布连线表示输入、参考、上下文或合成素材关系，不表示“下一步顺序”，也不是视觉关联线。
- 两个节点只是相关、属于同一组内容、需要放在一起展示时，用分组或布局，不要强行连线。
- 画布只能使用前端真实支持的节点类型；不要发明抽象节点类型。
- 普通文本、人物设定、广告创意、镜头描述、配音稿、短片方案段落，默认用 `textAnnotationNode`。
- `scriptNode` 只在用户明确要结构化脚本、镜头表、分镜表，或明确要求脚本生成器产物时使用。
- 用户说“做成视频 / 生成视频 / 做广告短片 / 生成短片 / 素材都有了怎么做”时，默认先考虑 `videoNode`。
- `videoComposeNode` 是最终时间线/合成节点，用于把多个视频片段和音频轨合成最终视频；只把视频/音频产物作为合成输入连进去，不要把创意简报、分镜文字或 prompt 直接连到它。

更多节点和连线判断读取 `references/canvas-modeling-guide.md`。

## 画布写入原则

- 画布写入必须有依据。创建节点或编辑图结构前，先基于当前画布 summary/ontology。
- 涉及命令结构、节点 data 或连线时，按需查询 command catalog、node create schema 和 link type catalog。
- 搭框架、工作流、分镜结构、短片方案落画布，或任何会创建多个节点/连线/分组/布局的请求，先收集必要 catalog/schema 并校验，然后用一次批量命令提交；不要边想边连续写多个单步操作。
- 多步骤、批量修改或包含连线的命令，写入前必须先 validate。
- 不要把多节点、多连线、故事板、原型搭建、批量整理、create+layout/link/group/action 组合拆成连续单步工具；应使用一次批量命令。
- 如果校验返回某个 source/target 的 `Allowed link_type values: none`，不要枚举重试其它 `link_type`；改用分组或保留未连接。
- 具体命令格式和工具调用顺序读取 `references/canvas-command-guide.md`。

## 用户可见回复

- 面向用户时称为“虾画”。
- 用户可见回复只说业务动作、业务对象、等待状态和业务结果。
- 不要解释底层 agent、plugin、toolset、注入块、协议名、schema 名、工具名、字段名、内部 id、JSON、桥接状态或前后端传输细节，除非用户明确要求调试接口契约。
- 需要向用户确认“添加哪类节点/内容”时，用口语化产品名称，不要列内部 node_type。
- 不要声称已经移动、创建、删除、连接、修改、运行或生成，除非前端写入/执行结果已经确认成功。
- 当前会话若未绑定具体画布，只能做项目级解释，或要求用户先打开一个画布。
- `canvasId` 表示画布 ID，不是节点 ID。

## 工具不可用时

- 如果虾画工具返回 `not_configured`、`not_implemented` 或 `canvas_id is required`，简短说明当前虾画工具尚未完成注入或未绑定画布。
- 不要改用 shell、curl、文件读写或猜测本地状态来绕过前端画布工具。
