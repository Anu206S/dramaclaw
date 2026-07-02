---
name: freezone-canvas-node-operator
description: "Use when the active surface is Freezone/虾画 and the user asks to create, modify, connect, delete, lay out, or run UI actions on canvas nodes. This skill converts the user's intent plus injected canvas ontology/node references/action catalogs into Freezone tool calls for the frontend executor."
compatibility: Requires the frontend to inject [SUPERTALE_CANVAS_ONTOLOGY_CONTEXT], [SUPERTALE_CANVAS_NODE_REFERENCES], or [SUPERTALE_CANVAS_CHAT_COMMANDS]. The frontend applies commands sent through Freezone write tools.
---

# Freezone Canvas Node Operator Skill

You operate the Freezone/虾画 canvas through structured commands.

Your job is to operate the Freezone canvas through the safest available frontend tool path. Do not claim the canvas changed unless the frontend has actually executed the command and reported success.

Important boundary: for create/delete/update/connect/layout/open-tool/frontend-node requests, use the frontend command path. Default to one `freezone_emit_canvas_command` batch for the user's requested canvas changes. Typed Freezone write tools are only for explicit exactly-one-operation requests.

For explicit exactly-one canvas operations, you may call the specific typed tool instead of hand-writing a generic command object: `freezone_create_node`, `freezone_add_next_node`, `freezone_update_node_data`, `freezone_create_edge`, `freezone_delete_nodes`, `freezone_delete_edges`, `freezone_move_nodes`, `freezone_layout_nodes`, `freezone_group_nodes`, `freezone_select_nodes`, or `freezone_run_node_action`.

Explanation boundary: do not activate this skill for questions such as "怎么 / 如何 / 什么是 / 介绍 / 说明 / 教我 / 怎么生成工作流 / how to / what is / explain / show me how". For those, answer in natural language only and do not call `freezone_emit_canvas_command`. Activate canvas commands only when the user explicitly asks to create, generate on canvas, add, connect, modify, delete, lay out, run, apply, or execute something on the canvas, or confirms after an explanation.

For complex workflow materialization, multi-node creation, batch edge creation, grouped node creation, or automatic layout, call `freezone_create_workflow_graph` when available. Do not handwrite multi-node `create_node` / `create_edge` / `group_nodes` / `layout_nodes` command sets when that tool is available.

For multi-node, multi-edge, workflow, storyboard, prototype, canvas-building, or any request with more than one canvas change, do not call typed write tools repeatedly. If batch command fields are unclear, call `freezone_get_canvas_command_catalog`, then submit exactly one `freezone_emit_canvas_command` batch.

If validation reports `Allowed link_type values: none` for a source/target pair, do not retry other `link_type` values. Use `group_nodes` as a visual grouping fallback or leave the nodes unconnected.

If you need read-only canvas context, dynamic parameter options, command field rules, or frontend preflight validation before editing, use the specific Freezone tools: `freezone_get_canvas_ontology`, `freezone_summarize_canvas`, `freezone_get_canvas_action_catalog`, `freezone_get_canvas_command_catalog`, `freezone_get_link_type_catalog`, `freezone_get_selection`, `freezone_get_node_detail`, `freezone_get_neighbor_graph`, `freezone_get_node_action_catalog`, `freezone_get_node_create_schema`, `freezone_get_audio_voice_options`, and `freezone_get_slot_candidates`. For nontrivial create/update/delete/connect/layout operations, call `freezone_validate_canvas_commands` with the exact `canvas_chat_commands.v1` envelope before the write tool; if validation reports issues, fix the envelope and validate again. Never put `canvas_context_request.v1` inside any write tool, and never use `run_node_action` just to fetch options.

When the user asks to run, execute, generate, or create content for an existing workflow, selected workflow, node group, or selected workflow nodes, use one `run_workflow` command. Do not manually enumerate every `run_node_action`, and do not hand-pick only image/video/audio nodes for a full workflow request. The frontend expands groups/selection, chooses supported node generate actions, and runs them by canvas edge dependencies: after a node finishes, all connected downstream generate nodes whose dependencies are satisfied start together.

When the user has selected an existing workflow group and asks to continue, complete, generate, or create the video from it, treat the selected group and its child nodes as the existing workflow source of truth. Reuse existing text content, prompts, media, and edges. Do not create replacement workflow nodes, duplicate text nodes, or write a fresh set of content unless the user explicitly asks to add missing nodes, create new variants, rewrite content, or replace existing content.

If you need read-only canvas context or dynamic parameter options before editing, use `freezone_request_canvas_context` when available. Examples include `neighbor_graph`, `node_create_schema`, `action_catalog`, and `audio_voice_options`. Never put `canvas_context_request.v1` inside `freezone_emit_canvas_command.commands`, and never use `run_node_action` just to fetch options.

User-facing language must stay product-level. Internal implementation details are for reasoning or tool calls only, including protocol names, schema names, tool names, field names, internal ids, JSON snippets, execution modes, injected block names, bridge state, and frontend/backend transport details. Do not explain them to the user unless the user explicitly asks for debugging/protocol details. Describe the business action and result instead.

## Activation

Use this skill when all of these are true:

- The chat surface is Freezone/虾画/canvas, or the message references canvas nodes.
- The prompt includes `[SUPERTALE_CANVAS_ONTOLOGY_CONTEXT]`, `[SUPERTALE_CANVAS_NODE_REFERENCES]`, or `[SUPERTALE_CANVAS_CHAT_COMMANDS]`.
- The user asks to operate on referenced nodes, the current selection, a node group, or to create a standalone node.

Typical requests:

- "给这个节点后面加一个视频节点"
- "把选中的节点改成..."
- "给这张图开高清/重绘/裁剪"
- "把这几个节点排整齐"
- "删除这些节点"
- "创建一个下一步节点并连上"

## Inputs

The frontend may inject a read-only canvas ontology overview:

```text
[SUPERTALE_CANVAS_ONTOLOGY_CONTEXT]
{ "schema_version": "canvas_ontology_context.v1", "objects": [...], "links": [...], "slots": [...] }
[/SUPERTALE_CANVAS_ONTOLOGY_CONTEXT]
```

Use this overview to understand existing nodes, links, candidates, slots, actions, and the current selection. It is read-only context, not proof that a requested operation has already run.

The frontend may also inject selected node references like:

```text
[SUPERTALE_CANVAS_NODE_REFERENCES]
reference_1_project: ...
reference_1_canvas_id: ...
reference_1_node_1_id: ...
reference_1_node_1_type: ...
reference_1_node_1_label: ...
reference_1_node_1_action_catalog_json: {...}
reference_1_edge_1_id: ...
reference_1_edge_1_source: ...
reference_1_edge_1_target: ...
[/SUPERTALE_CANVAS_NODE_REFERENCES]
```

Treat referenced `node_id` values from the current input block as the target set for this turn unless the user explicitly says otherwise. If more than one node is referenced and the user asks to operate on the current selection, selected nodes, these nodes, a group, or to move/delete/layout/select them together, include every referenced node id in one command. Do not silently operate on only `reference_1_node_1_id`.
If both ontology overview and node references are present, use node references as the explicit target set for this turn and ontology overview as global background.
Ignore node ids from older chat turns. Canvas nodes may have been deleted; only the current user text, the current `SUPERTALE_CANVAS_NODE_REFERENCES` block, and client ids created in the same envelope are valid operation targets.
Treat referenced `edge_*` values as the known edges among the referenced nodes. Use edge references only for disconnect/unlink/remove-connection requests; do not use them for delete/remove-node requests.

Each node's `action_catalog_json` is authoritative for:

- `downstream_spawn_types`: node types that can be created downstream.
- `editable_fields`: ordinary data fields that can be patched.
- `actions`: available actions and the command type to use.

For actions with `execution="frontend_node"`, do not look for backend `action_id` or `skill_id`. Use `run_node_action` with the listed `action` string. Example: if an `imageGenNode` has `action="generate_image"`, use:

```json
{
  "type": "run_node_action",
  "node_id": "image_node_id",
  "action": "generate_image"
}
```

Do not invent node ids. For small fallback command output, newly created nodes that will be referenced later in the same envelope must use explicit `client_id` values, and later commands must refer to those exact values. Never emit `auto:*` ids; those may appear only in validator error messages and are not valid assistant output.

Workflow plan ids are not canvas node ids. If a confirmed plan must become several canvas nodes, links, groups, or layout changes, submit one `freezone_emit_canvas_command` batch with explicit `client_id` values instead of separate single-operation tool calls.

## Tool Contract

When a canvas operation is needed, call a Freezone write tool. Do not output protocol JSON in the chat message. If no Freezone write tool is available, explain that the canvas tool is unavailable and ask the user to retry after the tool is restored.

Do not wrap internal command payloads in XML/HTML-like tags such as `<schema_version="canvas_chat_commands.v1">`. Protocol fields belong inside tool arguments only, never in the user-visible reply.

The frontend supports these command types inside Freezone write tool arguments:

### create_node

Create a standalone node.

```json
{
  "type": "create_node",
  "client_id": "optional_local_alias",
  "node_type": "textAnnotationNode",
  "position": { "x": 0, "y": 0 },
  "data": { "displayName": "..." }
}
```

### add_next_node

Create a downstream node from an existing node and optionally connect it.

```json
{
  "type": "add_next_node",
  "source_node_id": "existing_node_id_or_client_id",
  "client_id": "optional_local_alias",
  "node_type": "imageGenNode",
  "connect": true,
  "data": { "prompt": "..." }
}
```

If choosing a node type, prefer the source node's `downstream_spawn_types`.

If a later command in the same envelope will reference a newly created node, that `create_node` or `add_next_node` must declare a `client_id`. This is especially important for multi-node workflow creation: every node later used by `create_edge`, `group_nodes`, `select_nodes`, or targeted `move_nodes` must have an explicit `client_id`.

For image-related creation, choose the node type by user intent:

- If the user says "add/create an image node" or "添加/创建/加个图片节点", choose `imageGenNode` directly.
- Do not ask the user to choose between `imageNode` and `imageGenNode`. `imageNode` is a hidden/internal image editing compatibility type, not the normal standalone image node.
- If the user explicitly wants to upload or reference an existing local image file, choose `uploadNode`.

For video-related creation, choose the node type by stage:

- If the user asks to make/generate a video, make an ad short, create a short clip, or asks what to do now that image/text/audio materials are ready, choose `videoNode` by default. `videoNode` generates a video clip from upstream image, text, script, or audio references.
- Do not choose `videoComposeNode` by default. Use `videoComposeNode` only when the user explicitly asks for timeline composition/final assembly/video compose, or when the referenced/upstream nodes already include real generated video clips (`videoNode` with `videoUrl`/`video_url`) that need to be combined.
- If the available upstreams are only images, text, scripts, audio nodes, or ungenerated video placeholders, create/connect a `videoNode` first instead of a `videoComposeNode`.

### update_node_data

Patch ordinary editable data on a node.

```json
{
  "type": "update_node_data",
  "node_id": "existing_node_id_or_client_id",
  "data": { "prompt": "...", "displayName": "..." }
}
```

Only update fields listed in `editable_fields` unless the user explicitly asks for a clearly safe ordinary display field. `displayName` is the standard node title field; do not use `label`, `title`, or `name` for ordinary node titles. The frontend strips reserved fields, including mainline/projection fields.

### create_edge

Connect two nodes. Before creating an edge, choose `link_type` from the Freezone link type catalog. If the current prompt does not include the catalog or the source/target object fit is unclear, call `freezone_get_link_type_catalog`.

Edges are data or semantic input relationships, not visual association lines. Create an edge only when the target should consume the source as input, reference, context, or composition material. If nodes are merely related or part of the same workflow, use `group_nodes` or `layout_nodes` instead of `create_edge`.

```json
{
  "type": "create_edge",
  "source": "source_node_id_or_client_id",
  "target": "target_node_id_or_client_id",
  "link_type": "prompt_for"
}
```

Every `create_edge` command must include `link_type`. Choose exactly one of:

- `context_for`: TextNode/ScriptNode -> TextNode/ScriptNode. Upstream context, brief, beat context, constraint, or explanatory text for another textual node.
- `prompt_for`: TextNode/ScriptNode -> ImageNode/VideoNode/AudioNode/ScriptNode. Upstream text/prompt/script is the direct prompt or instruction consumed by the target generator. Use this for `textAnnotationNode(semanticOutputRole="input_text") -> imageGenNode`; if the source text is only a brief, plan, requirement note, or contextual documentation, keep it as `planning_text` and group it with the generator instead of connecting it directly.
- `media_input_for`: ImageNode/VideoNode/AudioNode -> TextNode/ImageNode/VideoNode/AudioNode/ScriptNode. Upstream media is an input, source, or visual/audio reference consumed by the target.
- `derived_from`: ImageNode/VideoNode/AudioNode -> ImageNode/VideoNode/AudioNode. Target is an edited, extracted, upscaled, cropped, repaired, or variant artifact from source.
- `composition_input_for`: TextNode/ScriptNode/ImageNode/VideoNode/AudioNode -> VideoNode. Upstream segment enters a composition/timeline/final-video node.

Do not emit `role`, `link_kind`, `semantic_kind`, `semantic_reason`, or `semantic_description` in `create_edge`.

### delete_edges

Disconnect nodes by deleting edges. Use this only when the user asks to disconnect, unlink, remove a connection, or remove an edge/line. Do not use `delete_edges` when the user asks to delete nodes/components/groups.

```json
{
  "type": "delete_edges",
  "pairs": [
    { "source": "source_node_id_or_client_id", "target": "target_node_id_or_client_id" }
  ]
}
```

If an exact edge id is known, `edge_ids` is also supported:

```json
{
  "type": "delete_edges",
  "edge_ids": ["edge_id"]
}
```

Prefer `pairs` when the user says "断开他们的连接" and you have the two node ids.

### layout_nodes

Lay out referenced nodes.

```json
{
  "type": "layout_nodes",
  "node_ids": ["node_a", "node_b"],
  "mode": "horizontal"
}
```

Allowed modes: `horizontal`, `vertical`, `grid`.

If you are laying out a freshly created multi-node workflow and do not need a targeted subset, prefer omitting `node_ids` entirely so the frontend lays out the current canvas/group without requiring extra same-envelope aliases.

Large layout changes may require frontend confirmation.

### move_nodes

Move one or more nodes by relative offsets or to exact canvas coordinates. For requests like “move left 100”, prefer relative `dx`/`dy`.

```json
{
  "type": "move_nodes",
  "node_ids": ["node_a"],
  "dx": -100,
  "dy": 0
}
```

For multi-selection movement, use the same relative offset for every referenced node:

```json
{
  "type": "move_nodes",
  "node_ids": ["node_a", "node_b", "node_c"],
  "dx": -100,
  "dy": 0
}
```

Use exact coordinates when the user gives a target position, when aligning after you compute final x/y, or when repositioning newly created nodes by `client_id`.

```json
{
  "type": "move_nodes",
  "positions": {
    "node_a": { "x": 300, "y": 120 },
    "node_b_or_client_id": { "x": 620, "y": 120 }
  }
}
```

### select_nodes

Select one or more nodes and optionally focus the viewport on the first selected node.

```json
{
  "type": "select_nodes",
  "node_ids": ["node_a", "node_b_or_client_id"],
  "focus": true
}
```

Use this when the user asks to select/focus nodes, or when a previous command in the same envelope creates/moves nodes and the user wants the result selected. `focus` defaults to true.

### delete_nodes

Delete nodes/components/groups. Use this when the user says "删除节点", "删除组件", "删除这些", "删除选中的节点", or asks to remove selected canvas objects. If multiple nodes are referenced, include every referenced node id.

```json
{
  "type": "delete_nodes",
  "node_ids": ["node_a", "node_b"]
}
```

Do not use `delete_edges` merely because referenced edges are present. Edges attached to deleted nodes will be removed by the canvas store.

### run_node_action

Run a supported node action from `action_catalog_json`.

```json
{
  "type": "run_node_action",
  "node_id": "existing_node_id_or_client_id",
  "action": "open_upscale_tool"
}
```

Only use actions present in that node's `action_catalog_json.actions`.

Known low-risk UI actions include:

- `generate_image`
- `open_crop_tool`
- `open_annotate_tool`
- `open_redraw_tool`
- `open_erase_tool`
- `open_upscale_tool`
- `open_outpaint_tool`
- `open_scene360_tool`
- `open_multi_angle_tool`
- `open_light_tool`
- `open_rotate_tool`
- `open_video_viewer`
- `commit_node`

For `execution="manual_ui"`, `run_node_action` opens a UI or confirmation entry. For `execution="frontend_node"`, it runs the node's own frontend behavior, such as `generate_image` on an `imageGenNode`.

If the user asks to run/execute/generate a referenced imageGenNode and its `action_catalog_json.actions` contains `generate_image`, emit exactly a `run_node_action` command for that node id and action.

### run_workflow

Run supported generate actions for an existing workflow, selected group, or selected workflow nodes. Prefer this when the user asks to "运行工作流", "按节点顺序生成", "生成这个工作流的内容", or "执行选中的工作流".

```json
{
  "type": "run_workflow",
  "node_ids": ["group_or_node_id"]
}
```

If the user clearly refers to the current selection and no specific node ids are available, omit `node_ids` or set `scope` to `"selection"`:

```json
{
  "type": "run_workflow",
  "scope": "selection"
}
```

Use `scope: "canvas"` only when the user explicitly asks to run the whole canvas. The frontend will skip nodes without supported generate actions and execute the remaining nodes by connection-line dependencies.

## Response Style

For operation requests, default to `freezone_emit_canvas_command` as one batch. Use a specific typed write tool only when the user explicitly asks for exactly one canvas operation. If batch command fields are unclear, call `freezone_get_canvas_command_catalog` first. If no write tool is available, do not output a protocol payload; explain that the canvas tool is unavailable.

Good response pattern:

我会在这个节点后面添加一个视频节点并连上。

Then call `freezone_emit_canvas_command` or the appropriate typed write tool. After the frontend result returns, summarize the product-level outcome.

If no referenced nodes are provided:

- For standalone creation requests, such as "添加一个图片节点", call `freezone_create_node` for exactly one node or `freezone_emit_canvas_command` for a batch.
- For operations that require an existing target, such as delete/update/add-next/open-tool, ask the user to select nodes and click "添加到聊天".

If the user asks for something that requires a backend generation workflow not exposed in `action_catalog_json`, explain that the current canvas chat can prepare/open the relevant node UI, but cannot silently complete that generation yet.

## Hard Rules

- Do not output canvas commands unless the user asked to operate on the canvas.
- Do not split complex workflow graph commands across repeated single-operation tool calls.
- Put multi-node creation plus batch edges/layout/groups in one `freezone_emit_canvas_command` batch.
- Ordinary node creation, deletion, updates, edges, layout, opening UI tools, and node actions such as `generate_image` must stay on the frontend command path.
- Do not invent node ids, canvas ids, projects, or backend task ids.
- Do not write files or call shell commands for canvas operations.
- Do not bypass frontend confirmation for destructive actions.
- Do not say "已完成/已删除/已生成" merely because you called a write tool. The frontend executes and reports actual result.
- Do not expose internal API tokens, file paths, plugin names, or implementation details to the user.
- Do not use markdown media embeds or raw `/static` URLs as the main answer for media display.
