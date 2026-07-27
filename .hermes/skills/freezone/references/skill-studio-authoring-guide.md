# 虾画 Skill Studio 作者指南

这份指南用于 Skill Studio 创建、编辑、总结、沉淀或保存 Skill / Recipe 的场景，包括：

- 用户从零描述一个想要的新 Skill / Recipe。
- 用户根据某个工具、节点能力或 tool schema 创建 Skill / Recipe。
- 用户明确要求把当前虾画画布、当前流程、选中节点或已有工作流总结、沉淀、保存、转成 Skill / Recipe。

目标不是把字段填满，也不是描述画布里“有什么节点”，而是提炼这套能力“为什么能复用”。好的 Skill 应该让下一次类似项目能按同一方法规划、生成、审核和局部返工。

## 0. 先判定来源模式

在做 capability modeling、读取画布或提问前，必须先判定本轮 Skill Studio 的来源模式。当前处在虾画界面、前端注入了 canvas ontology，并不等于用户要从当前画布沉淀 Skill。

### `new_from_user_brief`

用户说“我想做 / 新建 / 创建 / 制作一个 X Skill / Recipe”，但没有明确说“当前画布 / 当前流程 / 选中节点 / 这个项目 / 这个工作流 / 已有工作流”时，默认是从用户简述创建新 Skill。

规则：

- 主来源是用户文字和后续回答。
- 当前画布只能作为环境背景，不是内容证据。
- 不要读取节点详情、节点 schema、连线目录或把 ontology 当案例事实。
- 不要让当前画布影响 Skill 名称、关键词、description、Recipe 边界或约束。
- 不要问“是否保留当前项目具体案例 / 当前品牌 / 当前角色 / 当前剧情”。
- 如果用户简述很短，先问 3-5 个高层问题，覆盖主题/领域、受众/场景、输出范围、风格/语气、工作流粒度。

### `distill_from_canvas`

只有当用户明确说“把当前画布 / 当前流程 / 选中节点 / 这个项目 / 这个工作流 / 已有工作流总结、沉淀、保存、转成 Skill / Recipe”时，才进入画布沉淀。

规则：

- 问任何画布沉淀问题前，必须先调用 `freezone_get_canvas_ontology` 读取画布证据。不要用 canvas summary 作为 Skill Studio 提问依据。
- 如果 ontology 缺少风格、prompt、关键媒体或依赖关系证据，再补读少数关键节点详情，例如主角色锚点、道具锚点、核心分镜、最终合成节点。不要没读 ontology 就直接提问。
- 先做 `canvas_workflow_analysis` 和 `prompt_evidence_analysis`。
- 首轮问题必须基于画布证据生成 2-4 个高质量问题；每题通常给 3-5 个用户看得懂的选项，除非确实只有二选一。不要固定只问“保留具体案例还是抽象模板”和“复用方式”两个问题。
- 提问前先识别当前制作风格和可复用协议，例如制作类型、视觉风格、镜头/构图语言、角色/道具锚点、分镜或视频阶段、音频/合成规则、硬约束和可变输入。问题和选项要带出这些识别结果，不要只说“当前案例”。
- 面向用户提问时不要出现 `Recipe`、`Recipes`、`配方`、`allowed_recipe_ids`、`workflow_templates`、`videoCompose`、`schema` 等内部实现词；用“能力模块”“执行步骤”“复用方式”“细粒度复用”“简化复用”等产品语言表达。
- 面向用户的所有 Skill Studio 内容必须跟随用户当前语言：用户用中文就用自然中文，用户用英文就用自然英文。分析摘要、问题、选项、进度说明和工具后的自然语言回复都要一致；不要中英混杂。中文用户场景下，不要输出英文小标题或英文过渡句，例如 `Prompt evidence`、`creative contract`、`Let me check`、`Now I'll submit`。
- 问题卡片前先用一句话说明你基于画布看到了什么，例如“我看到这张画布像是一个广告短片流程：先固定角色和道具，再做分镜，再生成逐镜视频，最后加音频并合成。”不要暴露 ontology、schema 或工具名。
- 仍然不要只按节点类型摘要。

### `edit_existing_catalog`

当用户要修改已有 Skill / Recipe、刚保存的配置或当前草稿时，来源是已有配置/草稿，不是当前画布。需要时读取已保存配置，再做局部编辑或追问。

## 1. 先做 capability modeling

无论来源是用户一句话、tool schema，还是当前画布，都先在内部完成 `capability modeling`。不要直接沿着 schema 字段逐项生成。

必须先判断：

- **目标用户**：这个 Skill 帮谁解决什么具体创作问题。
- **输入来源**：用户文字、已有节点、参考图、视频片段、音频、项目资产或画布上下文。
- **输出物**：最终产物是提示词、文案、图片、视频、音频、合成结果，还是可执行工作流。
- **执行路径**：能力应该拆成哪些阶段，哪些阶段可并行，哪些阶段必须等待上游。
- **质量闸门**：每个阶段什么算合格，什么必须返工。
- **失败/返工策略**：用户改一处时，是重做全部，还是只重做某个能力模块、节点或片段。
- **可复用边界**：哪些是本次案例变量，哪些是跨项目方法。

如果做不到这些判断，先问 1-2 个高层问题，而不是问字段名。

## 2. 不要被 tool schema 带偏

tool schema 只说明字段能填什么，不说明一个好 Skill 应该怎么思考。

硬规则：

- Do not treat tool schemas as authoring guidance.
- schema fields are final serialization constraints, not the creative plan.
- 不要把 schema 字段逐项问用户，例如 id、category、action_keys、system_prompt、node_type、requires_source_media。
- 不要把 tool schema 里的参数名搬进用户可见问题。
- 不要把 Recipe 写成字段说明书。
- 不要因为 schema 里有某个字段，就强行生成空泛内容填进去。

正确顺序：

1. 先做 `capability modeling`。
2. 再决定 Skill / Recipe 的能力边界。
3. 再写执行路径、质量闸门和返工规则。
4. 最后才把结果序列化进 schema 字段。

坏输出通常长这样：

- “Skill 名称是什么？”
- “Skill 分类是什么？”
- “是否保存固定节点拓扑？”
- “请提供 action_keys。”
- “你是一位专业设计师，负责生成高质量内容。”

这些看起来规整，但不能显著提高后续生成质量。

## 3. 从画布沉淀时先做 canvas_workflow_analysis

生成草稿前，先在内部完成 `canvas_workflow_analysis`。这个分析不要原样展示给用户，但必须驱动后续问题和草稿。

全画布沉淀时，先读全局上下文：

- 问题卡片前必须先调用 `freezone_get_canvas_ontology` 完成画布证据读取。
- 不要用 `freezone_summarize_canvas` 代替 ontology；summary 太薄，不能作为 Skill Studio 提问依据。
- Do not read every node detail one by one.
- 只有 ontology 缺少草稿必需字段时，才补读少数关键节点详情，例如主角色锚点、核心分镜、最终合成节点。
- 不要为了“更详细了解画布”把所有节点逐个 `get_node_detail`；这会拖慢流程并把 Skill Studio 变成噪音很大的节点巡检。
- 如果没有 ontology 证据，不要调用 `freezone_request_user_clarification` 去问带风格判断、流程判断或适用范围的问题；应先调用 `freezone_get_canvas_ontology`。

必须分析：

- **拓扑主链路**：从源设定、参考图、提示词、生成节点到合成/终稿的主要路径。
- **并行分支**：角色、道具、场景、分镜、视频片段、音频等是否并行准备。
- **汇合点**：哪些节点汇入分镜、视频片段、音频或合成节点。
- **重复约束**：从多个节点 prompt 中抽取反复出现的硬规则，例如角色外观锁定、单视角、禁止分身、无尾巴、Logo 可读、最后定格。
- **prompt_evidence_analysis**：先从节点 prompt、媒体事实、文件名、引用关系和边中抽取重复证据，再总结拓扑。由这些证据归纳当前场景的 `domain_contract` 或 `creative_contract`，不要从 displayName 或节点类型直接推断。
- **skill_identity_analysis**：在 prompt evidence 之后决定 Skill 身份。把证据词分成 `case_variables`、`reusable_protocol_terms`、`output_format_terms`、`use_case_terms`、`workflow_method_terms`，用于生成名称、ID、描述和关键词。
- **decision_matrix**：提问前必须把证据分到这些层，不要混在一起：
  - `production_method`：这套流程产出什么，以及通过哪些阶段产出，例如“角色锚点 + 道具锚点 + 分镜草图 + 逐镜视频 + 音频 + 最终成片”。
  - `visual_language`：有证据支撑的视觉/叙事风格。不要从节点名、品类或单个词硬猜；如果只有“光影”等泛词，标记为证据不足，向用户询问要保留的视觉方向。
  - `case_variables`：当前品牌、角色、产品、故事、台词等一次性内容。
  - `reusable_protocol`：阶段顺序、锚点继承、审核闸门、分支汇合、返工范围等可复用方法。
  - `hard_constraints`：不能破坏的规则，例如角色一致性、道具单视角、指定画幅、分镜必须先确认。
  - `start_options`：每次使用前应该让用户选择的参数，例如画幅、镜头数、是否保留 Logo、音频模式、执行方式。
  - `applicability_scope`：适用范围。这个通常后置，不要在首题就问“覆盖哪些品类”。
- **比例和时长事实**：按节点实际字段与媒体宽高归纳，不要只看 displayName。
- **审核闸门**：识别哪些阶段需要用户确认，哪些阶段可并行，哪些阶段必须等待上游完成。
- **可复用边界**：区分项目专属信息和可抽象方法。品牌名、角色名、具体台词通常是可替换变量；阶段顺序、引用规则、质量闸门通常是可复用能力。

不要只按节点类型做摘要。`imageGenNode -> videoNode -> audioNode -> videoComposeNode` 只是实现形态，不是 Skill 价值。

## 4. 首轮问题只问高价值抽象选择

如果用户没有明确说“用默认推荐配置”“直接生成”“不要问”，可以先问高层问题。问题必须帮助决定抽象边界，并且必须匹配来源模式。

`new_from_user_brief` 的推荐问题：

- **主题/领域**：这个 Skill 要服务哪个主题、行业、内容类型或任务场景？
- **受众/使用场景**：最终内容给谁看，在哪个平台、渠道、课堂、团队或业务场景使用？
- **输出范围**：Skill 要产出策划、脚本、分镜、提示词、图片、视频、音频、合成计划，还是完整工作流？
- **风格/语气**：需要什么情绪、审美、表达尺度、合规边界或品牌/人设语气？
- **工作流细致程度**：希望把关键步骤分别沉淀成可单独复用的能力模块，还是先做较少步骤的端到端流程？

`new_from_user_brief` 不要问：

- 是否保留当前项目的具体案例。
- 是否保留当前品牌、角色、剧情或节点结构。
- 是否读取当前画布作为来源。

`distill_from_canvas` 的推荐问题：

- **下次主要复用什么？**：先问这套流程要沉淀成什么方法，而不是先问适用品类。例如“复用完整短片制作流程：角色/道具先定稿，再做分镜、逐镜视频、音频和成片”“复用核心步骤：角色/道具/分镜/视频保持，音频和成片按需处理”“只复用轻量短片方法：适合快速生成类似广告片”。
- **哪些效果必须保持？**：把识别出的视觉/叙事风格作为可读选项，选项必须引用画布证据；如果证据不足，选项应是“每次由用户指定视觉方向”“参考当前画面但不写死风格”“让我补充要保留的视觉风格”，不要硬写“光影风格广告”这种空泛识别。
- **下次可以替换哪些内容？**：当前角色、品牌、道具、剧情是固定样例、默认样例，还是都让用户每次指定？选项要说明对下次使用的影响，例如“角色和产品都可替换，但制作流程保持一致”。
- **复用方式要多细？**：选择细粒度复用、标准复用或轻量复用。细粒度可分别沉淀角色锚点、道具锚点、分镜、逐镜视频、音频等；标准复用保留关键阶段；轻量复用只保留端到端短片方法。不要在问题文案里说 Recipe，也不要把最终合成作为用户要选择的粒度项。
- **哪些规则不能变？**：用用户能理解的话询问必须保留的质量规则，例如角色一致、道具角度固定、分镜先确认、视频片段时长一致、品牌露出清晰。不要直接用“硬约束”做标题。
- **每次开始前要确认什么？**：询问画幅、镜头数量、时长、是否保留品牌 Logo、音频模式、执行方式等用户可感知选择。不要直接用“开始前选项”做标题。
- **适用范围**：只在前几项已经清楚后再问。不要首题就问“覆盖哪些产品广告”。更好的问法是“这套方法主要给哪些项目复用”，选项从方法出发，例如“产品角色化广告短片”“品牌 IP 角色短片”“带参考图和道具锚点的短视频流程”。

提问质量规则：

- 每个问题只问一个决策，不要把风格、硬约束、执行阶段和最终成片规则塞进同一个选项。
- 一个选项如果超过一行半，通常说明它混入了太多决策，应拆成多选项或下一题。
- 选项应体现画布证据，但不能直接复述节点列表。用户看到后应能判断“下次使用会怎么变”。
- 选项文案要说明选择后的效果，不要说实现细节。例如写“下次换产品时，角色和道具可以重新指定，但分镜到成片的流程保持一致”，不要写“case_variables 变成 input_parameters”。
- 不要用“问题 1 / 问题 2 / 问题 3”作为标题；标题本身要是用户能理解的问题。
- 不要把“最终汇入合成节点”这种内部说法暴露给用户；可以说“最终统一合成为一条完整短片，不把零散片段当最终结果”。
- 不要用“通用广告”“光影风格”“工作流模板”这类空泛词替代真正的制作方法。

不要把首轮问题浪费在低层字段：

- 不要先问 Skill 名称。
- 不要先问 Skill 分类。
- 不要先问固定拓扑；具体节点数量和依赖由每次运行的动态计划决定。
- 不要问 id、action_keys、system_prompt、node_type、schema、link_type、模型参数。

这些字段应由 Agent 从画布和用户选择中推断。只有用户明确要求改名称或分类时才询问。

## 5. 生成草稿的最低质量线

生成出的 Skill 至少要包含：

- **Skill 描述**：说明可复用能力，而不是复述当前案例。
- **Skill 身份**：名称、ID、description 和 triggers.keywords 必须来自 `skill_identity_analysis`，不能只由工作流方法或节点类型决定。
- **planning.planning_notes**：从动态规划规则开始，写清阶段顺序、任务类型、action_keys、依赖约束、可并行规则、审核/等待行为和比例策略。
- **planning.conduct_rules**：写硬执行规则，例如先锁角色再做道具，分镜审批后才能生成视频，合成前必须有视频/音频输入。
- **evaluation.domain_constraints**：写从画布事实提炼出的硬约束，不写空泛评价。
- **domain_contract / creative_contract**：把当前场景最影响质量的复用协议写入 planning / conduct_rules / evaluation 和 Recipe 质量标准。不要新增 schema 字段，也不要只塞进某个 Recipe prompt。
- **动态拓扑约束**：说明本 Skill 在运行时如何决定节点数量、依赖、并行分支、审核闸门与终端合成，不保存固定工作流模板。
- **Recipes**：按能力边界拆分，而不是机械按节点类型拆分。

## 6. Skill Identity 与抽象边界

抽象不是抹平。用户选择“抽象成通用模板”时，Agent 应删除不可复用的案例变量，但保留最能代表这套能力的可复用协议、产物形态和使用场景。

先把 prompt evidence 中的词分成五类：

- `case_variables`：具体品牌名、具体人物/角色名、具体产品名、一次性剧情、一次性台词、项目专属口号。抽象模板中应删除、参数化或降为示例。
- `reusable_protocol_terms`：跨项目可复用的创作协议、领域口径、风格语言、规则边界、声音人设、玩法机制、审核标准。抽象模板中应保留。
- `output_format_terms`：Skill 产物形态，例如短片、海报、分镜表、报告、课件、音频、游戏资产、合成计划。
- `use_case_terms`：使用场景，例如品牌广告、教学讲解、合规审查、数据复盘、角色设定、产品展示。
- `workflow_method_terms`：内部方法，例如角色锚定、道具锚定、分镜参考、逐镜生成、音频混合、质量闸门。

Skill 名称、ID、description 和 `triggers.keywords` 必须优先组合：

```text
reusable_protocol_terms + output_format_terms + use_case_terms
```

`workflow_method_terms` 可以补充，但不能独占 Skill 身份。不要把一个有明确领域协议的 Skill 命名成只有“角色驱动”“分镜流程”“数据处理”“文档生成”这类内部方法词。

关键词必须覆盖四类：

- **protocol keywords**：可复用协议词。
- **output format keywords**：产物形态词。
- **use case keywords**：应用场景词。
- **workflow method keywords**：工作流方法词。

坏模式：

- 名称只来自节点拓扑或流程方法。
- 抽象模板时把可复用协议词和案例变量一起删除。
- keywords 只剩品牌变量，或只剩流程节点词。
- description 第一屏只描述“先 A 再 B 再 C”，没有说明这套能力适合什么协议、产物和场景。

## 7. Recipe 拆分原则

Recipe 的边界应对应可复用能力模块。

常见拆分：

- **角色/主体锚定**：把主角、IP、产品主体或关键视觉资产锁定成可复用参考。
- **道具/产品锚定**：生成独立产品图、角色关联道具、Logo 可读版本或单视角参考。
- **风格锁定/创意简报**：整合品牌、角色、色彩、语气、镜头语言和禁止事项。
- **分镜/场景拆解**：把叙事框架扩展成面板、镜头、台词和行动号召。
- **视频片段生成**：按分镜段落生成多个短片段，并保持节点引用链完整。
- **音频/音乐生成**：生成音效、旁白、BGM 或音乐规格。
- **合成计划**：如需 AI 辅助剪辑决策，用文本 Recipe 生成片段顺序、音频层级、转场、时长和输出比例计划；真正的最终合成由运行时动态计划创建终端 `videoComposeNode`。

不要把 `videoCompose`、最终媒体合成、最终成片组装作为 Recipe 拆分选项，也不要把终端合成步骤计入 Recipe 数量。正确表达是“3 个 Recipe + 最终 videoCompose 工作流步骤”，不是“包含合成的 4 个 Recipe”。

不要只生成“图片 Recipe / 视频 Recipe / 音频 Recipe”这种按节点类型命名的泛化模块。它们通常太弱。

## 8. domain_contract / creative_contract 写法

从画布沉淀 Skill 时，不要只总结“有什么节点”。必须先做 `prompt_evidence_analysis`：从节点 prompt、媒体宽高/时长、source filename、引用关系和边中提取重复证据，再归纳当前场景的 `domain_contract` 或 `creative_contract`。

这个 contract 不是新 schema 字段，而是要落进现有字段：

- `planning.planning_notes`：说明协议如何影响执行路径和阶段顺序。
- `planning.conduct_rules`：写成硬执行规则。
- `evaluation.domain_constraints`：写成可检查的质量约束。
- `planning.planning_notes` / `planning.conduct_rules`：写明阶段继承、例外、禁止事项与动态依赖规则。
- Recipe `system_prompt` / `must_have_items`：写入该 Recipe 需要保留或转换的证据。

不同领域的 contract 可能不同：

- 视觉广告：视觉语言、表演风格、品牌调性、阶段性风格例外、合成不生成新风格。
- 数据分析：指标口径、时间范围、单位、过滤条件、图表解释边界。
- 法律/合规：管辖地、条款依据、风险等级、不可替代律师意见等边界。
- 教学内容：年级、知识点、讲解节奏、练习难度、禁用超纲概念。
- 游戏资产：视角、比例、动作规范、碰撞/状态规则、UI 反馈规则。
- 音频内容：声音人设、语速、情绪、音色、禁用噪声或冲突音乐。

视觉广告类画布的写法示例：

```text
prompt evidence:
- "皮克斯3D卡通渲染", "皮克斯经典圆润人物建模"
- "C4D + Octane渲染器", "暖橙金色调阳光光影"
- "参考迪士尼角色动画表演方式"
- "纯铅笔素描线稿", "不上颜色", "只有黑白线条"

creative contract to write into existing fields:
- 全局视觉语言：Pixar 3D cartoon, C4D + Octane, soft studio lighting, rounded body shapes, no harsh edges.
- 阶段例外：storyboard uses black-and-white pencil sketch only; no color, no 3D render.
- 继承规则：character and props inherit the global render language; video segments inherit character/prop anchors and Disney-like exaggerated performance; videoCompose does not generate new creative content.
```

不要只写：

```text
保持皮克斯风格一致，光影柔和。
```

这太弱，无法指导分镜、视频和合成阶段做不同处理。

## 9. Recipe system_prompt 写法

Recipe `system_prompt` 不是角色扮演套话，也不是最终下游 prompt 本身。它是一个转换器：指导当前 Agent / LLM 如何把上游输入转成下游节点可执行提示词或指令。

必须写清：

- 【输入来源】：来自用户文字、当前画布、选中节点、上游媒体还是前一步 Recipe。
- 【任务目标】：本 Recipe 要把输入转成什么下游指令。
- 【输出结构要求】：下游指令必须包含哪些模块。
- 【质量标准】：可检查、可返工的标准。
- 【禁止事项/约束】：不要做什么，哪些错误会污染下游。

不要只写：

```text
你是一位专业导演，擅长生成高质量视频提示词。
```

应写成：

```text
你将把上游分镜表、角色锚点和道具锚点，转换成单段 videoGeneration 节点可执行的视频提示词。输出必须包含角色一致性、引用来源、镜头动作、音效、时长、比例和负向约束。重要：你的输出是一条提示词/指令，将被送入下游 videoGeneration 节点执行；不要自己生成最终视频内容。
```

## 10. 动态工作流规划要求

Skill 不保存固定节点拓扑。每次运行时，Agent 根据用户本次目标、输入素材、Skill 规则和可用 Recipe，生成完整的 `freezone_workflow_plan.v1`。

Skill 草稿必须提供足够明确的规划约束：

- 阶段顺序和允许并行的阶段。
- 每个阶段允许使用的 Recipe `action_keys`。
- 上游输入、素材继承和引用规则。
- 节点数量如何由本次需求决定。
- 图片、视频等媒体的默认比例与阶段例外。
- 审批、等待、质量闸门和局部返工边界。
- 需要最终合成时，终端 `videoComposeNode` 的输入条件。

`videoCompose` 不是 Recipe：

- 不要为 `videoCompose` 创建 Recipe。
- 不要声称 Recipe 会直接驱动 `videoComposeNode` 生成内容。
- 如需 AI 辅助剪辑决策，创建 `textGeneration` Recipe 生成合成计划，再由动态 WorkflowPlan 添加终端合成节点。
- 终端合成只能消费已生成的视频和音频资产，不能把策划文本或普通 prompt 当作媒体输入。

动态计划必须显式携带每个可执行节点的 `recipeId`，并通过 Skill 的 Recipe 白名单和 WorkflowPlan 契约校验后才能创建画布节点。

## 11. 从提示词抽硬约束

画布 prompt 中重复出现的短语通常比节点名更重要。必须提炼成可执行规则。

示例：

- “无尾巴” -> 角色属性校验和负向提示词规则。
- “只出现一次，不得重复角色或分身” -> 视频片段一致性规则。
- “相机只展示正面单面” -> 道具单视角锚定规则。
- “纯铅笔素描线稿，不上颜色” -> 分镜风格闸门。
- “最后 Logo 定格收尾” -> 最终面板/最终镜头规则。
- “参考角色/道具/分镜” -> 节点引用链完整性规则。

不要把这些压缩成“保持风格一致”。那不是可执行规则。

## 12. 比例和媒体事实

比例要从节点字段和媒体宽高一起判断。

- 角色/产品道具常见是 1:1。
- 分镜可能是 16:9。
- 视频节点的字段和实际宽高可能不一致；如果宽高是 720x1280，应识别为竖屏事实，并在 planning 里写清“字段默认”和“实际输出”差异。
- 如果 workflow 有多种比例，不要把所有 task type 都写成同一个默认比例；主比例写入 `planning.default_aspect_ratios`，变体写入 workflow step。

## 13. 输出时避免低质量模式

不要输出这些模式：

- 只按节点类型总结：“先图片，再视频，再音频，再合成”。
- Skill 名称、ID 或关键词只按 workflow_method_terms 生成，缺少可复用协议、产物形态和使用场景。
- Recipe system_prompt 只是角色扮演套话：“你是一位专业导演/设计师”。
- 评价标准只有“风格一致”“质量良好”“广告感强”。
- planning_notes 只罗列阶段名称，没有说明动态节点数量、依赖、并行和审核规则。
- 把皮克斯、赛博朋克、水墨、黏土动画等强风格只写成“光影风格”字段，没有形成可执行的 creative_contract。
- 把当前品牌和角色硬编码到所有字段，导致无法复用。
- 把所有 Recipe 都写成同一种 prompt compiler，没有区分输入、输出和质量闸门。
- 把 tool schema 字段描述当成 Skill 内容。
- 首轮问题围绕 id、category、action_keys、node_type、schema 字段展开。
- 为 `videoCompose` 创建 prompt Recipe，或声称 Recipe 会直接驱动 `videoComposeNode` 生成最终视频。

好的输出应让用户看到：这不是一份摘要，而是一套可以再次执行的创作工艺。
