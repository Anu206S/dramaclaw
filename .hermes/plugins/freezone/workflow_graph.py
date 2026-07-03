"""Build frontend canvas commands from Freezone workflow graph plans."""

from __future__ import annotations

import re
from typing import Any

from freezone_workflows import registered_workflows, workflow_aliases, workflow_by_type

CANVAS_CHAT_COMMANDS_SCHEMA_VERSION = "canvas_chat_commands.v1"

ALLOWED_NODE_TYPES = {
    "textAnnotationNode",
    "scriptNode",
    "beatContextNode",
    "imageGenNode",
    "videoNode",
    "audioNode",
    "videoComposeNode",
}

DEFAULT_NODE_TYPE = "textAnnotationNode"

TEXTUAL_NODE_TYPES = {"textAnnotationNode", "scriptNode", "beatContextNode"}

LINK_TYPE_VALUES = {
    "context_for",
    "prompt_for",
    "media_input_for",
    "derived_from",
    "composition_input_for",
}

LINK_OBJECT_TYPE_BY_NODE_TYPE = {
    "textAnnotationNode": "TextNode",
    "scriptNode": "ScriptNode",
    "beatContextNode": "TextNode",
    "imageGenNode": "ImageNode",
    "videoNode": "VideoNode",
    "audioNode": "AudioNode",
    "videoComposeNode": "VideoNode",
}

LINK_TYPE_RULES = {
    "context_for": ({"TextNode", "ScriptNode"}, {"TextNode", "ScriptNode"}),
    "prompt_for": (
        {"TextNode", "ScriptNode"},
        {"ImageNode", "VideoNode", "AudioNode", "ScriptNode"},
    ),
    "media_input_for": (
        {"ImageNode", "VideoNode", "AudioNode"},
        {"TextNode", "ImageNode", "VideoNode", "AudioNode", "ScriptNode"},
    ),
    "derived_from": (
        {"ImageNode", "VideoNode", "AudioNode"},
        {"ImageNode", "VideoNode", "AudioNode"},
    ),
    "composition_input_for": (
        {"TextNode", "ScriptNode", "ImageNode", "VideoNode", "AudioNode"},
        {"VideoNode"},
    ),
}

STAGE_ORDER = {
    "input": 0,
    "resource": 0,
    "story": 1,
    "analysis": 1,
    "character": 2,
    "scene": 2,
    "asset": 3,
    "beat": 3,
    "shot": 4,
    "frame": 4,
    "image": 4,
    "video": 5,
    "audio": 5,
    "compose": 6,
    "quality": 7,
    "review": 7,
}

REGISTERED_WORKFLOWS = registered_workflows()
WORKFLOW_ALIASES = workflow_aliases()
WORKFLOW_BY_TYPE = workflow_by_type()


def build_workflow_plan(args: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic Freezone workflow plan from a workflow type."""
    workflow_types = _workflow_type_values(args)
    if len(workflow_types) > 1:
        return _multi_workflow_plan(args, workflow_types)
    workflow_type = _normalize_workflow_type(
        workflow_types[0]
        if workflow_types
        else (
            args.get("workflow_type")
            or args.get("workflowType")
            or args.get("type")
            or "short_drama"
        )
    )
    if workflow_type == "short_drama":
        return _short_drama_plan(args)
    if workflow_type == "ad_video":
        return _ad_video_plan(args)
    workflow = WORKFLOW_BY_TYPE.get(workflow_type)
    if workflow is not None:
        template_kind = workflow.get("template_kind")
        template = _workflow_template_kwargs(workflow)
        if template_kind == "simple":
            return _simple_workflow_plan(workflow_type=workflow_type, **template)
        if template_kind == "linear":
            return _linear_media_plan(workflow_type=workflow_type, **template)
    return {
        "ok": False,
        "status": "unsupported_workflow_type",
        "error": f"unsupported workflow_type: {workflow_type}",
    }


def build_workflow_graph_commands(args: dict[str, Any]) -> dict[str, Any]:
    """Convert a workflow plan/graph payload into canvas_chat_commands.v1 commands.

    The assistant-facing workflow plan uses logical ids. This builder turns those
    ids into same-envelope ``client_id`` aliases and only emits valid canvas
    command refs. It never emits ``auto:*`` ids.
    """
    payload = _workflow_payload(args)
    if not isinstance(payload.get("nodes"), list) or not payload.get("nodes"):
        workflow_types = _workflow_type_values(args)
        if (
            len(workflow_types) > 1
            or args.get("workflow_type")
            or args.get("workflowType")
            or args.get("type")
        ):
            planned = build_workflow_plan(args)
            if not planned.get("ok"):
                return {
                    "ok": False,
                    "status": planned.get("status") or "workflow_plan_failed",
                    "error": planned.get("error") or "failed to build workflow plan",
                    "commands": [],
                    "skipped_edges": [],
                    "warnings": [],
                }
            payload = planned
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return {
            "ok": False,
            "status": "empty_nodes",
            "error": "workflow graph requires a non-empty nodes array",
            "commands": [],
            "skipped_edges": [],
            "warnings": [],
        }

    warnings: list[str] = []
    skipped_edges: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    node_by_plan_id: dict[str, dict[str, Any]] = {}
    used_client_ids: set[str] = set()

    normalized_nodes = []
    for index, raw_node in enumerate(raw_nodes):
        if not isinstance(raw_node, dict):
            warnings.append(f"nodes[{index}] ignored because it is not an object")
            continue
        plan_id = _node_plan_id(raw_node, index)
        node_type = _node_type(raw_node)
        if node_type not in ALLOWED_NODE_TYPES:
            warnings.append(
                f"nodes[{index}] uses unsupported node_type {node_type!r}; "
                f"falling back to {DEFAULT_NODE_TYPE}"
            )
            node_type = DEFAULT_NODE_TYPE
        client_id = _unique_client_id(plan_id, used_client_ids)
        used_client_ids.add(client_id)
        node = {
            "plan_id": plan_id,
            "client_id": client_id,
            "node_type": node_type,
            "raw": raw_node,
            "stage_index": _stage_index(raw_node, node_type),
        }
        node_by_plan_id[plan_id] = node
        node_by_plan_id[client_id] = node
        normalized_nodes.append(node)

    if not normalized_nodes:
        return {
            "ok": False,
            "status": "empty_nodes",
            "error": "workflow graph did not contain any valid node objects",
            "commands": [],
            "skipped_edges": skipped_edges,
            "warnings": warnings,
        }

    edge_records: list[dict[str, Any]] = []
    prompt_source_plan_ids: set[str] = set()
    audio_prompt_target_plan_ids: set[str] = set()
    for edge_index, edge in enumerate(_edge_pairs(payload.get("edges"))):
        source_ref, target_ref, requested_link_type = edge
        source = node_by_plan_id.get(source_ref)
        target = node_by_plan_id.get(target_ref)
        if source is None or target is None:
            skipped_edges.append(
                {
                    "index": edge_index,
                    "source": source_ref,
                    "target": target_ref,
                    "reason": "source or target plan node not found",
                }
            )
            continue
        if source["client_id"] == target["client_id"]:
            skipped_edges.append(
                {
                    "index": edge_index,
                    "source": source_ref,
                    "target": target_ref,
                    "reason": "self edges are not allowed",
                }
            )
            continue
        link_type = _infer_link_type(source["node_type"], target["node_type"], requested_link_type)
        if link_type is None:
            skipped_edges.append(
                {
                    "index": edge_index,
                    "source": source_ref,
                    "target": target_ref,
                    "reason": f"{source['node_type']} cannot directly connect to {target['node_type']}",
                }
            )
            continue
        if link_type == "context_for" and target["node_type"] == "beatContextNode":
            skipped_edges.append(
                {
                    "index": edge_index,
                    "source": source_ref,
                    "target": target_ref,
                    "reason": "beatContextNode is used as a prompt/context source, not a semantic edge target",
                }
            )
            continue
        record = {
            "index": edge_index,
            "source_ref": source_ref,
            "target_ref": target_ref,
            "source": source,
            "target": target,
            "link_type": link_type,
        }
        edge_records.append(record)
        if link_type == "prompt_for" and source["node_type"] in TEXTUAL_NODE_TYPES:
            prompt_source_plan_ids.add(source["plan_id"])
        if (
            link_type == "prompt_for"
            and source["node_type"] in TEXTUAL_NODE_TYPES
            and target["node_type"] == "audioNode"
        ):
            audio_prompt_target_plan_ids.add(target["plan_id"])

    for order, node in enumerate(normalized_nodes):
        raw_node = node["raw"]
        data = _node_data(
            raw_node,
            node["node_type"],
            audio_uses_upstream_text=node["plan_id"] in audio_prompt_target_plan_ids,
        )
        if node["plan_id"] in prompt_source_plan_ids and node["node_type"] in TEXTUAL_NODE_TYPES:
            data.setdefault("semanticOutputRole", "input_text")
        command = {
            "type": "create_node",
            "client_id": node["client_id"],
            "node_type": node["node_type"],
            "position": _node_position(raw_node, node["stage_index"], order),
            "data": data,
        }
        commands.append(command)

    for record in edge_records:
        source = record["source"]
        target = record["target"]
        link_type = record["link_type"]
        if link_type == "context_for" and source["plan_id"] in prompt_source_plan_ids:
            skipped_edges.append(
                {
                    "index": record["index"],
                    "source": record["source_ref"],
                    "target": record["target_ref"],
                    "reason": (
                        "source node is marked as input_text for prompt_for edges; "
                        "skipping context_for to avoid conflicting text output roles"
                    ),
                }
            )
            continue
        command = {
            "type": "create_edge",
            "source": source["client_id"],
            "target": target["client_id"],
            "link_type": link_type,
        }
        commands.append(command)

    groups = _groups(payload.get("groups"), payload.get("layout"))
    group_client_node_ids: list[list[str]] = []
    if groups:
        for group in groups:
            node_ids = [
                node_by_plan_id[item]["client_id"]
                for item in group["node_ids"]
                if item in node_by_plan_id
            ]
            if len(node_ids) >= 2:
                group_client_node_ids.append(_dedupe(node_ids))
                commands.append(
                    {
                        "type": "group_nodes",
                        "node_ids": group_client_node_ids[-1],
                        "label": group.get("label") or "工作流",
                    }
                )
    elif len(normalized_nodes) >= 2:
        commands.append(
            {
                "type": "group_nodes",
                "node_ids": [node["client_id"] for node in normalized_nodes],
                "label": str(payload.get("workflow_type") or payload.get("title") or "工作流"),
            }
        )

    layout_targets = group_client_node_ids or [[node["client_id"] for node in normalized_nodes]]
    for node_ids in layout_targets:
        commands.append(
            {
                "type": "layout_nodes",
                "node_ids": node_ids,
                "mode": "horizontal",
            }
        )
    commands.append(
        {
            "type": "select_nodes",
            "node_ids": [node["client_id"] for node in normalized_nodes],
            "focus": True,
        }
    )

    return {
        "ok": True,
        "status": "workflow_graph_commands_created",
        "schema_version": CANVAS_CHAT_COMMANDS_SCHEMA_VERSION,
        "commands": commands,
        "skipped_edges": skipped_edges,
        "warnings": warnings,
    }


def _workflow_payload(args: dict[str, Any]) -> dict[str, Any]:
    for key in ("plan", "workflow", "graph", "body"):
        value = args.get(key)
        if isinstance(value, dict):
            return value
    return args


def _workflow_type_values(args: dict[str, Any]) -> list[str]:
    raw = (
        args.get("workflow_types")
        or args.get("workflowTypes")
        or args.get("types")
        or args.get("workflow_type")
        or args.get("workflowType")
        or args.get("type")
    )
    values: list[Any]
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str) and "," in raw:
        values = raw.split(",")
    elif raw is None:
        values = []
    else:
        values = [raw]
    normalized: list[str] = []
    for value in values:
        workflow_type = _normalize_workflow_type(value)
        if workflow_type and workflow_type not in normalized:
            normalized.append(workflow_type)
    return normalized


def _normalize_workflow_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return WORKFLOW_ALIASES.get(text, text or "short_drama")


def _workflow_template_kwargs(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": workflow["title"],
        "nodes": workflow["nodes"],
        "edges": workflow["edges"],
    }


def _multi_workflow_plan(args: dict[str, Any], workflow_types: list[str]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    groups: list[dict[str, Any]] = []
    summaries: list[str] = []
    row_gap = 1250

    for workflow_index, workflow_type in enumerate(workflow_types):
        child_args = dict(args)
        child_args.pop("workflow_types", None)
        child_args.pop("workflowTypes", None)
        child_args.pop("types", None)
        child_args["workflow_type"] = workflow_type
        child_plan = build_workflow_plan(child_args)
        if not child_plan.get("ok"):
            return child_plan
        prefix = _safe_client_id(workflow_type)
        id_map: dict[str, str] = {}
        for node_index, node in enumerate(child_plan.get("nodes") or []):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or f"node_{node_index + 1}").strip()
            prefixed_id = f"{prefix}_{node_id}"
            id_map[node_id] = prefixed_id
            next_node = dict(node)
            next_node["id"] = prefixed_id
            stage_index = _stage_index(next_node, _node_type(next_node))
            next_node.setdefault(
                "position",
                {
                    "x": 80 + stage_index * 340,
                    "y": 80 + workflow_index * row_gap + (node_index % 4) * 220,
                },
            )
            nodes.append(next_node)
        for edge in child_plan.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            source = id_map.get(str(edge.get("source") or ""))
            target = id_map.get(str(edge.get("target") or ""))
            if not source or not target:
                continue
            next_edge = dict(edge)
            next_edge["source"] = source
            next_edge["target"] = target
            edges.append(next_edge)
        child_layout = (
            child_plan.get("layout") if isinstance(child_plan.get("layout"), dict) else {}
        )
        for group in _groups(child_plan.get("groups"), child_layout):
            node_ids = [id_map[item] for item in group["node_ids"] if item in id_map]
            if len(node_ids) >= 2:
                groups.append(
                    {
                        "label": group.get("label") or child_plan.get("title") or "工作流",
                        "node_ids": node_ids,
                    }
                )
        summary = child_plan.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(summary.strip())

    title = str(args.get("title") or args.get("name") or "批量工作流").strip() or "批量工作流"
    return _plan(
        workflow_type="multi_workflow",
        title=title,
        summary="；".join(summaries) or "批量创建多个虾画节点工作流。",
        nodes=nodes,
        edges=edges,
        groups=groups,
    )


def _short_drama_plan(args: dict[str, Any]) -> dict[str, Any]:
    beat_count = _positive_int(args.get("beat_count") or args.get("beats"), default=1, maximum=6)
    title = str(args.get("title") or args.get("name") or "短剧 / 小说转视频工作流")
    nodes: list[dict[str, Any]] = [
        _plan_node(
            "script_input",
            "textAnnotationNode",
            "剧本/故事输入",
            "承载用户上传的剧本、小说片段、故事梗概或创意 brief。",
            "input",
        ),
        _plan_node(
            "story_outline",
            "textAnnotationNode",
            "故事摘要与主线",
            "提炼世界观、主线冲突、情绪基调和爽点/反转。",
            "story",
        ),
        _plan_node(
            "character_profile",
            "textAnnotationNode",
            "角色设定",
            "整理主角、反派、关键配角、关系和动机。",
            "character",
        ),
        _plan_node(
            "scene_plan",
            "textAnnotationNode",
            "场景规划",
            "整理高频场景、临时地点、道具和视觉风格要求。",
            "scene",
        ),
        _plan_node(
            "beat_plan",
            "scriptNode",
            "分集 / Beat 表",
            "按 episode、act 或 beat group 拆分可生产单元。",
            "beat",
        ),
    ]
    edges: list[dict[str, str]] = [
        _edge("script_input", "story_outline"),
        _edge("script_input", "character_profile"),
        _edge("script_input", "scene_plan"),
        _edge("story_outline", "beat_plan"),
    ]
    beat_node_ids: list[str] = []
    for index in range(1, beat_count + 1):
        beat_id = f"beat_{index}"
        frame_id = f"frame_beat_{index}"
        video_id = f"video_beat_{index}"
        audio_text_id = f"audio_text_beat_{index}"
        audio_id = f"audio_beat_{index}"
        beat_node_ids.extend([beat_id, frame_id, video_id, audio_text_id, audio_id])
        nodes.extend(
            [
                _plan_node(
                    beat_id,
                    "beatContextNode",
                    f"Beat {index} 镜头上下文",
                    "保存本 beat 的剧情目标、画面描述、角色、场景和镜头要求。",
                    "beat",
                ),
                _plan_node(
                    frame_id,
                    "imageGenNode",
                    f"Beat {index} 首帧 / 分镜图",
                    "根据 beat、角色和场景生成首帧或分镜图。",
                    "frame",
                ),
                _plan_node(
                    video_id,
                    "videoNode",
                    f"Beat {index} 视频片段",
                    "基于首帧/分镜图和镜头描述生成视频片段。",
                    "video",
                ),
                _plan_node(
                    audio_text_id,
                    "textAnnotationNode",
                    f"Beat {index} 配音文本",
                    "本 beat 的旁白、对白或解说词，用作下游文本生成音频输入。",
                    "audio",
                ),
                _plan_node(
                    audio_id,
                    "audioNode",
                    f"Beat {index} 配音 / 音效",
                    "由上游配音文本生成音频。",
                    "audio",
                ),
            ]
        )
        edges.extend(
            [
                _edge("beat_plan", beat_id),
                _edge("character_profile", frame_id),
                _edge("scene_plan", frame_id),
                _edge(beat_id, frame_id),
                _edge(frame_id, video_id),
                _edge(beat_id, video_id),
                _edge("story_outline", audio_text_id),
                _edge(audio_text_id, audio_id),
            ]
        )
    nodes.extend(
        [
            _plan_node(
                "compose_preview",
                "videoComposeNode",
                "成片合成 / 预览",
                "合成视频片段、配音、字幕和音乐，形成预览成片。",
                "compose",
            ),
        ]
    )
    for index in range(1, beat_count + 1):
        edges.extend(
            [
                _edge(f"video_beat_{index}", "compose_preview"),
                _edge(f"audio_beat_{index}", "compose_preview"),
            ]
        )
    groups = [
        {
            "label": title,
            "node_ids": [
                "script_input",
                "story_outline",
                "character_profile",
                "scene_plan",
                "beat_plan",
                *beat_node_ids,
                "compose_preview",
            ],
        }
    ]
    return _plan(
        workflow_type="short_drama",
        title=title,
        summary="从剧本/故事输入到首帧、视频片段、音频和成片合成的虾画节点工作流。",
        nodes=nodes,
        edges=edges,
        groups=groups,
    )


def _ad_video_plan(args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or args.get("name") or "广告视频工作流").strip()
    goal = _workflow_goal_text(args, fallback=title)
    product_input = (
        f"用户目标：{goal}\n"
        "产品/素材：整理用户提供的商品、图片、卖点、价格/优惠、投放平台和参考素材。\n"
        "目标受众：如用户未指定，需要在后续沟通中补充年龄、购买场景和核心痛点。\n"
        "本节点是后续 Hook、脚本、图片、视频和音频节点的事实来源。"
    )
    hook_options = (
        f"基于用户目标“{goal}”提炼广告 Hook、核心卖点和 CTA。\n"
        "Hook 方向：开头 1-3 秒必须直接抓住注意力，突出产品最强利益点。\n"
        "卖点方向：把产品特征转成用户收益，优先写新鲜感、品质感、便利性、优惠和信任背书。\n"
        "CTA 方向：引导点击、下单、领取优惠或立即购买。"
    )
    ad_script = (
        f"围绕“{goal}”撰写广告脚本。\n"
        "结构：开场 Hook -> 产品/场景展示 -> 核心卖点证明 -> 优惠/信任背书 -> CTA。\n"
        "内容要求：包含口播文案、字幕重点和关键镜头说明；后续图片、视频、音频节点应复用这里的脚本事实。"
    )
    visual_prompt = (
        f"为“{goal}”生成广告关键画面。画面需要突出产品主体、购买欲、清晰构图、适合电商短视频投放。"
    )
    video_prompt = f"为“{goal}”生成广告视频片段。视频需要按广告脚本呈现产品特写、场景使用、卖点强化和 CTA 情绪。"
    audio_prompt = f"为“{goal}”生成广告口播或背景音乐，语气清晰、有转化感，配合广告脚本。"
    voiceover_text = (
        f"正在寻找更省心的选择？这一次，我们为你准备了“{goal}”。\n"
        "从第一眼的质感，到入口后的真实体验，每一个细节都为日常使用而来。\n"
        "新鲜、可靠、方便，不用反复比较，也不用担心踩坑。\n"
        "现在下单，把这份刚刚好的选择带回家。"
    )
    return _linear_media_plan(
        workflow_type="ad_video",
        title="广告视频工作流",
        nodes=[
            ("product_input", "textAnnotationNode", "产品/素材输入", product_input, "input"),
            ("hook_options", "textAnnotationNode", "Hook 与卖点", hook_options, "story"),
            ("ad_script", "textAnnotationNode", "广告脚本", ad_script, "script"),
            ("visual_frame", "imageGenNode", "广告关键画面", visual_prompt, "image"),
            ("ad_video", "videoNode", "广告视频片段", video_prompt, "video"),
            ("voiceover_text", "textAnnotationNode", "口播文案", voiceover_text, "audio"),
            ("voiceover", "audioNode", "口播/音乐", audio_prompt, "audio"),
            ("compose", "videoComposeNode", "成片合成", "合成视频、口播、字幕和音乐。", "compose"),
        ],
        edges=[
            ("product_input", "hook_options"),
            ("hook_options", "ad_script"),
            ("ad_script", "visual_frame"),
            ("visual_frame", "ad_video"),
            ("ad_script", "voiceover_text"),
            ("voiceover_text", "voiceover"),
            ("ad_video", "compose"),
            ("voiceover", "compose"),
        ],
    )


def _workflow_goal_text(args: dict[str, Any], *, fallback: str) -> str:
    fields = (
        "user_goal",
        "userGoal",
        "goal",
        "brief",
        "product_brief",
        "productBrief",
        "product",
        "description",
        "title",
        "name",
    )
    for field in fields:
        value = args.get(field)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value.strip())
    return fallback


def _linear_media_plan(
    *,
    workflow_type: str,
    title: str,
    nodes: list[tuple[str, str, str, str, str]],
    edges: list[tuple[str, str]],
) -> dict[str, Any]:
    return _plan(
        workflow_type=workflow_type,
        title=title,
        summary=f"{title}的虾画节点工作流。",
        nodes=[_plan_node(*node) for node in nodes],
        edges=[_edge(source, target) for source, target in edges],
        groups=[{"label": title, "node_ids": [node[0] for node in nodes]}],
    )


def _simple_workflow_plan(
    *,
    workflow_type: str,
    title: str,
    nodes: list[tuple[str, str, str, str, str]],
    edges: list[tuple[str, str]],
) -> dict[str, Any]:
    return _plan(
        workflow_type=workflow_type,
        title=title,
        summary=f"{title}，按顺序连接节点。",
        nodes=[_plan_node(*node) for node in nodes],
        edges=[_edge(source, target) for source, target in edges],
        groups=[{"label": title, "node_ids": [node[0] for node in nodes]}],
    )


def _plan(
    *,
    workflow_type: str,
    title: str,
    summary: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": "freezone_workflow_plan.v1",
        "workflow_type": workflow_type,
        "mode": "analysis_only",
        "summary": summary,
        "source_context": {"user_goal": title, "canvas_context": [], "input_assets": []},
        "analysis": {"entities": [], "production_units": [], "risks": []},
        "phases": [group["label"] for group in groups],
        "assumptions": ["节点创建和生成执行需等待用户确认。"],
        "missing_inputs": [],
        "expansion_rules": {},
        "nodes": nodes,
        "edges": edges,
        "layout": {"direction": "left_to_right", "groups": groups},
        "execution_policy": {
            "requires_user_confirmation": True,
            "auto_create_nodes": False,
            "auto_generate_content": False,
            "handoff_tool": "freezone_create_workflow_graph",
        },
    }


def _plan_node(
    node_id: str,
    node_type: str,
    label: str,
    description: str,
    stage: str,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "node_type": node_type,
        "label": label,
        "description": description,
        "stage": stage,
    }


def _edge(source: str, target: str) -> dict[str, str]:
    return {"source": source, "target": target}


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def _node_plan_id(node: dict[str, Any], index: int) -> str:
    for key in ("id", "client_id", "clientId", "node_id", "nodeId"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    label = node.get("label") or node.get("title") or node.get("name") or f"node_{index + 1}"
    return str(label)


def _node_type(node: dict[str, Any]) -> str:
    for key in ("node_type", "nodeType", "type"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return DEFAULT_NODE_TYPE


def _unique_client_id(raw: str, used: set[str]) -> str:
    base = _safe_client_id(raw)
    if not base or re.fullmatch(r"auto:\d+", base, flags=re.IGNORECASE):
        base = "workflow_node"
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def _safe_client_id(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(value).strip())
    text = re.sub(r"_+", "_", text).strip("_-")
    return text[:64] or "workflow_node"


def _stage_index(node: dict[str, Any], node_type: str) -> int:
    text = " ".join(
        str(node.get(key) or "")
        for key in ("stage", "phase", "group", "role", "id", "label", "title", "description")
    ).lower()
    for key, order in STAGE_ORDER.items():
        if key in text:
            return order
    return {
        "textAnnotationNode": 0,
        "scriptNode": 1,
        "beatContextNode": 3,
        "imageGenNode": 4,
        "videoNode": 5,
        "audioNode": 5,
        "videoComposeNode": 6,
    }.get(node_type, 0)


def _node_position(node: dict[str, Any], stage_index: int, order: int) -> dict[str, int]:
    position = node.get("position")
    if isinstance(position, dict):
        x = _number(position.get("x"))
        y = _number(position.get("y"))
        if x is not None and y is not None:
            return {"x": int(x), "y": int(y)}
    row = order % 4
    return {"x": 80 + stage_index * 340, "y": 80 + row * 220}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _node_data(
    node: dict[str, Any],
    node_type: str,
    *,
    audio_uses_upstream_text: bool = False,
) -> dict[str, Any]:
    data = node.get("data")
    result = dict(data) if isinstance(data, dict) else {}
    label = node.get("label") or node.get("title") or node.get("name")
    description = node.get("description") or node.get("responsibility") or node.get("purpose")
    if isinstance(label, str) and label.strip():
        result.setdefault("displayName", label.strip())
        result.setdefault("title", label.strip())
    if isinstance(description, str) and description.strip():
        result.setdefault("content", description.strip())
        result.setdefault("prompt", description.strip())
        result.setdefault("description", description.strip())
    if node_type == "audioNode":
        result.setdefault("audioKind", "speech")
        result.setdefault("audioUrl", None)
        result.setdefault("sourceFileName", None)
        result.setdefault("durationMs", None)
        result.setdefault("isUploading", False)
        text = result.get("text")
        if not audio_uses_upstream_text and (not isinstance(text, str) or not text.strip()):
            for key in ("content", "prompt", "description"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    result["text"] = value.strip()
                    break
        result.setdefault("emotionPrompt", "")
        result.setdefault("voiceLanguage", "")
        result.setdefault("isGenerating", False)
        result.setdefault("generationStartedAt", None)
    return result


def _edge_pairs(raw_edges: Any) -> list[tuple[str, str, str | None]]:
    result: list[tuple[str, str, str | None]] = []
    if not isinstance(raw_edges, list):
        return result
    for raw in raw_edges:
        source: Any = None
        target: Any = None
        requested_link_type: str | None = None
        if isinstance(raw, dict):
            source = (
                raw.get("source") or raw.get("from") or raw.get("source_id") or raw.get("sourceId")
            )
            target = (
                raw.get("target") or raw.get("to") or raw.get("target_id") or raw.get("targetId")
            )
            link_type_value = raw.get("link_type") or raw.get("linkType")
            if isinstance(link_type_value, str) and link_type_value.strip():
                requested_link_type = link_type_value.strip()
            else:
                legacy_role = raw.get("role")
                if isinstance(legacy_role, str) and legacy_role.strip():
                    requested_link_type = legacy_role.strip()
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            source, target = raw[0], raw[1]
            if len(raw) >= 3 and isinstance(raw[2], str) and raw[2].strip():
                requested_link_type = raw[2].strip()
        if (
            isinstance(source, str)
            and source.strip()
            and isinstance(target, str)
            and target.strip()
        ):
            result.append((source.strip(), target.strip(), requested_link_type))
    return result


def _infer_link_type(
    source_type: str, target_type: str, requested: str | None = None
) -> str | None:
    if requested in {"visual_reference_for", "source_media_for"}:
        requested = "media_input_for"
    if requested in LINK_TYPE_VALUES and _link_type_allowed(requested, source_type, target_type):
        return requested
    if target_type == "videoComposeNode" and _link_type_allowed(
        "composition_input_for",
        source_type,
        target_type,
    ):
        return "composition_input_for"
    source_object = _link_object_type(source_type)
    target_object = _link_object_type(target_type)
    if source_object in {"TextNode", "ScriptNode"}:
        if target_object in {"TextNode", "ScriptNode"}:
            return "context_for"
        if target_object in {"ImageNode", "VideoNode", "AudioNode"}:
            return "prompt_for"
    if source_object in {"ImageNode", "VideoNode", "AudioNode"} and target_object in {
        "TextNode",
        "ImageNode",
        "VideoNode",
        "AudioNode",
        "ScriptNode",
    }:
        return "media_input_for"
    return None


def _link_type_allowed(link_type: str, source_type: str, target_type: str) -> bool:
    rule = LINK_TYPE_RULES.get(link_type)
    if rule is None:
        return False
    source_objects, target_objects = rule
    source_object = _link_object_type(source_type)
    target_object = _link_object_type(target_type)
    return source_object in source_objects and target_object in target_objects


def _link_object_type(node_type: str) -> str:
    return LINK_OBJECT_TYPE_BY_NODE_TYPE.get(node_type, "")


def _groups(raw_groups: Any, layout: Any) -> list[dict[str, Any]]:
    groups = raw_groups
    if not isinstance(groups, list) and isinstance(layout, dict):
        groups = layout.get("groups")
    result: list[dict[str, Any]] = []
    if not isinstance(groups, list):
        return result
    for raw in groups:
        if not isinstance(raw, dict):
            continue
        node_ids = raw.get("node_ids") or raw.get("nodeIds") or raw.get("nodes")
        if not isinstance(node_ids, list):
            continue
        refs = [item.strip() for item in node_ids if isinstance(item, str) and item.strip()]
        if len(refs) < 2:
            continue
        label = raw.get("label") or raw.get("title") or raw.get("name")
        result.append({"label": str(label).strip() if label else "工作流", "node_ids": refs})
    return result


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
