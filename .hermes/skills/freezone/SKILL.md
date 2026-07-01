---
name: freezone
description: "Use when the active chat surface is 虾画/Freezone/canvas, or when the user asks about canvas nodes, graph edits, canvas actions, selections, layout, visual boards, or node-based workflows. This skill is a placeholder contract for injected Freezone tools."
compatibility: Requires Freezone/虾画 chat surface with frontend-injected current project, canvas, resource, and node context for canvas-scoped operations.
---

# Freezone 虾画 Skill

## 一句话定位

- 这个 skill 用来识别“当前是在虾画/Freezone 画布里工作”。
- 虾画当前主链路是：前端注入只读画布上下文，Agent 输出命令，前端执行并保留历史、选中态、确认流程和工具面板。
- 遇到“节点该怎么理解、什么时候该连线、什么时候不该连、视频节点和合成节点怎么分工”这类判断时，先参考 `references/canvas-operation-manual.md`。

## 先判断在做什么

- 用户在问“有哪些 workflow / 工作流 / 工作流技能 / 类型 / 模板 / 方案”，或要分析、预览短剧、广告视频、产品视频、MV 等整体流程时：交给 `workflows` skill，并优先使用工作流计划工具生成计划；规划阶段不直接改画布。
- 用户明确要求“创建/添加/生成/再创建/再来一个/再添加一个/重新建一个/复制一个同类型”已注册工作流时：直接调用 `freezone_create_workflow_graph`，传 `workflow_type` 或 `workflow_types`，不要把工作流拆成多次 `create_node`。
- 当前画布已经存在同类型工作流时，仍然允许再次创建一个新的工作流实例。不要因为已有文生图、图生视频等工作流就改成查询列表、解释已有内容或复用旧节点。
- 用户已经在具体操作节点，例如创建、修改、移动、连接、布局、删除、打开工具、运行节点动作：进入画布命令模式。
- 只有用户确认工作流计划后，才把计划交给工作流落图工具创建具体画布节点和连线。

## 画布命令模式

- 只要本轮消息包含 `[SUPERTALE_CANVAS_ONTOLOGY_CONTEXT]`、`[SUPERTALE_CANVAS_NODE_REFERENCES]` 或 `[SUPERTALE_CANVAS_CHAT_COMMANDS]`，普通画布编辑就按前端命令模式处理。
- `[SUPERTALE_CANVAS_ONTOLOGY_CONTEXT]` 是当前画布的只读 overview，用来理解已有 nodes、links、slots、actions 和 current selection；不要把它当执行结果。
- `[SUPERTALE_CANVAS_NODE_REFERENCES]` 是本轮明确目标节点。若 overview 和 node references 同时存在，优先以 node references 作为操作目标。
- 节点内的 `action_catalog_json` 是前端操作目录：
  `execution="chat_command"` 用对应 `command_type`；
  `execution="manual_ui"`、`execution="frontend_node"`、`requires_confirmation` 用 `run_node_action`，并使用动作里的 `action` 字段。

## 画布建模原则

- 画布连线表示数据输入、参考或上下文关系，不表示“下一步顺序”。
- 画布只能使用前端真实支持的节点类型；不要发明抽象节点类型。
- `add_next_node` 只在当前节点会作为新节点输入时使用。若只是创建一个相关节点但当前节点不是输入，应使用 `create_node`，必要时再补 `create_edge`。
- 多输入任务应把多个输入节点分别连接到目标节点，而不是串成 `A -> B -> C`。例如“图片 + 文本生成视频”应让图片节点和文本节点分别连接到 `videoNode`。
- 文本作为图片生成输入时，可以使用 `textAnnotationNode -> imageGenNode`；图片节点自身 prompt 会和上游文本共同构成生成上下文。
- `textAnnotationNode` 是默认的普通文本语义节点。人物设定、广告创意、分镜描述、配音稿、普通脚本内容，优先用它。
- `scriptNode` 不是默认文本节点，也不是默认工作流中间节点。只有用户明确要结构化脚本、镜头表、分镜表，或明确要求脚本生成器产物时，再考虑使用它。
- 不要复用历史轮次里的画布节点 ID。只有当前用户文本、当前 node references、或本轮刚创建的 `client_id` 可作为操作目标。

## 视频节点原则

- 用户说“做成视频 / 生成视频 / 做广告短片 / 生成短片 / 素材都有了怎么做”时，默认应创建 `videoNode`，用于根据上游图片、文本、脚本、音频参考生成一个视频片段。
- `videoNode` 是视频生成节点，不是最终时间线节点。它负责生成单个镜头或单段视频素材。
- `videoNode` 常见模式包括：文生视频、图生视频、首尾帧视频、全能参考、图片参考。是否可切换、真实字段名和枚举值是什么，以当前节点的 `action_catalog_json.editable_schema` 为准；不要猜字段或自造值。
- 当用户要求“改成图生视频 / 改成首尾帧 / 改成全能参考 / 改成图片参考 / 改视频模式”时，优先理解为修改 `videoNode` 的生成模式，而不是修改视频模型、视频比例或把节点换成 `videoComposeNode`。
- 不要默认创建 `videoComposeNode`。`videoComposeNode` 只用于已有一个或多个真实视频片段后做时间线合成/最终成片导出。
- 只有当上游已经有带 `videoUrl` / `video_url` 的 `videoNode`，或用户明确说“时间线合成 / 合成多个视频片段 / 剪成最终成片 / video compose”时，才考虑 `videoComposeNode`。

## 常用命令约定

- 节点 CRUD、布局、打开工具和节点自身动作都走 `canvas_chat_commands.v1`。
- `move_nodes` 用于移动节点。相对移动用 `dx/dy`；移动到指定坐标再用 `positions`。如果本轮引用了多个节点且用户表达的是整体移动，必须把所有目标节点都放进同一个 `node_ids`。
- 删除节点时用 `delete_nodes`，把所有目标节点 ID 放进 `node_ids`。不要因为引用里有边就改成 `delete_edges`。
- 只有用户明确要求“断开连接 / 移除连线 / 解绑连接”时，才使用 `delete_edges`。
- 如果用户要求“执行生成/运行/生成”当前引用的 `imageGenNode`，且 `action_catalog_json.actions` 中存在 `generate_image`，则使用 `run_node_action` 调用该动作。

## 用户可见回复

- 面向用户时称为“虾画”；不要主动解释底层 agent、plugin、toolset、注入块、协议名、schema 名、工具名、字段名或桥接细节。
- 内部实现信息只用于推理或调用工具，不要写进自然语言回复。
- 用户可见回复只说业务动作、业务对象、等待状态和业务结果。

- 不要声称已移动、创建、删除、连接或修改节点。任意 Freezone 画布写入工具成功只表示命令已提交给前端执行器；最终是否应用成功取决于前端执行结果。
- 当前会话若未注入 `DRAMACLAW_CANVAS_ID`，说明没有绑定具体画布，只能做项目级解释或要求用户先打开一个画布。
- `canvasId` 表示画布 ID，不是节点 ID。

## 工作流列表查询

当用户问“有哪些 workflow / 有哪些工作流 / 支持哪些工作流 / 有哪些工作流技能 / 我的工作流技能有哪些 / 有哪些 workflow skill / 有哪些流程 / 有哪些类型 / 有哪些模板 / 有哪些方案 / 可以创建哪些类型 / 可以做哪些流程”时，这是纯查询请求，优先调用 `freezone_list_workflows` 获取当前注册列表，再按工具结果回复。工具不可用时再使用下面的静态列表兜底：

注意：“再创建一个文生图工作流 / 再来一个图生视频 / 新增一个同样的工作流”不是列表查询请求，必须调用 `freezone_create_workflow_graph`。

```text
当前已注册的工作流有 9 个：

1. 短剧 / 小说转视频
2. 广告视频
3. 产品视频 / 商品演示
4. MV / 音乐视频
5. 文生图
6. 图生视频
7. 文生视频
8. 图生文
9. 文生音频

你可以选择其中一个，我再根据对应类型提示你需要提供哪些材料。
```

不要输出 `freezone_workflow_plan.v1`，不要要求用户提供材料，不要等待确认，不要调用或等待画布命令，不要列未注册的示例类型。

“工作流技能 / workflow skill”默认指 `workflows` skill 中注册的工作流规划能力，不是 `freezone.sketch_from_context`、`freezone.frame_from_context`、`freezone.scene_360` 这类画布节点可执行原子技能。只有用户明确说“画布 skill / 节点技能 / 可执行技能 / action / action_catalog / 生成草图技能 / 分镜技能”时，才列画布 action catalog。

## 工作流规划

当用户选择或要求创建某类工作流时，交给 `workflows` skill，由它按意图读取对应 reference：

- 短剧、小说转视频、故事转视频：`workflows/references/short-drama.md`
- 广告视频、投放素材、Hook、A/B 版本：`workflows/references/ad-video.md`
- 产品视频、商品演示、功能讲解：`workflows/references/product-video.md`
- MV、音乐视频、歌词视觉化：`workflows/references/mv.md`
- 文生图：`workflow_type="text_to_image"`
- 图生视频：`workflow_type="image_to_video"`
- 文生视频：`workflow_type="text_to_video"`
- 图生文：`workflow_type="image_to_text"`
- 文生音频：`workflow_type="text_to_audio"`

所有工作流计划都必须通过 `workflows` skill 生成 `freezone_workflow_plan.v1`，且只规划，不直接改画布。

## 工具契约


虾画 Agent 的主链路工具按优先顺序分层：

读全局：

- `freezone_get_canvas_ontology`：只读查询前端当前画布的详细 ontology context；不修改画布，也不需要用户确认。
- `freezone_summarize_canvas`：只读查询前端当前画布的简单 ontology summary；不修改画布，也不需要用户确认。
- `freezone_get_canvas_action_catalog`：只读查询前端当前画布的 action catalog；不修改画布，也不需要用户确认。
- `freezone_get_canvas_command_catalog`：只读查询前端当前 `canvas_chat_commands.v1` 批量命令 catalog；使用 `freezone_emit_canvas_command` 前如果不确定 `commands[]` 字段，先调用它。
- `freezone_get_link_type_catalog`：只读查询普通节点连线的 `link_type` catalog；创建 `create_edge` 前如果不确定类型，优先用它查询，再选择 `link_type`。
- `freezone_get_selection`：只读查询前端当前选择；不修改画布，也不需要用户确认。

读节点：

- `freezone_get_node_detail(node_id)`：读取单个节点详情。
- `freezone_get_neighbor_graph(node_id, depth)`：读取单个节点上下游邻居。
- `freezone_get_node_action_catalog(node_id)`：读取单个节点的 action catalog。
- `freezone_get_node_create_schema(node_type)`：读取创建某类节点允许填写的 data schema。
- `freezone_get_audio_voice_options(node_id)`：读取音频节点可用音色选项。
- `freezone_get_slot_candidates(slot_kind)`：读取当前可提交到槽位的候选节点；`slot_kind` 可选。

校验：

- `freezone_validate_canvas_commands`：前端预校验 `canvas_chat_commands.v1`，使用当前前端画布、节点类型、连线规则和 action catalog 检查命令是否会失败；不修改画布，也不需要用户确认。对多节点创建、连线、删除、批量修改等非平凡操作，先校验，通过后再调用对应写入工具。

写入：

- `freezone_emit_canvas_command`：默认写入入口。只要用户没有明确要求“只创建/修改/连接/移动/布局/分组/选择/执行一个对象或一个操作”，就把本次画布修改整理成一次 `commands[]` 批量提交；若不确定 `commands[]` 的字段，先调用 `freezone_get_canvas_command_catalog`。
- 单步写入工具：`freezone_create_node`、`freezone_add_next_node`、`freezone_update_node_data`、`freezone_create_edge`、`freezone_delete_nodes`、`freezone_delete_edges`、`freezone_move_nodes`、`freezone_layout_nodes`、`freezone_group_nodes`、`freezone_select_nodes`、`freezone_run_node_action`。这些工具只用于用户明确要求 exactly one 的单个操作；不要把“创建这些节点/搭一个框架/做一个流程/整理一批内容”拆成连续单步工具。
- 多节点、多连线、工作流、故事板、原型搭建、批量整理、create+layout/link/group/action 组合这类请求，必须先查 `freezone_get_canvas_command_catalog`（如字段不确定），然后用一次 `freezone_emit_canvas_command` 批量提交。
- 如果 `freezone_validate_canvas_commands` 返回某个 source/target 的 `Allowed link_type values: none`，不要枚举重试其它 `link_type`；改用 `group_nodes` 或保留为未连接节点。

如果主链路工具返回 `not_configured`、`not_implemented` 或 `canvas_id is required`，直接简短说明当前虾画工具尚未完成注入或未绑定画布，不要改用 shell、curl、文件读写或猜测本地状态。

## 回复规则

- 解释/咨询类请求：如果用户问“怎么 / 如何 / 什么是 / 介绍 / 说明 / 教我 / 怎么生成工作流 / 如何生成 workflow / how to / what is / explain / show me how”，只用自然语言回答步骤、概念或可选项；不要创建、修改、连接、布局、运行节点，不要调用或等待 `freezone_emit_canvas_command`。只有用户明确要求“在画布上创建/生成/搭建/添加/连接/运行/应用/执行”或在解释后确认要落地到画布，才进入画布命令模式。
- 画布读取类请求：如果没有前端注入的节点引用，才读取当前画布快照再回答；如果已有 `[SUPERTALE_CANVAS_NODE_REFERENCES]`，优先使用注入内容。
- 上下文补充/预校验类请求：如果当前注入内容不足以判断合法节点、上下游关系、普通连线的 `link_type`、创建参数、模型/音色/模板选项，优先调用具体只读查询工具或 `freezone_request_canvas_context`。非平凡画布修改在最终发命令前优先调用 `freezone_validate_canvas_commands` 校验，若返回问题，修正命令后再次校验；不要用任何写入工具包装这些读取、选项查询或校验请求。
- 工作流类请求：如果用户询问有哪些 workflow / 工作流 / 工作流技能 / workflow skill / 流程 / 类型 / 模板 / 方案，使用 `workflows` 回复已注册列表；如果用户意图是规划或预览一条由多个节点、连线和执行阶段组成的生成工作流，使用 `workflows` 分析并优先调用 `freezone_build_workflow_plan` 生成计划，不能直接创建节点。用户明确要求创建已注册工作流，或确认把已注册工作流落到画布后，必须调用 `freezone_create_workflow_graph`，直接传 `workflow_type` 或 `workflow_types`，让工具一次性生成节点、连线、布局和分组。“再创建一个 / 再来一个 / 新增一个同类型”也属于创建请求，不属于查询或复用请求。
- 一次创建多个已注册工作流时，不要逐个展开节点清单或手写多份计划；必须只调用一次 `freezone_create_workflow_graph`，传 `workflow_types` 数组。
- 画布节点创建、移动、修改、连线、布局、删除、打开工具类请求：如果是已注册工作流，必须调用 `freezone_create_workflow_graph`；如果是普通多节点批量创建/连线/布局，使用一次 `freezone_emit_canvas_command` 批量提交，由前端执行器应用。只有用户明确要求 exactly one 的单个操作时，才调用对应结构化单步工具。
- 运行/生成已有工作流、选中工作流、工作流组或一组已连接节点时，必须使用一个 `run_workflow` 画布命令；不要手写多个 `run_node_action`，也不要只挑图片/视频/音频中的一部分节点。前端会按连线依赖执行：一个节点完成后，所有依赖已满足的下游生成节点会同批启动。
- 当用户选中已有工作流组并说“继续完成视频 / 继续生成 / 完成视频创建 / 基于已有工作流继续”时，必须把选中组和组内已有节点内容视为事实来源：优先读取/复用已有文本、prompt、媒体和连线，然后运行已有工作流。不要重新规划工作流、不要新建重复节点、不要新写一套文本内容，除非用户明确要求“新增节点 / 补一个节点 / 重写内容 / 替换内容”。
- 全局画布请求：如果用户说“看看画布”“整理当前画布”“基于现有节点继续做”，且不是主线工作流规划意图，优先读取 `[SUPERTALE_CANVAS_ONTOLOGY_CONTEXT]` 中的 objects/links/current_selection，选择已有节点或用 `create_node`/`create_edge`/`layout_nodes` 等前端命令落地。
- 不展示原始 API URL、认证头、文件系统路径、内部字段名、工具名或内部 JSON，除非用户明确要求调试接口契约。
