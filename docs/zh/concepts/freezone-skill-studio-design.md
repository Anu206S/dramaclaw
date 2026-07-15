# 虾画 Skill Studio 设计与落地说明

## 范围

本文档只描述 A 部分：用户通过对话创建或编辑虾画 Skills / Recipes。

不包含 B 部分：普通虾画 Agent 如何消费 Skills / Recipes 生成工作流。A 部分只负责产出可保存、可预览、可被后续消费的配置草稿。

## 边界约束

虾画 Agent 和虾导 Agent 必须保持隔离。本文档讨论的 Skill Studio、虾画 Skills、虾画 Recipes、虾画对话卡片、虾画历史记录和虾画画布操作，只能改变 Freezone / 虾画相关链路。

实现时默认规则：

- 只改虾画需要的入口、状态、缓存、渲染、工具桥接和配置存储。
- 不修改虾导 Agent 的默认行为、消息解析、历史记录展示、工具执行逻辑和现有创作流程。
- 如果某个能力确实需要复用 SuperChat 通用层，必须保证默认行为不变，只在 Freezone scope 或明确的虾画 variant 下启用。
- 如果改动可能影响虾导，先停下来向用户确认；确认后应先更新本文档，再按更新后的边界实现。
- 后续所有虾画 Agent 相关需求都应遵循本文档。若需求与本文档冲突，应先讨论并修订本文档，而不是直接改代码。

## 目标

- 用户可以在对话里说“帮我创建一个电商详情页 Skill”。
- Agent 根据用户描述生成一个 Skill 草稿和若干 Recipe 草稿。
- 前端展示结构化预览，用户确认后才保存。
- 保存目标沿用现有账号级 catalog：

```text
output/<username>/_account/freezone/agent_config/skills/*.json
output/<username>/_account/freezone/agent_config/recipes/*.json
```

- 普通创作请求不能误触发 Skill 创建。
- Skill Studio 不修改底层画布协议，不影响虾导 Agent。

## 触发入口

### 对话入口

当用户明确表达以下意图时，进入 Skill Studio：

- “创建一个 Skill”
- “帮我做一个 Recipe”
- “把这个流程保存成 Skill”
- “以后这种工作流做成模板”
- “沉淀成可复用能力”
- “修改已有 Skill / Recipe”

反例：

- “做个电商海报”
- “帮我想一个公益短片”
- “加一个图片节点”

这些属于普通虾画创作，不应进入 Skill Studio。

### 设置页入口

后续可以在“虾画 Skills / 虾画 Recipes”页面增加“AI 创建”按钮。点击后打开虾画聊天或配置生成弹窗，默认带上“创建 Skill / Recipe”的上下文。

第一阶段可以先只做对话入口。

## 创建 Skill 的场景判断顺序

创建 Skill 之前，Agent 应先判断当前请求属于哪一种场景。不要把所有请求都当成“从零创建 Skill”，也不要在普通创作请求里过早进入配置流程。

### 总体判断顺序

```text
1. 用户是否明确表达“创建 / 保存 / 沉淀 / 修改 Skill 或 Recipe”？
   - 是：进入 Skill Studio 判断流程。
   - 否：按普通虾画创作处理；任务完成后可轻量提示“是否沉淀为 Skill”。

2. 用户是否指向已有 Skill 或 Recipe？
   - 是：进入“改造型”流程。
   - 否：继续判断画布状态。

3. 当前画布是否存在完整工作流？
   - 是：进入“总结型”流程，从工作流提炼 Skill / Recipes。
   - 否：继续判断是否有可参考素材。

4. 当前画布是否存在零散但有价值的素材、节点或提示词？
   - 是：进入“归纳型”流程，从素材归纳风格、规则和生成动作。
   - 否：进入“创作型”流程，从用户目标自动生成 Skill / Recipes 草稿。
```

### 1. 总结型：从完整工作流生成 Skill

适用场景：

- 用户说“把当前流程保存成 Skill”。
- 画布里已经有可复用的节点链路。
- 节点之间存在明确输入、处理、输出关系。

Agent 行为：

- 读取当前画布摘要、节点类型、连线关系和关键节点内容。
- 识别工作流解决的问题、输入要求、中间步骤和输出结果。
- 将领域规则提炼为 Skill。
- 将可复用的单步生成动作提炼为 Recipes。
- 尽量复用已有节点结构，不凭空扩展过多步骤。

对话文案倾向：

```text
我会把当前画布里的工作流整理成一个可复用 Skill，并尽量复用已有节点结构生成对应 Recipes。
```

### 2. 创作型：从自然语言目标创建 Skill

适用场景：

- 用户明确说要创建 Skill，但画布为空或没有可参考内容。
- 用户只给了一个目标，例如“做一个电商详情页 Skill”。

Agent 行为：

- 根据目标自动补全 Skill 草稿。
- 自动生成触发条件、规划器提示词、行为规则、评价规则。
- 自动建议必要 Recipes。
- 展示关键假设，而不是追问字段。

对话文案倾向：

```text
我会先按你的目标生成一个可保存的 Skill 草稿，并自动补齐触发条件、规划器提示词、行为规则、评价规则和建议 Recipes。
```

### 3. 归纳型：从零散画布素材创建 Skill

适用场景：

- 画布没有完整工作流。
- 画布里有图片、文本、Prompt、参考风格、角色设定、品牌素材等。
- 用户希望把这些素材沉淀成可复用能力。

Agent 行为：

- 不把零散素材误判为完整工作流。
- 从素材里归纳风格、领域、输入约束、输出偏好和评价标准。
- 生成 Skill 草稿。
- 必要时生成少量 Recipes，但不强行构造复杂工作流。

对话文案倾向：

```text
当前画布没有完整工作流，但有可参考素材。我会基于这些素材归纳风格、输入输出和生成规则，创建一个 Skill 草稿。
```

### 4. 改造型：编辑、扩展或派生已有 Skill / Recipe

适用场景：

- 用户提到已有 Skill 或 Recipe。
- 用户说“把这个 Skill 改成更适合小红书”“给这个 Skill 加一个 Recipe”“基于内置 Skill 改一下”。

Agent 行为：

- 不创建全新 Skill，除非用户明确要求“复制一个新的”。
- 如果是内置项，保存时写用户 overlay 或定制副本，不修改内置源文件。
- 如果是用户自建项，直接更新用户配置。
- 如果是扩展动作，优先新增或修改 Recipe，再更新 Skill 的关联说明。

对话文案倾向：

```text
我会基于现有配置做定制，不修改内置源文件。保存后它会作为你的用户定制版本生效。
```

### 5. Recipe 集合反推 Skill

适用场景：

- 用户已经导入或创建了一组 Recipes。
- 用户希望“把这些 Recipes 组织成一个 Skill”。
- 画布里没有完整工作流，但已有多个具体生成动作。

Agent 行为：

- 从 Recipes 的 `action_keys`、`output_kind`、`system_prompt` 和 `result_summary` 反推出领域能力。
- 生成 Skill 的触发条件、规划器提示词和评价规则。
- 将已有 Recipes 作为 Skill 可调度的动作集合。

对话文案倾向：

```text
这些 Recipes 已经描述了具体生成动作。我会把它们组织成一个 Skill，负责触发、规划和评价。
```

### 6. 临时执行，不沉淀 Skill

适用场景：

- 用户只是要求完成一次创作任务。
- 用户没有表达“创建 / 保存 / 沉淀 / 复用”的意图。

Agent 行为：

- 不进入 Skill Studio。
- 继续按普通虾画 Agent 执行画布任务。
- 任务结束后，如果流程明显可复用，可以给一个轻量建议，但不能打断创作。

对话文案倾向：

```text
这类任务以后可以沉淀成 Skill；如果你愿意，我可以把当前流程整理成可复用能力。
```

### 自动补全与用户纠偏

进入 Skill Studio 后，Agent 不应把第三层设计成连续追问字段。更好的方式是：

- Agent 先用少量高层选项问题确认方向。
- Agent 根据用户选择自动生成完整草稿。
- Agent 展示关键假设。
- 用户只做确认、保存或自然语言纠偏。

## 选项式澄清问题流

当用户从零创建 Skill，或当前画布信息不足以直接总结 Skill 时，Agent 可以先生成一组高层问题。每个问题提供几个选项，用户依次点击回复。选完后，Agent 再根据选择生成 Skill / Recipes 草稿。

这不是字段表单。问题只用于确定高层创作方向，不暴露底层 JSON 字段。

### 交互状态机

Skill Studio 前端和后端应围绕明确状态推进，避免普通聊天、问题流、草稿预览和保存动作互相混杂。

```text
idle
  普通聊天状态。

detecting
  后端识别本轮是否进入 Skill Studio。普通创作请求应回到 idle。

questioning
  展示选项式澄清问题。用户可逐题点击，也可使用推荐配置或跳过。

drafting
  Agent 根据用户目标、画布上下文、已有 catalog 和问题答案生成完整草稿。

previewing
  前端展示 Skill / Recipe 草稿卡。此时尚未保存。

editing
  用户用自然语言调整草稿；Agent 基于当前草稿生成修改后的完整草稿。

saving
  用户确认保存，前端调用 catalog 保存接口。

saved
  保存完成，提示用户可在设置页查看，也可在输入框用 `/` 指定 Skill。

cancelled
  用户取消创建或关闭草稿，不保存任何内容，回到普通聊天。
```

约束：

- `previewing` 之前不能保存。
- `cancelled` 不应留下半成品文件。
- `editing` 不是重新创建，必须基于当前草稿修改。
- `saved` 后不自动执行画布工作流。

### 基本流程

```text
1. 用户表达创建意图。
2. Agent 判断需要澄清方向。
3. Agent 展示 3-5 个高层问题，每题 3-4 个选项。
4. 用户依次点击选项，也可以选择“用推荐配置”或“跳过，直接生成草稿”。
5. Agent 汇总选择，说明将按什么方向生成。
6. Agent 生成 Skill 草稿卡和 Recipe 草稿卡。
7. 用户自然语言纠偏、查看 JSON 或保存。
```

### 示例：公益短片 Skill

Agent 开场：

```text
我先帮你确定这个 Skill 的方向。选完后，我会自动生成 Skill 和 Recipes 草稿；保存前你还可以继续修改。
```

问题 1：这个 Skill 主要解决什么阶段？

- 创意策划：主题、情绪、核心表达、传播主张。
- 分镜脚本：时间线、镜头、旁白、音乐节奏。
- 视觉生成：主视觉、关键帧、角色 / 场景图。
- 完整工作流：从主题到分镜、视觉、合成节点。

问题 2：输出更偏哪种形态？

- 文案 / 策划文档。
- 图片 / 关键帧。
- 视频工作流。
- 混合输出。

问题 3：用户输入通常是什么？

- 只有一句主题。
- 有详细 brief。
- 有参考图 / 素材。
- 有已有画布节点。

问题 4：希望工作流复杂度多高？

- 轻量：1 个 Skill + 1 个 Recipe。
- 标准：1 个 Skill + 3 个 Recipes。
- 完整：Skill + 多个 Recipes + workflow template。
- 先只建 Skill，不建 Recipes。

问题 5：风格更偏哪类？

- 纪实公益。
- 情绪叙事。
- 手绘动画。
- 社媒传播。

选择完成后，Agent 汇总：

```text
我会按以下方向生成草稿：

- 类型：完整工作流。
- 输出：混合输出。
- 输入：一句主题或 brief。
- 复杂度：标准配置。
- 风格：纪实公益。

接下来我会生成 1 个 Skill 和 3 个 Recipes 草稿，保存前你可以继续修改。
```

### 问题设计原则

- 问题数量控制在 3-5 个以内。
- 每个问题 3-4 个选项。
- 问题必须是用户能理解的创作意图，不问 `id`、`category`、`keywords`、`system_prompt` 等底层字段。
- 每个选项必须影响草稿生成策略，不能为了互动而互动。
- 用户可以点击选项，也可以直接用自然语言回答。
- 必须提供“用推荐配置”或“跳过，直接生成草稿”。

### 问题流数据结构

选项式问题不应只作为普通文本输出。当前 Freezone 实现复用通用澄清工具 `freezone_request_user_clarification` 展示问题卡片；它不写画布、不保存 catalog，只负责把用户选择结构化返回给 Agent。Skill Studio 问题流需要在 clarification 事件中保持稳定的会话标识，便于后续草稿和保存动作串联。

建议 payload：

```json
{
  "type": "assistant.clarification.request",
  "clarification_id": "skill_studio_01",
  "title": "我先帮你确定这个 Skill 的方向",
  "description": "选完后我会自动生成 Skill 和 Recipes 草稿；保存前还可以继续修改。",
  "questions": [
    {
      "id": "workflow_scope",
      "title": "这个 Skill 主要解决什么阶段？",
      "options": [
        {
          "id": "creative_planning",
          "label": "创意策划",
          "description": "主题、情绪、核心表达、传播主张"
        },
        {
          "id": "storyboard_execution",
          "label": "分镜脚本",
          "description": "时间线、镜头、旁白、音乐节奏"
        }
      ]
    }
  ],
  "allow_recommended": true,
  "allow_skip": true
}
```

用户回答建议 payload：

```json
{
  "type": "assistant.clarification.response",
  "clarification_id": "skill_studio_01",
  "answers": [
    {
      "question_id": "workflow_scope",
      "option_id": "creative_planning"
    }
  ],
  "used_recommended": false,
  "skipped": false
}
```

### 问题回答提交方式

第一阶段建议前端本地收集用户选择，全部问题完成后一次性提交给 Agent。

原因：

- 减少聊天轮次数，避免消息流里出现多条无意义点击回复。
- Agent 可以一次性看到完整方向，生成更稳定的草稿。
- 用户仍然可以中途用自然语言回答；前端将自然语言作为附加说明提交。

如果用户选择“用推荐配置”：

- 前端提交 `used_recommended: true`。
- Agent 使用默认选项生成草稿，并在摘要里说明默认假设。

如果用户选择“跳过，直接生成草稿”：

- 前端提交 `skipped: true`。
- Agent 直接基于用户原始目标和画布上下文生成草稿。

### 选项到草稿生成的映射

- 阶段选择：决定 Skill 的能力边界。
- 输出形态：决定 Recipes 的 `output_kind` 分布。
- 输入类型：决定是否需要素材输入、触发规则和上下文读取策略。
- 复杂度：决定 Recipes 数量、是否生成 workflow template。
- 风格方向：决定 `planning.prompt_guide`、`planning.conduct_rules` 和评价规则。

### 不同场景的问题数量

总结型：

- 问题应更少。画布已有完整工作流时，Agent 应优先总结现有结构，只问是否保留项目特征、是否拆分关键节点为 Recipes。

归纳型：

- 问题数量中等。Agent 已有素材线索，只需要确认风格、输出形态和复杂度。

创作型：

- 可以使用完整问题流。因为没有画布上下文，需要通过高层选项确定方向。

改造型：

- 不使用完整问题流。Agent 应围绕已有 Skill / Recipe 做定制、扩展或派生。

示例：

```text
我先按“电商详情页视觉与文案工作流”来组织：
- 面向淘宝 / 天猫 / 小红书商品详情页。
- 优先生成文案策划，再生成视觉图提示词。
- 评价重点放在卖点清晰度、视觉质感和转化导向。

如果方向不对，你可以直接说“更偏小红书种草”或“只做图片生成”。
```

原则：

- 不要求用户补齐底层字段。
- 不在用户确认前直接保存。
- 不把普通创作请求误判为创建 Skill。
- Skill 是领域能力包，Recipe 是 Skill 下可被调度的具体动作配方。

## 草稿预览与修改机制

Skill Studio 的核心产物是“当前草稿”。用户所有自然语言纠偏都应作用在当前草稿上，而不是每次重新从零生成。

草稿卡片是单一事实源。聊天只负责提出创建、解释或修改意图；真正会被保存的内容，只能来自当前草稿卡片里的结构化 draft。不能保存聊天里的自然语言描述，也不能让 Agent 口头声称“已修改”但没有返回新的草稿。

### 草稿生成

Agent 生成草稿时，最终应形成完整 Skill / Recipes 草稿，而不是只给用户展示局部字段或自然语言摘要。

草稿生成可能需要整理用户目标、画布上下文、已有 catalog 和多个 Recipe 节点。为了避免用户在等待完整草稿时感觉界面卡住，前端应展示轻量的 Skill Studio 状态流。状态流只表达当前生成阶段，不是草稿数据源，也不能被保存。

推荐状态阶段：

```text
进入 Skill Studio -> 正在整理 Skill 方向...
等待约 6 秒仍未出草稿 -> 正在生成 Skill 草稿...
总等待约 8 秒仍未出草稿 -> 草稿较完整，正在补齐 Recipes 和校验项...
收到问题卡或草稿卡 -> 隐藏状态卡，展示真实交互卡片
Hermes 超时 -> 保留已到达内容，并显示超时/重试状态
```

状态流规则：

- 状态事件使用同一个 assistant turn，不新开消息。
- 同一 turn 只展示最新状态，避免多条等待文案堆叠。
- 一旦出现 `skill_studio.questions`、`skill_studio.draft` 或可见澄清卡，状态卡应自动隐藏。
- 状态卡不能替代 `freezone_finish_agent_catalog_draft` 后产生的完整草稿事件；真正进入保存态必须等待完整草稿事件。
- 不把草稿拆成“Skill 先保存、Recipes 后补”的半成品流程，避免 currentDraft、校验和保存语义变复杂。

### 草稿传输优化：避免单次巨大 tool_call

当前实现里，草稿阶段使用 `freezone_present_agent_catalog_draft` 一次性传入完整 `skill + recipes`。这会带来两个问题：

1. **单次 tool_call 过大。** 当 Skill 包含多个 Recipes，且每个 Recipe 都有较长的 `system_prompt` 时，Agent 的 tool_call 参数会变成一条很大的 Hermes ACP JSON-RPC stdout 行。由于后端通过 `hermes_sdk.py` 使用 `stdout.readline()` 读取 Hermes 输出，默认单行限制较小，可能触发：

```text
Separator is found, but chunk is longer than limit
```

2. **用户等待时间过长。** 前端只有等完整 `skill + recipes` 一次性 tool_call 完成后，才能收到真正的草稿事件。在此之前，页面只能显示固定时间驱动的“正在整理 / 正在生成 / 正在补齐”状态，无法知道 Skill、Recipe 1、Recipe 2 等具体部分是否已经生成完成。Recipe 越多、提示词越长，用户看到真实草稿前的空等时间越明显。

这不是前端渲染问题，也不是保存接口问题，而是 Skill Studio 草稿数据在 Agent -> Hermes -> 后端的传输层被一次性塞进了单行 tool_call，同时把所有中间进度都隐藏到了最后一步。

优化目标：

- Agent 不再用一次 tool_call 传完整草稿。
- 前端最终仍然只看到一个完整、可保存的 `skill_studio.draft`。
- 保存接口和草稿卡片的结构化编辑语义保持不变。
- 草稿生成过程可以按真实完成进度向前端更新状态，例如 Skill 已完成、Recipe 1 / 6 已完成，而不是只靠固定时间文案猜测状态。

推荐改法是把草稿提交拆成 begin / put 或 patch / finish：

```text
freezone_begin_agent_catalog_draft
  开始一个 Skill Studio 草稿构建会话，只传 session_id、mode、summary、warnings 等轻量信息。

freezone_put_agent_catalog_skill
  提交 Skill 主体。

freezone_put_agent_catalog_recipe
  每次提交一个 Recipe。多个 Recipes 使用多次小 tool_call。

freezone_patch_agent_catalog_draft
  局部修改当前草稿中的 Skill 或某个 Recipe。适合用户让 AI 调整时只改少数字段。

freezone_finish_agent_catalog_draft
  结束草稿构建。插件或后端根据 session_id 组装完整 skill + recipes，并发出最终 skill_studio.draft 事件。
```

`finish` 工具不能再携带完整 `skill` 或 `recipes`，只能携带 `skill_studio_session_id`、预期数量、校验信息等轻量字段。完整草稿只能由前面已经提交的小块在后端/插件侧组装出来。

改造后的状态流可以从“按时间猜测”升级为“按真实进度更新”：

```text
begin draft  -> 正在创建草稿结构...
put skill    -> 已生成 Skill 基础配置
put recipe 1 -> 已生成 Recipe 1 / 6
put recipe 2 -> 已生成 Recipe 2 / 6
...
finish draft -> 隐藏状态卡，展示完整 Skill / Recipe 草稿卡
```

状态事件只用于展示，不参与保存。真正可保存的数据仍然只来自 `finish` 后组装出的完整 `skill_studio.draft`。

草稿修改也应复用同一套分片机制：

- 已有草稿作为当前 `skill_studio_session_id` 下的 source of truth。
- Agent 优先提交 patch；只有完整替换对象时才提交被修改的 Skill 或 Recipe 小块。
- 未修改的 Recipe 沿用当前草稿版本。
- `finish` 后重新组装完整草稿并替换前端 currentDraft。

这样用户点击“让 AI 调整”时，Agent 不需要把所有 Recipes 全量重传，也不会因为一个完整草稿 tool_call 过大导致 Hermes 读行失败。

传输层仍应加安全线：Hermes subprocess stdout 读取应设置更高的 line limit，并允许通过环境变量调整。这个只是防止其他 ACP 消息偶发过大，不应替代分片草稿协议。

### 草稿局部修改优化：Agent 只提交 patch

分片提交解决了“完整草稿单次 tool_call 过大”和“前端长时间等不到真实进度”的问题，但如果用户只是要求局部修改，例如“把关键词删几个”“只改某个 Recipe 的提示词”，Agent 仍然不应该重新传一遍完整 Skill 或多个 Recipes。

更好的方案是：**当前草稿留在 plugin/session 里，Agent 只提交 patch，最后再 finish 输出完整草稿给前端。**

#### 当前问题

没有 patch 工具时，局部修改通常会退化为：

```text
用户点击“让 AI 调整”
  ↓
Agent 追问修改方向
  ↓
Agent 重新 put Skill / put Recipe 1 / put Recipe 2 / ...
  ↓
finish 输出完整草稿
```

这会带来三个问题：

- 用户只是改一个字段，却看到“已生成 Recipe 1 / 6、2 / 6...”这类像重新生成的状态。
- Agent 容易误改或漏传未修改 Recipe，导致草稿结构变化。
- tool_call 次数和传输数据量仍然偏大，修改体验不够轻。

#### 工具设计

新增工具：

```text
freezone_patch_agent_catalog_draft
```

Skill patch 示例：

```json
{
  "skill_studio_session_id": "public-service-video-skill-001",
  "target": "skill",
  "patch": [
    {
      "op": "replace",
      "path": "/triggers/keywords",
      "value": ["公益短片", "公益视频"]
    }
  ]
}
```

Recipe patch 示例：

```json
{
  "skill_studio_session_id": "public-service-video-skill-001",
  "target": "recipe",
  "recipe_id": "public-service-video-script",
  "patch": [
    {
      "op": "replace",
      "path": "/system_prompt",
      "value": "新的 system_prompt..."
    }
  ]
}
```

第一版只支持三个操作：

```text
replace
add
remove
```

路径使用 JSON Pointer：

```text
/category
/description
/triggers/keywords
/planning/conduct_rules/0
```

Recipe 不用数组下标定位，必须优先使用 `recipe_id`，避免 Recipe 顺序变化后改错对象。

#### plugin 应用规则

plugin 内部继续维护当前草稿会话：

```python
_PENDING_SKILL_STUDIO_DRAFTS[session_id] = {
    "skill": ...,
    "recipes": {index: recipe}
}
```

`freezone_patch_agent_catalog_draft` 的执行逻辑：

```text
1. 根据 skill_studio_session_id 找到当前 draft。
2. target=skill 时，patch draft["skill"]。
3. target=recipe 时，用 recipe_id 在 draft["recipes"].values() 中找到目标 Recipe。
4. 对目标对象应用 JSON Pointer patch。
5. 发出 skill_studio.status，说明已更新哪个部分。
6. 不直接展示完整草稿；完整草稿仍然由 finish 统一输出。
```

patch 应用第一版要严格：

- `path` 必须以 `/` 开头。
- `target=recipe` 时，`recipe_id` 已经定位目标 Recipe，`patch.path` 必须是 Recipe 对象内部路径，例如 `/system_prompt`、`/must_have_items`，不要写 `/recipes/<recipe_id>/system_prompt`。
- 不支持修改 `id`，除非后续明确需要。
- 不支持穿透不存在的父级。
- list 只支持数字 index 和 `-` 追加。
- patch 失败必须返回 tool error，不吞错误。
- patch 失败不能破坏原 draft。

#### 修改流程

局部修改的推荐流程：

```text
用户点击“让 AI 调整”
  ↓
前端 tool result 带 currentDraft
  ↓
Agent 追问一个问题
  ↓
用户回答
  ↓
Agent:
  freezone_begin_agent_catalog_draft(mode=edit, expected_recipe_count=当前总数)
  freezone_patch_agent_catalog_draft(...)
  freezone_finish_agent_catalog_draft(...)
  ↓
前端收到完整 skill_studio.draft，替换 currentDraft
```

`patch` 工具只更新 plugin/session 中的草稿，不直接作为前端保存源。前端仍然只保存 `finish` 后得到的完整 `skill_studio.draft`。

#### Agent 使用规则

prompt / tool schema 需要明确：

```text
For local edits, prefer freezone_patch_agent_catalog_draft.
Use put_skill / put_recipe only when replacing an entire Skill or Recipe object.
Always finish with freezone_finish_agent_catalog_draft.
Do not regenerate unchanged Recipes.
For target=recipe, pass recipe_id and use patch paths relative to that Recipe object,
for example /system_prompt or /must_have_items; never use /recipes/<recipe_id>/...
inside patch.path.
```

也就是说：

- 删除或补充关键词：用 patch。
- 修改 `description`、`planning_prompt`、`system_prompt`：用 patch。
- 调整某个 Recipe 的单个字段：用 patch。
- 完整重写一个 Recipe：可以用 `freezone_put_agent_catalog_recipe`。
- 大幅重构整个 Skill / Recipes：可以重新 put 对应对象，但仍不应重传未修改项。

#### 状态显示

patch 工具应发真实进度状态，而不是“重新生成 Recipe”：

```json
{
  "type": "skill_studio.status",
  "status": "draft_patch_applied",
  "message": "已更新 Skill 触发关键词"
}
```

Recipe 示例：

```text
已更新 Recipe：公益短片脚本与分镜
```

这样用户看到的是“改了哪里”，不是“重新生成到了第几个 Recipe”。

#### 测试要求

至少覆盖：

- patch Skill keywords 后 finish，draft 里 keywords 变化，Recipes 保持不变。
- patch Recipe `system_prompt` 后 finish，只有目标 Recipe 变化，其他 Recipe 保持不变。
- invalid path 返回错误，原 draft 不被破坏。
- remove keyword list item 可用。
- prompt / schema 明确包含 `freezone_patch_agent_catalog_draft` 和 “local edits prefer patch”。

前端收到草稿后进入 `previewing`：

- 展示 Skill 草稿卡。
- 展示 Recipe 草稿卡。
- 展示 warnings。
- 提供保存、继续调整、查看 JSON、取消。

草稿卡应显示明确状态：

- `未保存`：Agent 已生成或用户已修改，但尚未写入 catalog。
- `已修改`：用户手动编辑过当前草稿。
- `AI 调整中`：正在把当前草稿交给 Agent 继续修改。
- `已保存`：当前草稿已经成功写入用户 catalog。

### 草稿卡片手动编辑

草稿卡不是只读预览，而是可编辑的结构化表单。用户可以不通过 Agent，直接在卡片里修改字段。

可编辑内容包括：

- Skill：
  - ID
  - 分类
  - 描述
  - 触发关键词
  - 节点类型
  - 规划器提示词
  - 提示词风格
  - 行为规则
  - 评价规则
  - workflow template 简表
- Recipes：
  - ID
  - 名称
  - 输出类型
  - action keys
  - `system_prompt`
  - 必需元素
  - 规划器提示词
  - 输出概述
  - 是否需要上游素材输入

手动编辑规则：

- 用户修改字段后，前端立即更新当前草稿状态。
- 草稿卡显示“未保存”或“已修改”状态。
- 保存按钮根据必填校验实时启用或禁用。
- 手动编辑不会立刻写入用户 catalog。
- 用户可以在手动编辑后通过草稿卡片启动 Agent 修改会话，Agent 必须基于最新草稿继续调整。
- 用户点击保存时，保存的是当前草稿卡片里的字段值，而不是最近一条 Agent 回复文本。

### 草稿修改会话

草稿修改不是普通聊天的隐式路由。前端不应根据“短修改句 + 最近有 Skill Studio 草稿”判断用户要进入 Skill Studio；这类判断容易把普通虾画创作误导到 Skill Studio 语境。

草稿修改应由明确的 Skill Studio 事件启动，然后进入一个由 Agent 主导的修改问答会话。修改问答会话中，Agent 可以一个问题一个问题地收集用户偏好；信息足够后，Agent 输出修改后的完整草稿。

#### 未保存草稿的修改

当草稿仍处于 `previewing` 或 `editing` 状态时，用户可以在草稿卡片上点击“让 AI 调整”。这个动作只负责启动修改会话，不要求用户一次性写完所有修改要求。

点击“让 AI 调整”表示用户已经不满足当前草稿，Agent 不能再询问“是否保存当前版本”，也不能提供 `save_now`、`save_current`、`confirm_save` 这类选项。保存动作只属于页面草稿卡里的确认按钮；Agent 修改会话只负责追问修改方向并输出新的完整草稿。

前端应通过 Skill Studio 专用 `tool.result` 返回：

```json
{
  "action": "start_revision",
  "draft": "当前完整 Skill / Recipes 草稿",
  "skill_studio_session_id": "当前草稿会话 ID"
}
```

Agent 收到后应发起问题卡片，例如：

```text
你想主要调整哪一部分？
- 触发条件
- 工作流步骤
- Recipe 提示词
- 评价标准
```

用户回答后，Agent 可以继续追问，也可以在信息足够时使用 `freezone_begin_agent_catalog_draft`、`freezone_patch_agent_catalog_draft` 或 put 工具、`freezone_finish_agent_catalog_draft` 输出新的完整草稿。前端收到新草稿后替换当前 `currentDraft`。

未保存草稿修改的关键规则：

- 修改入口来自草稿卡片动作，而不是前端猜测普通输入框文本。
- 卡片动作只需要点击一次，后续回答都属于 Agent 已经发起的修改问答会话。
- Agent 必须基于前端传回的最新 `draft` 修改；如果用户手动编辑过字段，手动编辑后的 `currentDraft` 是唯一事实源。
- 修改完成前不写入用户 catalog。

#### 已保存内容的再次修改

保存后的内容不应要求用户回到卡片里点“继续修改”。用户已经处在 AI 对话里，保存后自然说：

```text
还是改成现代简约吧
刚才那个不要国潮
把 Recipe 的提示词再收紧一点
```

Agent 应根据对话历史中的保存结果识别这是对最近保存的 Skill / Recipe 做修改，然后进入修改问答会话。

保存结果必须作为 Skill Studio `tool.result` 进入对话历史，至少包含：

```json
{
  "action": "save",
  "saved_to_catalog": true,
  "saved_skill_ids": ["..."],
  "saved_recipe_ids": ["..."],
  "draft": "保存时的完整 Skill / Recipes 草稿",
  "skill_studio_session_id": "当前草稿会话 ID"
}
```

如果历史中的 `draft` 足够完整，Agent 直接基于它发起修改问答。如果历史中只有 ID 或草稿信息不足，Agent 应先读取完整配置，再发起修改问答：

```text
freezone_get_saved_skill
freezone_get_saved_recipe
```

已保存内容修改的流程：

```text
用户自然说“再改一下”
  ↓
Agent 根据历史识别为修改最近保存的 Skill / Recipe
  ↓
必要时读取已保存完整配置
  ↓
Agent 一问一答收集修改意图
  ↓
信息足够后输出 edit 草稿
  ↓
用户确认后保存修改
```

已保存内容修改的关键规则：

- 前端不做“短修改句”判断，也不自动把 `active_skill_studio_context` 注入普通消息。
- 判断是否修改已保存 Skill / Recipe 由 Agent 基于对话历史和用户当前表达完成。
- 如果用户明确要求“生成图 / 执行节点 / 继续画布 / 跑工作流”，应按普通虾画处理，不进入 Skill Studio。
- Agent 不能直接改 catalog；仍然必须先输出 edit 草稿，用户确认后才保存。

#### 修改输出形式

前端展示和保存层仍然只接收完整 Skill / Recipes 草稿；Agent 不能只给用户展示局部字段或自然语言 diff。

但 Agent 到 plugin/session 的传输层应优先使用 `freezone_patch_agent_catalog_draft` 做局部修改：

- plugin/session 中的 current draft 是修改源。
- Agent 只提交字段级 patch。
- `finish` 后由 plugin/session 组装完整 Skill / Recipes 草稿。
- 前端用完整草稿替换 `currentDraft`，保存时仍然只保存完整草稿。

这样既保留完整草稿校验和保存语义，又避免局部修改时重传所有 Recipes。

### 手动编辑与 Agent 修改的同步

当前草稿只有一个权威版本，保存在前端状态中。

```text
Agent 生成草稿 → 前端 currentDraft
用户手动编辑 → 更新 currentDraft
用户点击“让 AI 调整” → 将 currentDraft 作为 tool.result 发给 Agent
Agent 一问一答收集修改意图
Agent 返回完整草稿 → 替换 currentDraft
用户保存 → 保存 currentDraft
```

第一阶段建议采用“编辑锁”避免冲突：

- 用户发起“让 AI 调整”后，前端把当前 `currentDraft` 作为 Skill Studio `tool.result` 发送给后端。
- 请求进行中，草稿表单进入只读状态，卡片显示 `AI 调整中`。
- 用户如果想继续手动修改，可以先取消本次调整；否则等待 Agent 返回。
- Agent 返回完整草稿后，前端用返回结果替换 `currentDraft`，状态回到 `未保存`。
- Agent 返回失败时，保留原 `currentDraft`，状态回到 `已修改` 或 `未保存`，并提示用户可重试。

冲突处理：

- 如果用户手动编辑后又让 Agent 修改，Agent 应保留用户刚刚改过的明确字段，除非用户要求覆盖。
- 如果 Agent 返回草稿缺少用户手动新增的 Recipe，前端不自动合并；直接用 Agent 返回的完整草稿替换，并可在 warnings 中提示“本次修改移除了某些草稿项”。
- 前端第一阶段不做字段级 diff 合并，避免状态复杂化；字段级 patch 只发生在 Agent 到 plugin/session 的草稿构建层。

后续如果需要支持“Agent 调整中用户继续手动编辑”，可以引入 `revision`：

- 每次用户手动编辑或 Agent 替换草稿，`revision` 加 1。
- Agent 请求带上 `base_revision`。
- Agent 返回时，如果前端发现当前 `revision` 已经大于 `base_revision`，不自动覆盖。
- 前端提示用户“草稿已被你手动修改，是否应用 AI 返回版本？”。
- 用户确认后才替换；否则保留当前手动版本。

第一阶段不做 revision 合并，只采用编辑锁，交互更清楚，实现也更稳定。

### 原始 JSON 编辑

高级用户可以在草稿卡里展开“查看 / 编辑原始 JSON”。

规则：

- JSON 编辑区与表单字段双向同步。
- JSON 无法解析时，表单保持上一次有效草稿，保存按钮禁用。
- JSON 解析成功但缺必填字段时，表单同步，保存按钮禁用并标出缺失字段。
- 保存前仍按相同 schema 校验。

### 保存确认

用户点击保存或说“保存”时，前端应展示简短确认：

```text
将保存 1 个 Skill 和 3 个 Recipes。
Skill：ecommerce_detail
Recipes：detail_text_plan、detail_hero_image、detail_split_image
```

确认后再调用保存接口。

保存完成后提示：

```text
已保存。你可以在虾画 Skills 设置里编辑，也可以在输入框输入 `/` 选择它。
```

### 取消

用户取消时：

- 不调用保存接口。
- 不写入用户 catalog。
- 保留聊天记录中的说明和问题选择，但草稿不生效。
- 状态回到普通聊天。

## 内置与用户定制语义

Skill Studio 必须和设置页的 catalog overlay 语义一致。

### 内置项

内置 Skills / Recipes 来自代码目录：

```text
src/novelvideo/freezone/agent_catalog/builtins/skills/*.json
src/novelvideo/freezone/agent_catalog/builtins/recipes/*.json
```

内置源文件不应被用户操作修改。

### 用户项与 overlay

用户配置写入：

```text
output/<username>/_account/freezone/agent_config/skills/*.json
output/<username>/_account/freezone/agent_config/recipes/*.json
```

语义：

- 新建非内置 ID：写完整用户配置。
- 编辑内置项：写完整用户定制副本，同 ID 覆盖展示和使用。
- 禁用内置项：写最小 overlay，例如 `{ "id": "xxx", "enabled": false }`。
- 删除内置项：写隐藏 overlay，例如 `{ "id": "xxx", "hidden": true }`。
- 删除用户自建项：物理删除用户目录里的 JSON。
- 导出配置：不带 `_catalog_*` 响应元数据。

列表展示：

- 纯内置：显示“内置”。
- 内置被用户编辑：显示“已定制”。
- 用户自建：不显示内置标记。

冲突处理：

- create 模式遇到同 ID 用户配置：提示将覆盖已有配置。
- create 模式遇到同 ID 内置配置：提示将创建用户定制版本，不修改内置源。
- edit 模式：允许覆盖当前用户配置或用户定制副本。

### 输入框指定 Skill

虾画聊天输入框支持输入 `/` 唤起启用中的 Skill 列表。这个入口不负责创建 Skill，也暂时不改变 Agent 的执行策略；第一阶段只做展示和可见文本插入，方便用户在对话里明确表达想参考哪个 Skill。

交互建议：

1. 用户在输入框输入 `/`。
2. 前端弹出启用中的 Skills。
3. 每个列表项展示：
   - Skill ID 或显示名称
   - 分类
   - 描述
   - 触发词摘要
4. 用户点击或键盘选择后，输入框插入可见文本，例如 `/ecommerce_detail`。
5. 用户继续输入自然语言请求。
6. 发送后，文本按普通用户输入处理，不携带隐藏 metadata。

优先级：

```text
当前阶段：仅展示启用中的 Skill，用户选择后只插入文本。

后续消费阶段：用户手动指定 Skill > 自动匹配 Skill > 通用虾画规则。
```

约束：

- 第一阶段不影响本轮消息的结构化上下文。
- 指定 Skill 不能覆盖底层画布协议。
- 如果后续接入结构化消费，Skill 不存在、已禁用或校验不通过时，后端应回退到自动匹配，并在回复中提示用户。
- 第一阶段只展示 Skill，不展示 Recipe。Recipe 仍由 Skill 的 `action_key` 关联。

前端数据来源复用现有接口：

```text
GET /api/freezone/agent-config/skills
```

前端过滤：

- `enabled !== false`
- 必填字段有效
- 查询文本匹配 `id` / `category` / `description` / `triggers.keywords`

后续接入执行消费时，发送请求建议使用结构化 metadata，而不是只把 `/skill_id` 混进用户文本：

```json
{
  "content": "帮我做一组详情页",
  "surface_context": {
    "freezone_canvas_id": "user_local_xxx",
    "selected_skill_id": "ecommerce_detail"
  }
}
```

如果现有聊天协议暂时不方便扩展，也可以作为过渡方案在 prompt 前缀中注入；该方案不属于当前展示阶段：

```text
[FREEZONE_SELECTED_SKILL]
id: ecommerce_detail
[/FREEZONE_SELECTED_SKILL]
```

## 数据契约

### Skill 草稿

```json
{
  "id": "ecommerce_detail",
  "enabled": true,
  "version": 1,
  "name": "电商详情页生成",
  "category": "ecommerce",
  "description": "电商详情页与商品图规划能力",
  "aliases": ["商品详情页", "卖点图", "电商海报"],
  "triggers": {
    "keywords": ["详情页", "商品图", "卖点图"],
    "node_scopes": ["textGeneration", "imageGeneration"]
  },
  "planning": {
    "planning_notes": "执行路径说明：先生成详情页文案规划，再基于文案规划生成商品主视觉图提示词或图片节点。若用户已提供完整文案，可跳过文案规划，直接进入图片生成步骤。",
    "prompt_guide": "风格指引",
    "conduct_rules": [
      "每个 workflow step 必须使用 catalog 任务类型作为 node_type，不使用画布内部节点类型",
      "每个 workflow step 的 action_key 必须能匹配某个 Recipe 的 action_keys",
      "下游步骤的 input_strategy 必须明确指向上游 step_id"
    ],
    "default_aspect_ratios": {
      "imageGeneration": "3:4"
    }
  },
  "workflow_templates": [
    {
      "id": "default",
      "description": "默认流程",
      "steps": [
        {
          "id": "text_plan",
          "step_number": 1,
          "node_type": "textGeneration",
          "action_key": "detail_text_plan",
          "prompt_strategy": "user_message",
          "input_strategy": {
            "type": "user_message"
          },
          "need_review": true,
          "multiplicity": "single"
        },
        {
          "id": "hero_image",
          "step_number": 2,
          "node_type": "imageGeneration",
          "action_key": "detail_hero_image",
          "prompt_strategy": "previous_output",
          "input_strategy": {
            "type": "previous_step",
            "step_id": "text_plan"
          },
          "need_review": false,
          "multiplicity": "single"
        }
      ]
    }
  ],
  "evaluation": {
    "quality_threshold": 7,
    "domain_constraints": [],
    "rating_bands": [],
    "visual_review_items": [],
    "text_review_items": []
  }
}
```

Skill 的 `triggers.node_scopes` 使用 catalog 语义层节点范围，不使用画布内部节点类型。可选值固定为：

- `textGeneration`
- `imageGeneration`
- `videoGeneration`
- `audioGeneration`

Skill 的 `workflow_templates.steps[*].node_type` 也使用同一组 catalog 任务类型，不使用画布内部节点类型。禁止在 Skill Studio 草稿里写：

- `textAnnotationNode`
- `imageGenNode`
- `videoNode`
- `audioNode`
- 其他画布内部组件类型

### Skill workflow template 生成规范

`workflow_templates` 是 A 部分产出的“可被后续消费的执行蓝图”。即使 A 部分不负责真正执行 workflow，草稿也必须尽量具备可执行性，避免只生成领域说明。

#### 1. `input_strategy` 必须明确上游来源

不要使用含混写法：

```json
{ "source": "previous_steps" }
```

推荐使用明确结构：

```json
{ "type": "user_message" }
```

```json
{ "type": "user_assets" }
```

```json
{ "type": "previous_step", "step_id": "text_plan" }
```

```json
{ "type": "previous_steps", "step_ids": ["culture_extract", "copy_plan"] }
```

规则：

- 第一步通常来自 `user_message`、`user_assets` 或 `canvas_selection`。
- 下游步骤必须用 `step_id` 或 `step_ids` 明确指向上游步骤。
- 不允许只写“previous steps”“上一步结果”“已有内容”等无法机器解析的泛化来源。
- 如果某一步可以跳过，应在 `condition` 或 `planning_notes` 中说明，不要让 `input_strategy` 模糊承担分支逻辑。

#### 2. `planning_notes` 应写执行路径，而不是只写适用场景

`planning_notes` 不是一句领域介绍。它应该告诉 Agent 如何选择路径、如何安排步骤、哪些步骤可跳过。

推荐包含：

- 默认路径：用户常规输入时如何执行。
- 分支路径：用户已有文案、已有素材、只有主题时分别怎么走。
- 步骤顺序：先做什么，再做什么。
- review 节点：哪些步骤需要用户确认。
- 终端输出：最终生成什么类型的节点或结果。

示例：

```text
默认路径：用户只有商品卖点或 brief 时，先创建 textGeneration 节点生成详情页文案规划，再创建 imageGeneration 节点生成主视觉图。若用户已提供完整文案，可跳过文案规划，直接使用该文案作为图片生成输入。文案规划步骤需要用户 review；图片生成步骤不需要 review。
```

#### 3. `conduct_rules` 应包含硬性执行规则

`conduct_rules` 不应只写“风格统一”“尊重文化”这类质量倾向，也要写 Agent 执行时不能违反的规则。

推荐包含：

- workflow step 的 `node_type` 必须使用 `textGeneration`、`imageGeneration`、`videoGeneration`、`audioGeneration`。
- 每个 step 的 `action_key` 必须匹配某个 Recipe 的 `action_keys`。
- 下游 step 必须明确引用上游 `step_id`。
- 不得跳过必须 review 的中间结果。
- 不得在上游缺失时直接生成终端图片或视频。
- 不得把无关上游素材全部连入下游步骤。
- 多对象、多镜头、多场景类 workflow 应按对象或镜头组拆分节点，而不是塞进一个节点。

#### 4. workflow step 至少补清楚 action key 和上游关系

每个 workflow step 至少应包含：

- `id`：稳定步骤 ID。
- `step_number`：执行顺序。
- `goal_template`：该步骤目标。
- `node_type`：catalog 任务类型。
- `action_key`：对应 Recipe 动作。
- `prompt_strategy`：如 `user_message`、`previous_output`、`llm_refine`。
- `input_strategy`：明确来源。
- `need_review`：是否需要用户确认。
- `multiplicity`：`single`、`per_input` 或结构化数量配置。

如果某个 step 的 `action_key` 找不到对应 Recipe，草稿应给出 warning，保存前应提示用户补齐 Recipe 或修改 action key。

#### 5. 推荐补齐 catalog 完整度字段

Skill 草稿推荐包含以下可选字段，提高设置页管理、检索和后续迁移能力：

- `enabled`: 默认 `true`。
- `version`: 从 `1` 开始，后续大改递增。
- `name`: 面向用户展示的名称。
- `aliases`: 同义词、别名、常见触发表达。

这些字段不是所有版本的最低必填项，但 Agent 生成新 Skill 时应尽量补齐。设置页可继续兼容旧 Skill 缺失这些字段的情况。

### Recipe 草稿

```json
{
  "id": "detail_text_plan",
  "enabled": true,
  "name": "详情页文案规划",
  "output_kind": "text",
  "action_keys": ["detail_text_plan"],
  "system_prompt": "节点级执行指令",
  "must_have_items": ["产品定位", "分屏策划"],
  "planning_prompt": "根据商品 brief，生成详情页文案与分屏策划方案。",
  "result_summary": "商品详情页文案与分屏策划方案",
  "requires_source_media": false,
  "force_enhancement": false
}
```

说明：

- Recipe 字段统一使用下划线命名，不使用驼峰字段。
- `system_prompt` 是 Recipe 被调度执行时的节点级元提示词，用来指导 Agent/LLM 写出可送入对应节点的 prompt、brief 或生成指令。
- `planning_prompt` 是节点工作描述，写这个 Recipe “根据什么做什么”，不写调度机制。
- `result_summary` 是节点产物描述，写业务结果是什么，不写下游执行或 workflow 机制。
- `Skill.workflow_templates.steps[*].action_key` 应能匹配某个 Recipe 的 `action_keys`。
- A 部分只负责生成和保存这些字段，不负责执行 workflow。
- A 部分可以生成 `workflow_templates` 字段作为配置内容，但不保证普通虾画 Agent 会消费它；消费逻辑属于 B 部分。

### Recipe `system_prompt` 编写规范

Recipe 是 Skill 下可被调度的具体动作配方。`system_prompt` 不是最终图片、视频、音频或正文成品的提示词本身，而是**指导 Agent/LLM 写节点 prompt 的 prompt**。

也就是说，Recipe 被调度后，当前 LLM 应根据用户目标、上游 Recipe 输出、参考素材和画布上下文，产出一条可送入对应节点继续执行的 prompt / brief / instruction。

规则：

- `text` Recipe：不要直接写最终文案、脚本、大纲正文；应指导当前 LLM 输出给 `textGeneration` 节点使用的完整提示词/指令。
- `image` Recipe：不要直接写最终图片描述成品；应指导当前 LLM 把上游方案改写成给 `imageGeneration` 节点使用的完整图片生成 prompt。
- `video` Recipe：不要直接写最终视频描述成品；应指导当前 LLM 把上游脚本、分镜或画面方案改写成给 `videoGeneration` 节点使用的视频生成 prompt。
- `audio` Recipe：不要直接写最终音频内容；应指导当前 LLM 把上游文案、情绪和声音要求改写成给 `audioGeneration` 节点使用的音频生成 prompt。

`system_prompt` 里应明确：只输出下游节点 prompt / brief / instruction，不在当前步骤直接完成最终内容生成。

推荐包含以下结构：

- 【角色设定】该节点执行者的专业身份。
- 【输入来源】需要读取的用户目标、画布上下文、上游 Recipe 输出或参考素材。
- 【任务目标】本 Recipe 要完成的 prompt/brief 生成或改写任务。
- 【输出结构要求】要求下游 prompt/brief 包含哪些模块、字段、段落或格式。
- 【质量标准】判断下游 prompt/brief 是否合格的标准。
- 【禁止事项】例如不要跳过上游输入、不要自行声称已经生成图片、不要输出与结构无关的解释。

输出结构要求应描述下游 prompt/brief 必须包含的模块，例如主体、场景、镜头、构图、风格、色彩、文本排版、连续性和负面约束，而不是把这些要求当作当前 Recipe 的最终成品直接输出。

## 必填校验

### Skill 必填

- `id`
- `category`
- `description`
- `triggers.keywords` 至少 1 个

### Recipe 必填

- `id`
- `name`
- `output_kind`
- `action_keys` 至少 1 个
- `system_prompt`
- `planning_prompt`
- `result_summary`

保存前和导入前都必须校验。无效草稿不能保存。

## 实现前必须固定的契约

下面这些契约需要在第一阶段开工前固定下来，避免前端、后端和 Agent prompt 各自按理解实现。

### 结构化事件拆分

问题流和草稿预览必须走 Freezone bridge，而不是普通聊天文本，也不走 dramaclaw 的 `ui_spec` 文本展示链路。当前实现中二者使用不同 bridge 事件：

- `freezone_request_user_clarification`
  - 用于展示选项式澄清问题。
  - 只在 `questioning` 状态出现。
  - 工具写入 clarification pending event，后端 websocket watcher 发出 clarification 事件，前端渲染为可点击问题卡。
  - 该工具只收集用户选择，不写画布、不保存 catalog。
- `freezone_begin_agent_catalog_draft`
  - 用于开始 Skill / Recipe 草稿构建会话。
  - 只传 session、mode、summary、expected_recipe_count、warnings 等轻量信息。
- `freezone_put_agent_catalog_skill`
  - 用于提交或替换 Skill 主体。
- `freezone_put_agent_catalog_recipe`
  - 用于提交或替换单个 Recipe。
- `freezone_patch_agent_catalog_draft`
  - 用于局部修改当前草稿中的 Skill 或某个 Recipe。
  - 适合调整关键词、说明、规则、某个 Recipe 的 `system_prompt` 等局部字段。
- `freezone_finish_agent_catalog_draft`
  - 用于结束草稿构建。
  - 工具根据 session 内已提交或 patch 后的对象组装完整 Skill / Recipe 草稿，写入 Skill Studio pending event。
  - 后端 websocket watcher 发出 `skill_studio.event`，前端渲染为可编辑草稿卡。

这样可以避免 Agent 把问题、解释和草稿混在同一个消息里，也方便前端分别测试。问题阶段可以复用通用 clarification 组件，但草稿阶段必须使用 Skill Studio 专用草稿事件。

传输链路必须和 Freezone 画布协议保持一致：

```text
Hermes Freezone 工具调用
  -> 写入当前 Agent profile 下的 pending bridge 文件
  -> API websocket watcher 读取 pending
  -> 发送对应前端事件给前端
  -> 前端按 turn_id 追加到当前 assistant message 的 uiEvents
```

约束：

- 不从 Hermes `tool.result` 文本里解析 Skill Studio UI。
- 不把 Skill Studio 卡片塞进 `<ui-spec>`。
- 问题工具返回值只表示用户完成了选择，Agent 需要基于返回答案继续生成或修改草稿。
- 草稿工具返回值只表示草稿已进入前端确认链路；保存动作后续走 catalog API。

### 草稿会话标识

Skill Studio 每次进入创建或编辑流程时，都应生成一个 `skill_studio_session_id`。

用途：

- 绑定问题流、问题答案、草稿卡和保存动作。问题流使用 `clarification_id`，建议与 `skill_studio_session_id` 保持一致或可追踪映射。
- 避免多个虾画 Agent 会话同时存在时互相覆盖草稿。
- 用户切换历史 Agent 后，能恢复对应会话的草稿状态。

草稿事件应带上该字段：

```json
{
  "skill_studio_session_id": "skill_studio_01"
}
```

前端保存时也应带上该 ID，便于日志排查和防止误保存旧草稿。问题流事件使用 `clarification_id` 串联到同一个 Skill Studio 过程。

### ID 自动生成规则

Agent 不应向用户追问 `id`。第一阶段统一自动生成。

规则：

- 从用户目标、Skill 名称或 Recipe 名称生成语义化 ID。
- 只允许小写字母、数字、下划线和短横线。
- 中文目标可以由 Agent 生成英文语义 ID，不要求拼音。
- Skill ID 应偏领域能力，例如 `ecommerce_detail`、`public_welfare_short_video`。
- Recipe ID 应偏具体动作，例如 `detail_text_plan`、`poster_image_prompt`。
- Recipe 的 `action_keys` 默认包含自身 ID。
- 如果 ID 与用户配置冲突，前端保存前提示覆盖确认。
- 如果 ID 与内置配置冲突，默认提示将创建用户定制版本，不修改内置源。
- 如果用户没有明确要求覆盖，Agent 可以追加数字后缀，例如 `ecommerce_detail_2`。

保存前仍以服务端校验为准。

### Agent 输出约束

进入 Skill Studio 后，Agent 的完成条件必须是结构化输出，而不是自然语言承诺。

强约束：

- 不能只回复“我已经创建好了”。
- 不能只回复“我已经修改好了”。
- 不能只贴 JSON 到聊天正文。
- 不能只在聊天正文返回局部 diff 或 patch。
- 生成草稿或修改草稿时，必须调用 begin / put 或 patch / finish 草稿工具链，最终由 `freezone_finish_agent_catalog_draft` 产生完整草稿事件。
- 展示问题时，必须调用 `freezone_request_user_clarification`。

如果 Agent 没有调用对应结构化工具，前端不进入保存态，只在聊天里提示需要先生成草稿。

### 保存失败恢复

第一阶段保存顺序仍然是先 Recipes、再 Skill，但需要明确失败处理：

- 保存失败时，前端保留当前草稿卡，不清空。
- 已成功保存的 Recipes 不自动回滚。
- Skill 保存失败时，提示用户重试，并说明可能已有部分 Recipes 写入。
- 用户重试时仍保存当前草稿卡的完整内容。
- 后续可以增加 batch save 接口，再做真正事务语义。

### 原始 JSON 与表单同步优先级

草稿表单是主编辑面，原始 JSON 是高级编辑入口。

规则：

- 表单修改立即更新 `currentDraft`。
- JSON 编辑成功解析后，覆盖表单和 `currentDraft`。
- JSON 无法解析时，不覆盖当前有效草稿。
- JSON 可解析但校验失败时，表单可同步展示，但保存按钮禁用并标出缺失字段。
- 保存永远保存最后一个 valid `currentDraft`。

### A / B 分工边界

A 部分只负责创建、编辑、预览和保存合法 catalog JSON。

B 部分负责普通虾画 Agent 如何消费这些 catalog JSON 来规划和生成画布工作流。

两部分唯一稳定契约是：

- Skill JSON schema。
- Recipe JSON schema。
- `Skill.workflow_templates.steps[*].action_key` 与 `Recipe.action_keys` 的关联。

A 部分不保证生成的 `workflow_templates` 会被立即执行；B 部分实现消费逻辑时再解释这些字段。

## 结构化工具

第一阶段 Freezone 已有两类工具支撑 Skill Studio：问题阶段复用通用澄清工具，草稿阶段使用 Skill Studio 专用草稿工具。

### 问题流工具

```text
freezone_request_user_clarification
```

工具输入：

```json
{
  "clarification_id": "skill_studio_01",
  "title": "我先帮你确定这个 Skill 的方向",
  "description": "选完后我会自动生成 Skill 和 Recipes 草稿；保存前还可以继续修改。",
  "questions": [],
  "allow_recommended": true,
  "allow_skip": true
}
```

字段说明：

- `clarification_id`: 当前问题流 ID。Skill Studio 中建议使用与 `skill_studio_session_id` 一致或可追踪的稳定 ID。
- `title`: 问题卡标题。
- `description`: 面向用户的说明。
- `questions`: 选项式问题数组。
- `allow_recommended`: 是否展示“用推荐配置”。
- `allow_skip`: 是否展示“跳过，直接生成草稿”。

约束：

- 这个工具只用于收集用户选择，不代表已经生成草稿。
- Agent 收到用户答案后，应继续调用 begin / put 或 patch / finish 草稿工具链展示完整草稿。
- 不要用该工具询问 `id`、`category`、`action_keys`、`system_prompt` 等底层字段。

### 草稿工具

```text
freezone_begin_agent_catalog_draft
freezone_put_agent_catalog_skill
freezone_put_agent_catalog_recipe
freezone_patch_agent_catalog_draft
freezone_finish_agent_catalog_draft
```

`begin` 工具输入：

```json
{
  "skill_studio_session_id": "skill_studio_01",
  "mode": "create",
  "summary": "本次草稿说明",
  "expected_recipe_count": 3,
  "warnings": []
}
```

`put skill` 工具输入：

```json
{
  "skill_studio_session_id": "skill_studio_01",
  "skill": {}
}
```

`put recipe` 工具输入：

```json
{
  "skill_studio_session_id": "skill_studio_01",
  "index": 0,
  "recipe": {}
}
```

`patch` 工具输入：

```json
{
  "skill_studio_session_id": "skill_studio_01",
  "target": "recipe",
  "recipe_id": "public-service-video-script",
  "patch": [
    {
      "op": "replace",
      "path": "/system_prompt",
      "value": "新的 system_prompt..."
    }
  ]
}
```

`finish` 工具输入：

```json
{
  "skill_studio_session_id": "skill_studio_01"
}
```

字段说明：

- `skill_studio_session_id`: 当前 Skill Studio 会话 ID。
- `mode`: `create` 或 `edit`
- `expected_recipe_count`: 本次完整草稿预期 Recipe 数量；用于真实进度展示和 finish 校验。
- `skill`: 单个 Skill 草稿。
- `recipe`: 单个 Recipe 草稿。
- `target`: patch 目标，`skill` 或 `recipe`。
- `recipe_id`: patch Recipe 时必须提供，用于定位目标 Recipe。
- `patch`: JSON Pointer patch 操作数组。
- `summary`: 面向用户的自然语言说明
- `warnings`: 风险提示，例如“已有相同 action_key 的 Recipe，建议复用”

约束：

- Agent 不能把最终 JSON 直接贴在聊天正文里作为完成结果。
- Agent 必须通过草稿工具链提交草稿。
- 新建或大幅重写时使用 begin + put skill + put recipe + finish。
- 局部修改时优先使用 begin + patch + finish。
- `finish` 后才产生完整 `skill_studio.draft` 事件。
- 工具调用后不会直接依赖 `tool.result` 渲染卡片；工具会把草稿事件写入 pending bridge，后端通过 websocket 发给前端渲染。

## 前端预览

收到 `skill_studio.event` 且事件类型为 `skill_studio.draft` 后，前端展示一个配置草稿预览。

预览内容：

- 顶部显示 `summary`
- Skill 区域：
  - ID
  - 分类
  - 描述
  - 触发词
  - workflow steps 简表
- Recipes 区域：
  - ID
  - 名称
  - 输出类型
  - action keys
  - 必需元素
- warnings 区域
- 操作按钮：
  - 保存
  - 编辑
  - 取消

保存时调用已有 agent config 保存接口：

```text
POST /api/freezone/agent-config/skills
POST /api/freezone/agent-config/recipes
```

保存顺序建议：

1. 先保存 Recipes。
2. 再保存 Skill。

原因是 Skill 可能引用 Recipe 的 `action_keys`，先让依赖存在更直观。

## 后端职责

### Prompt 构造

当进入 Skill Studio 时，后端给 Agent 的 prompt 应包含：

- 当前任务是创建或编辑 Skills / Recipes。
- Skills / Recipes 是领域配置，不是画布命令。
- 不允许修改底层画布操作协议。
- 必须输出结构化草稿工具调用。
- 已有 Skills / Recipes 摘要，用于避免重复创建。
- 当前画布摘要，可选。

### 已有配置摘要

第一阶段只需要注入简表：

```text
Skills:
- id, category, description, keywords

Recipes:
- id, name, output_kind, action_keys
```

不需要注入完整 `system_prompt`，避免上下文过长。

### 模式识别

第一阶段可以用 prompt 规则识别，不必做复杂分类器：

- 明确包含创建/编辑 Skill / Recipe 意图时进入 Skill Studio。
- 其他情况继续走普通虾画 Agent。

后续如果误判明显，再增加服务端意图分类。

## 编辑已有配置

编辑场景：

- “把电商详情页 Skill 默认图片数改成 3”
- “这个 Recipe 的输出说明改短一点”
- “禁用某个 Skill”

编辑已有配置时，前端保存层仍然只接受完整草稿；Agent 到 plugin/session 层优先使用 patch 做局部修改。

流程：

1. Agent 找到目标配置。
2. 将目标配置作为 edit 草稿会话的当前版本。
3. 对局部字段使用 `freezone_patch_agent_catalog_draft`，对完整对象替换使用 put 工具。
4. `finish` 输出完整 Skill / Recipe 草稿。
5. 前端展示预览。
6. 用户确认后覆盖保存。

## 错误处理

- 生成草稿缺必填字段：前端显示不能保存，并标出缺失字段。
- 与已有 ID 冲突：
  - create 模式：提示将覆盖已有配置，要求用户确认。
  - edit 模式：允许覆盖。
- Recipe action key 重复：
  - 不阻断保存。
  - 在 warnings 中提示可能与已有 Recipe 冲突。
- Agent 未调用结构化工具：
  - 聊天中提示“需要生成配置草稿后才能保存”，不要自动保存。

## 测试建议

### 后端测试

- 普通请求“做个电商海报”不进入 Skill Studio。
- “创建一个电商详情页 Skill”进入 Skill Studio。
- Skill Studio prompt 包含已有 catalog 摘要。
- Skill Studio prompt 明确禁止修改底层画布协议。

### 前端测试

- 收到 `skill_studio.event` 的草稿事件后显示预览卡。
- 缺必填字段时保存按钮禁用。
- 保存时分别调用 skills 和 recipes 接口。
- 用户取消后不保存。

### 集成测试

- 用户通过对话创建 Skill + Recipe。
- 前端预览后确认保存。
- 文件落到账号级 catalog。
- 设置页刷新后能看到新配置。

## 第一阶段验收

- 用户明确要求创建 Skill / Recipe 时，Agent 能返回结构化草稿。
- Skill Studio 卡片由 Freezone bridge 的 `skill_studio.event` 触发，不依赖 Hermes `tool.result` 文本解析。
- 前端能展示草稿并保存。
- 普通虾画创作请求不会被切到 Skill Studio。
- 保存后的 JSON 能被设置页读取、编辑、导入、导出。
- 不影响虾导 Agent。

## 分工建议

负责 A 部分的人可以独立完成：

- Skill Studio 模式 prompt。
- 草稿工具契约。
- 前端草稿预览。
- 保存/取消交互。
- 对应测试。

与 B 部分的唯一硬依赖是 JSON schema。只要字段契约稳定，B 可以用手写 JSON 或 A 生成的 JSON 继续实现“用 Skill 生成工作流”。
