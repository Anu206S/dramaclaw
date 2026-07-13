"""Build Freezone workflow plans from Freezone agent catalog JSON files.

This module is intentionally independent from the legacy registered workflow
builders.  It only returns the same ``freezone_workflow_plan.v1`` shape that
``workflow_graph.py`` already knows how to turn into canvas commands.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from novelvideo.freezone.agent_config_store import list_user_agent_config_items
except Exception:  # pragma: no cover - Hermes can run before app imports are available.
    list_user_agent_config_items = None

CATALOG_PREFIX = "catalog."
PLAN_SCHEMA_VERSION = "freezone_workflow_plan.v1"

_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_ROOT = _ROOT / "src" / "novelvideo" / "freezone" / "agent_catalog" / "builtins"
_SKILLS_DIR = _CATALOG_ROOT / "skills"
_RECIPES_DIR = _CATALOG_ROOT / "recipes"

_NODE_TYPE_BY_GENERATION = {
    "text": "textAnnotationNode",
    "image": "imageGenNode",
    "video": "videoNode",
    "audio": "audioNode",
}

_NODE_TYPE_BY_STEP = {
    "textGeneration": "textAnnotationNode",
    "imageGeneration": "imageGenNode",
    "videoGeneration": "videoNode",
    "audioGeneration": "audioNode",
}

_STAGE_BY_NODE_TYPE = {
    "textAnnotationNode": "story",
    "imageGenNode": "image",
    "videoNode": "video",
    "audioNode": "audio",
    "videoComposeNode": "compose",
}

_FALLBACK_WORKFLOW_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "text-to-image",
        "name": "文生图",
        "description": "根据文本需求生成图片节点。",
        "aliases": ["text_to_image"],
        "keywords": ["文生图", "图片", "海报", "image"],
        "template_id": "text-to-image",
        "template_name": "文生图",
        "operation_type": "text-to-image",
        "goal": "根据用户需求生成图片提示词并创建图片生成节点",
        "node_type": "imageGeneration",
        "generation_type": "image",
    },
    {
        "id": "image-to-video",
        "name": "图生视频",
        "description": "基于图片素材生成视频节点。",
        "aliases": ["image_to_video"],
        "keywords": ["图生视频", "图片转视频", "视频"],
        "template_id": "image-to-video",
        "template_name": "图生视频",
        "operation_type": "image-to-video",
        "goal": "基于用户图片素材生成视频片段",
        "node_type": "videoGeneration",
        "generation_type": "video",
    },
    {
        "id": "text-to-video",
        "name": "文生视频",
        "description": "根据文本需求生成视频节点。",
        "aliases": ["text_to_video"],
        "keywords": ["文生视频", "视频", "短片"],
        "template_id": "text-to-video",
        "template_name": "文生视频",
        "operation_type": "text-to-video",
        "goal": "根据用户需求生成视频片段",
        "node_type": "videoGeneration",
        "generation_type": "video",
    },
    {
        "id": "image-to-text",
        "name": "图像理解",
        "description": "从图片素材中提取文本描述。",
        "aliases": ["image_to_text"],
        "keywords": ["图像理解", "图片分析", "识图"],
        "template_id": "image-to-text",
        "template_name": "图像理解",
        "operation_type": "image-to-text",
        "goal": "分析用户图片素材并输出结构化描述",
        "node_type": "textGeneration",
        "generation_type": "text",
    },
    {
        "id": "text-to-audio",
        "name": "文生音频",
        "description": "根据文本需求生成音频节点。",
        "aliases": ["text_to_audio"],
        "keywords": ["音频", "配音", "音乐", "audio"],
        "template_id": "text-to-audio",
        "template_name": "文生音频",
        "operation_type": "text-to-audio",
        "goal": "根据用户需求生成音频内容",
        "node_type": "audioGeneration",
        "generation_type": "audio",
    },
    {
        "id": "product-video",
        "name": "产品视频",
        "description": "围绕产品卖点生成视频工作流。",
        "aliases": ["product_video"],
        "keywords": ["产品视频", "商品", "产品", "卖点"],
        "template_id": "product-video",
        "template_name": "产品视频",
        "operation_type": "product-video",
        "goal": "围绕产品卖点生成视频内容",
        "node_type": "videoGeneration",
        "generation_type": "video",
    },
    {
        "id": "music-video",
        "name": "音乐视频",
        "description": "根据音乐或主题生成 MV 工作流。",
        "aliases": ["mv", "music_video"],
        "keywords": ["MV", "音乐视频", "music"],
        "template_id": "music-video",
        "template_name": "音乐视频",
        "operation_type": "music-video",
        "goal": "根据音乐或主题生成 MV 视频内容",
        "node_type": "videoGeneration",
        "generation_type": "video",
    },
    {
        "id": "short-drama",
        "name": "短剧",
        "description": "根据剧本或创意生成短剧工作流。",
        "aliases": ["short_drama"],
        "keywords": [{"keyword": "短剧", "weight": 2}, "故事", "剧本", "复仇"],
        "template_id": "short-drama-from-script",
        "template_name": "短剧脚本流程",
        "operation_type": "short-drama-from-script",
        "goal": "根据用户剧本或故事创意生成短剧制作节点",
        "node_type": "videoGeneration",
        "generation_type": "video",
    },
    {
        "id": "video-ad",
        "name": "广告视频",
        "description": "生成产品或品牌广告视频工作流。",
        "aliases": ["ad_video", "video_ad"],
        "keywords": ["产品", "品牌", "宣传", "创意"],
        "template_id": "video-ad-full",
        "template_name": "广告视频完整流程",
        "operation_type": "video-ad-creative-outline",
        "goal": "生成广告创意大纲",
        "node_type": "textGeneration",
        "generation_type": "text",
        "steps": [
            {
                "id": "ad-outline",
                "step_number": 1,
                "goal_template": "生成广告创意大纲",
                "node_type": "textGeneration",
                "action_key": "video-ad-creative-outline",
                "prompt_strategy": "user_message",
                "input_strategy": {"type": "none"},
            },
            {
                "id": "storyboard-grid",
                "step_number": 2,
                "goal_template": "将广告脚本中的所有 Shot 合成为多宫格分镜图",
                "node_type": "imageGeneration",
                "action_key": "video-storyboard-grid",
                "prompt_strategy": "llm_refine",
                "input_strategy": {"type": "previous_step", "step_id": "ad-outline"},
            },
        ],
    },
)


def registered_catalog_workflows() -> list[dict[str, Any]]:
    """Return assistant-visible workflow entries backed by JSON skills."""
    workflows: list[dict[str, Any]] = []
    for skill in _load_skills():
        skill_id = _text(skill.get("id"))
        if not skill_id or skill.get("_disabled") is True:
            continue
        templates = _templates(skill)
        label = _catalog_label(skill)
        workflows.append(
            {
                "workflow_type": _catalog_type(skill_id),
                "label": f"{label}（配置）",
                "description": _text(skill.get("description")),
                "aliases": _catalog_aliases(skill, None),
                "template_count": len(templates),
                "source": "workflow_json",
                "catalog_source": _catalog_source(skill),
                "catalog_source_label": _catalog_source_label(skill),
                "catalog_base_source": _text(skill.get("_catalog_base_source")),
            }
        )
        for template in templates:
            template_id = _text(template.get("id"))
            if not template_id:
                continue
            workflows.append(
                {
                    "workflow_type": _catalog_type(skill_id, template_id),
                    "label": f"{label} / {_template_label(template)}（配置）",
                    "description": _text(template.get("description")),
                    "aliases": _catalog_aliases(skill, template),
                    "template_count": 1,
                    "source": "workflow_json",
                    "catalog_source": _catalog_source(skill),
                    "catalog_source_label": _catalog_source_label(skill),
                    "catalog_base_source": _text(skill.get("_catalog_base_source")),
                }
            )
    return sorted(workflows, key=lambda item: str(item.get("workflow_type") or ""))


def catalog_workflow_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for workflow in registered_catalog_workflows():
        workflow_type = _text(workflow.get("workflow_type"))
        if not workflow_type:
            continue
        aliases[_alias_key(workflow_type)] = workflow_type
        for alias in workflow.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                aliases[_alias_key(alias)] = workflow_type
    return aliases


def build_catalog_workflow_plan(args: dict[str, Any]) -> dict[str, Any] | None:
    """Return a plan for ``catalog.*`` workflow types, or ``None`` if not applicable."""
    workflow_type = _requested_workflow_type(args)
    if not workflow_type:
        return None
    spec = _parse_catalog_type(workflow_type)
    if spec is None:
        return None
    skill_id, template_id = spec
    skill = _load_skill(skill_id)
    if skill is None:
        return _error(f"catalog skill not found: {skill_id}")
    template = _choose_template(skill, template_id, args)
    if template is None:
        return _error(f"catalog template not found for skill: {skill_id}")
    recipes = _recipe_index()
    return _build_plan(skill=skill, template=template, recipes=recipes, args=args)


def resolve_catalog_workflow(args: dict[str, Any]) -> dict[str, Any]:
    """Resolve a user request to JSON-backed workflow skill/template candidates.

    This is intentionally deterministic.  The assistant can call it as the
    first read-only step, show the top candidate to the user, then call
    ``freezone_build_workflow_plan`` or ``freezone_create_workflow_graph`` only
    after confirmation.
    """
    user_goal = _workflow_goal_text(args)
    limit = _int(args.get("limit"), 5)
    if limit < 1:
        limit = 5
    exact = _exact_catalog_workflow_candidate(args, user_goal)
    if exact is not None:
        return {
            "ok": True,
            "resolver": "workflow_json_catalog.v1",
            "user_goal": user_goal,
            "matched": True,
            "ambiguous": False,
            "matched_skill_count": 1,
            "recommended": exact,
            "candidates": [exact],
            "next_step": {
                "requires_user_confirmation": True,
                "message": "已精确命中 JSON workflow skill/template；请确认后继续生成工作流计划。",
                "tool": "freezone_build_workflow_plan",
                "arguments": {
                    "workflow_type": exact.get("workflow_type"),
                    "user_goal": user_goal,
                },
            },
        }

    skills = _load_skills()
    candidates: list[dict[str, Any]] = []
    for skill in skills:
        if skill.get("_disabled") is True:
            continue
        skill_id = _text(skill.get("id"))
        if not skill_id:
            continue
        skill_score, skill_reasons = _skill_score(skill, user_goal)
        templates = _templates(skill) or [{}]
        for template in templates:
            template_id = _text(template.get("id"))
            template_score, template_reasons = _template_resolution_score(template, user_goal)
            score = skill_score + template_score
            if not user_goal:
                score = 0.0
            workflow_type = _catalog_type(skill_id, template_id or None)
            candidates.append(
                {
                    "workflow_type": workflow_type,
                    "skill_id": skill_id,
                    "skill_name": _catalog_label(skill),
                    "template_id": template_id,
                    "template_name": _template_label(template) if template else "",
                    "score": round(score, 3),
                    "reasons": skill_reasons + template_reasons,
                    "description": _text(template.get("description"))
                    or _text(skill.get("description")),
                    "step_count": len(template.get("steps") or []) if template else 0,
                    "source": "workflow_json",
                    "catalog_source": _catalog_source(skill),
                    "catalog_source_label": _catalog_source_label(skill),
                }
            )
    candidates.sort(
        key=lambda item: (
            -float(item.get("score") or 0),
            str(item.get("workflow_type") or ""),
        )
    )
    top_candidates = candidates[:limit]
    top = top_candidates[0] if top_candidates else None
    second_score = float(top_candidates[1].get("score") or 0) if len(top_candidates) > 1 else 0.0
    top_score = float(top.get("score") or 0) if top else 0.0
    matched = bool(top and top_score > 0)
    matched_skill_ids = {
        _text(candidate.get("skill_id"))
        for candidate in top_candidates
        if float(candidate.get("score") or 0) > 0 and _text(candidate.get("skill_id"))
    }
    ambiguous = bool(
        matched
        and (
            len(matched_skill_ids) > 1
            or (second_score > 0 and top_score - second_score < 1.0)
        )
    )
    next_step = {
        "requires_user_confirmation": False,
        "message": "没有命中 JSON workflow skill；请询问用户补充目标或手动选择 workflow。",
    }
    if matched and top:
        if ambiguous:
            next_step = {
                "requires_user_selection": True,
                "message": "命中多个 JSON workflow skill/template；请让用户从 candidates 中选择一个 workflow_type 后再继续。",
                "candidate_workflow_types": [
                    _text(candidate.get("workflow_type"))
                    for candidate in top_candidates
                    if float(candidate.get("score") or 0) > 0
                ],
            }
        else:
            next_step = {
                "requires_user_confirmation": True,
                "message": "请先向用户确认命中的 skill/template，再继续生成工作流计划。",
                "tool": "freezone_build_workflow_plan",
                "arguments": {
                    "workflow_type": top.get("workflow_type"),
                    "user_goal": user_goal,
                },
            }
    return {
        "ok": True,
        "resolver": "workflow_json_catalog.v1",
        "user_goal": user_goal,
        "matched": matched,
        "ambiguous": ambiguous,
        "matched_skill_count": len(matched_skill_ids),
        "recommended": top if matched else None,
        "candidates": top_candidates,
        "next_step": next_step,
    }


def _exact_catalog_workflow_candidate(args: dict[str, Any], user_goal: str) -> dict[str, Any] | None:
    requested_type = _text(args.get("workflow_type") or args.get("workflowType") or args.get("type"))
    normalized_request = _alias_key(requested_type or user_goal)
    if not normalized_request:
        return None
    aliases = catalog_workflow_aliases()
    workflow_type = aliases.get(normalized_request)
    if workflow_type is None and normalized_request.startswith(CATALOG_PREFIX):
        workflow_type = normalized_request
    if workflow_type is None:
        return None
    for workflow in registered_catalog_workflows():
        if _alias_key(workflow.get("workflow_type")) != _alias_key(workflow_type):
            continue
        parsed = _parse_catalog_type(_text(workflow.get("workflow_type")))
        skill_id = parsed[0] if parsed else ""
        template_id = parsed[1] if parsed else ""
        return {
            "workflow_type": workflow.get("workflow_type"),
            "skill_id": skill_id,
            "skill_name": str(workflow.get("label") or "").replace("（配置）", "").split(" / ")[0],
            "template_id": template_id or "",
            "template_name": str(workflow.get("label") or "").replace("（配置）", ""),
            "score": 99.0,
            "reasons": [f"精确匹配 workflow_type/alias：{requested_type or user_goal}"],
            "description": workflow.get("description") or "",
            "step_count": 0,
            "source": "workflow_json",
            "catalog_source": workflow.get("catalog_source") or "",
            "catalog_source_label": workflow.get("catalog_source_label") or "",
        }
    return None


def _build_plan(
    *,
    skill: dict[str, Any],
    template: dict[str, Any],
    recipes: dict[str, dict[str, Any]],
    args: dict[str, Any],
) -> dict[str, Any]:
    skill_id = _text(skill.get("id"))
    template_id = _text(template.get("id"))
    user_goal = _workflow_goal_text(args) or _template_label(template)
    title = _text(args.get("title") or args.get("name")) or _catalog_label(skill)
    group_label = f"{title} / {_template_label(template)}"

    raw_steps = [step for step in template.get("steps") or [] if isinstance(step, dict)]
    raw_steps.sort(
        key=lambda item: (_int(_get(item, "stepNumber", "step_number"), 999), _text(item.get("id")))
    )

    nodes: list[dict[str, Any]] = [
        {
            "id": "catalog_user_input",
            "node_type": "textAnnotationNode",
            "label": "用户需求 / 输入素材",
            "description": user_goal,
            "stage": "input",
            "data": {
                "displayName": "用户需求 / 输入素材",
                "title": "用户需求 / 输入素材",
                "content": user_goal,
                "prompt": user_goal,
                "workflowCatalogRole": "user_input",
            },
        }
    ]
    edges: list[dict[str, str]] = []
    step_ids: list[str] = []

    for step in raw_steps:
        step_id = _safe_id(_text(step.get("id")) or f"step_{len(step_ids) + 1}")
        step_ids.append(step_id)
        operation_type = _text(
            _get(step, "operationType", "operation_type", "actionKey", "action_key")
        )
        recipe = recipes.get(operation_type) if operation_type else None
        node_type = _node_type_for_step(step, recipe)
        prompt = _compose_node_prompt(
            skill=skill,
            template=template,
            step=step,
            recipe=recipe,
            user_goal=user_goal,
        )
        recipe_settings = _recipe_settings(recipe)
        prompt_builder = _prompt_builder(
            step=step,
            recipe=recipe,
            user_goal=user_goal,
        )
        label = _text(_get(step, "goalTemplate", "goal_template")) or _text(
            recipe.get("name") if recipe else ""
        )
        if len(label) > 48:
            label = label[:45] + "..."
        label = label or operation_type or step_id
        data = {
            "displayName": label,
            "title": label,
            "content": prompt,
            "prompt": prompt,
            "description": prompt,
            "workflowCatalog": {
                "skillId": skill_id,
                "templateId": template_id,
                "stepId": step_id,
                "operationType": operation_type,
                "recipeId": _text(recipe.get("id") if recipe else ""),
                "promptStrategy": _text(_get(step, "promptStrategy", "prompt_strategy")),
                "inputStrategy": _get(step, "inputStrategy", "input_strategy") or {},
                "model": _text(step.get("model")),
                "needReview": bool(step.get("needReview")),
                "recipeSettings": recipe_settings,
                "promptBuilder": prompt_builder,
            },
        }
        model = _text(step.get("model"))
        if model:
            data["model"] = model
        aspect_ratio = _text(_get(step, "aspectRatio", "aspect_ratio"))
        if aspect_ratio:
            data["aspectRatio"] = aspect_ratio
        if node_type == "audioNode":
            data.setdefault("text", prompt)
        nodes.append(
            {
                "id": step_id,
                "node_type": node_type,
                "label": label,
                "description": prompt,
                "stage": _stage_for_step(step, node_type),
                "data": data,
            }
        )
        for source in _dependency_sources(step, step_ids[:-1]):
            edges.append({"source": source, "target": step_id})

    if len(nodes) > 1:
        groups = [{"label": group_label, "node_ids": [node["id"] for node in nodes]}]
    else:
        groups = []
    return {
        "ok": True,
        "schema_version": PLAN_SCHEMA_VERSION,
        "workflow_type": _catalog_type(skill_id, template_id),
        "mode": "analysis_only",
        "summary": _text(template.get("description")) or _text(skill.get("description")),
        "source_context": {"user_goal": user_goal, "canvas_context": [], "input_assets": []},
        "analysis": {"entities": [], "production_units": [], "risks": []},
        "phases": [group_label],
        "assumptions": [
            "该工作流由 Freezone 内置与当前用户 agent_config 的 skills/recipes JSON 生成。",
            "节点创建后仍需用户确认运行；创建节点不会自动生成图片、视频或音频。",
        ],
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


def _compose_node_prompt(
    *,
    skill: dict[str, Any],
    template: dict[str, Any],
    step: dict[str, Any],
    recipe: dict[str, Any] | None,
    user_goal: str,
) -> str:
    goal = _text(_get(step, "goalTemplate", "goal_template")) or _text(step.get("id"))
    recipe_name = _text(recipe.get("name") if recipe else "")
    operation_type = _text(
        _get(step, "operationType", "operation_type", "actionKey", "action_key")
    )
    prompt_strategy = _text(_get(step, "promptStrategy", "prompt_strategy"))
    system_prompt = _text(_get(recipe, "system_prompt")) if recipe else ""
    is_prompt_recipe = _looks_like_prompt_recipe(system_prompt)
    if prompt_strategy == "user_message":
        return user_goal
    if prompt_strategy == "llm_refine" or is_prompt_recipe:
        target = goal or recipe_name or operation_type or "当前节点"
        return (
            f"主题：{user_goal}\n"
            f"任务：{target}\n"
            "根据用户需求和上游节点内容生成最终可执行内容。"
            "具体生成规则已保存到 workflowCatalog.promptBuilder。"
        ).strip()
    return goal or recipe_name or operation_type or user_goal


def _recipe_settings(recipe: dict[str, Any] | None) -> dict[str, Any]:
    if not recipe:
        return {}
    settings: dict[str, Any] = {}
    for source_key, target_key in (
        ("output_kind", "outputKind"),
        ("generationType", "outputKind"),
        ("generation_type", "outputKind"),
        ("requires_source_media", "requiresSourceMedia"),
        ("requiresSourceMedia", "requiresSourceMedia"),
        ("force_enhancement", "forceEnhancement"),
        ("forceEnhancement", "forceEnhancement"),
        ("skip_detail_check", "skipDetailCheck"),
        ("skipDetailCheck", "skipDetailCheck"),
        ("enabled", "enabled"),
        ("version", "version"),
    ):
        value = _get(recipe, source_key)
        if value is not None and target_key not in settings:
            settings[target_key] = value
    action_keys = [
        _text(item)
        for field in ("actionKeys", "action_keys")
        for item in recipe.get(field) or []
        if _text(item)
    ]
    if action_keys:
        settings["actionKeys"] = action_keys
    return settings


def _prompt_builder(
    *,
    step: dict[str, Any],
    recipe: dict[str, Any] | None,
    user_goal: str,
) -> dict[str, Any]:
    strategy = _text(_get(step, "promptStrategy", "prompt_strategy"))
    if not strategy:
        strategy = "llm_refine" if recipe else "template"
    builder: dict[str, Any] = {
        "mode": strategy,
        "userGoal": user_goal,
        "goalTemplate": _text(_get(step, "goalTemplate", "goal_template")),
        "inputStrategy": _get(step, "inputStrategy", "input_strategy") or {},
    }
    if not recipe:
        return builder
    system_prompt = _text(_get(recipe, "system_prompt"))
    builder.update(
        {
            "recipeId": _text(recipe.get("id")),
            "recipeName": _text(recipe.get("name")),
            "recipeRef": _recipe_ref(recipe),
            "isPromptRecipe": _looks_like_prompt_recipe(system_prompt),
        }
    )
    return builder


def _looks_like_prompt_recipe(system_prompt: str) -> bool:
    text = _text(system_prompt)
    if not text:
        return False
    markers = (
        "提示词/指令",
        "提示词",
        "原始提示词",
        "生成指令",
        "refined prompt",
        "output only refined prompt",
        "prompt generation",
        "image generation ai",
        "video generation ai",
    )
    lower = text.lower()
    return any(marker.lower() in lower for marker in markers)


def _dependency_sources(step: dict[str, Any], previous_step_ids: list[str]) -> list[str]:
    input_strategy = _get(step, "inputStrategy", "input_strategy")
    if not isinstance(input_strategy, dict):
        return ["catalog_user_input"] if not previous_step_ids else [previous_step_ids[-1]]
    strategy_type = _text(input_strategy.get("type"))
    raw_step_id = _text(_get(input_strategy, "stepId", "step_id"))
    if raw_step_id:
        return [_safe_id(raw_step_id)]
    raw_step_ids = _get(input_strategy, "stepIds", "step_ids")
    if isinstance(raw_step_ids, list):
        step_ids = [_safe_id(_text(item)) for item in raw_step_ids if _text(item)]
        if step_ids:
            return step_ids
    if strategy_type == "none":
        return []
    if strategy_type == "user_assets":
        return ["catalog_user_input"]
    if strategy_type in {"previous_step", "previous_step_and_user_assets"}:
        return previous_step_ids[-1:] or ["catalog_user_input"]
    if strategy_type in {"previous_steps", "previous_steps_and_user_assets"}:
        return previous_step_ids or ["catalog_user_input"]
    return previous_step_ids[-1:] or ["catalog_user_input"]


def _node_type_for_step(step: dict[str, Any], recipe: dict[str, Any] | None) -> str:
    node_type = _NODE_TYPE_BY_STEP.get(_text(_get(step, "nodeType", "node_type")))
    if node_type:
        return node_type
    if recipe:
        generation_type = _text(_get(recipe, "generationType", "generation_type", "output_kind"))
        return _NODE_TYPE_BY_GENERATION.get(generation_type, "textAnnotationNode")
    return "textAnnotationNode"


def _stage_for_step(step: dict[str, Any], node_type: str) -> str:
    text = " ".join(
        _text(value)
        for value in (
            step.get("id"),
            _get(step, "goalTemplate", "goal_template"),
            _get(step, "operationType", "operation_type", "actionKey", "action_key"),
            _get(step, "nodeType", "node_type"),
        )
    ).lower()
    for key in ("input", "story", "character", "scene", "prop", "asset", "shot", "frame", "image", "video", "audio", "compose"):
        if key in text:
            return "asset" if key == "prop" else key
    return _STAGE_BY_NODE_TYPE.get(node_type, "story")


def _choose_template(
    skill: dict[str, Any],
    template_id: str | None,
    args: dict[str, Any],
) -> dict[str, Any] | None:
    templates = _templates(skill)
    requested = _text(
        template_id
        or args.get("template_id")
        or args.get("templateId")
        or args.get("workflow_template")
        or args.get("workflowTemplate")
    )
    if requested:
        normalized = _alias_key(requested)
        for template in templates:
            if _alias_key(_text(template.get("id"))) == normalized:
                return template
    if not templates:
        return None
    message = _workflow_goal_text(args)
    if message:
        scored = [
            (_template_score(template, message), index, template)
            for index, template in enumerate(templates)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        if scored[0][0] > 0:
            return scored[0][2]
    return templates[0]


def _template_score(template: dict[str, Any], message: str) -> float:
    condition = template.get("condition")
    if not isinstance(condition, dict):
        return 0
    text = message.lower()
    score = 0.0
    for keyword in _get(condition, "messageKeywords", "message_keywords") or []:
        keyword_text = _text(keyword).lower()
        if keyword_text and keyword_text in text:
            score += 1.0
    return score


def _skill_score(skill: dict[str, Any], message: str) -> tuple[float, list[str]]:
    text = message.lower()
    score = 0.0
    reasons: list[str] = []
    triggers = skill.get("triggers")
    keywords = triggers.get("keywords") if isinstance(triggers, dict) else []
    for keyword in keywords or []:
        weight = 1.0
        if isinstance(keyword, dict):
            keyword_text = _text(keyword.get("keyword"))
            weight = _float(keyword.get("weight"), 1.0)
        else:
            keyword_text = _text(keyword)
        if keyword_text and keyword_text.lower() in text:
            score += weight
            reasons.append(f"命中 skill 关键词：{keyword_text}")
    name_bits = [
        _text(skill.get("id")),
        _text(skill.get("name")),
        _text(skill.get("label")),
        _text(skill.get("category")),
    ]
    for bit in name_bits:
        if bit and bit.lower() in text:
            score += 0.75
            reasons.append(f"命中 skill 标识：{bit}")
    for alias in _string_list(skill.get("aliases")):
        alias_text = alias.lower()
        if not alias_text:
            continue
        if alias_text == text:
            score += 3.0
            reasons.append(f"精确命中 skill 别名：{alias}")
        elif alias_text in text:
            score += 1.5
            reasons.append(f"命中 skill 别名：{alias}")
    return score, reasons[:8]


def _template_resolution_score(template: dict[str, Any], message: str) -> tuple[float, list[str]]:
    text = message.lower()
    score = 0.0
    reasons: list[str] = []
    condition = template.get("condition")
    if isinstance(condition, dict):
        for keyword in _get(condition, "messageKeywords", "message_keywords") or []:
            keyword_text = _text(keyword)
            if keyword_text and keyword_text.lower() in text:
                score += 1.25
                reasons.append(f"命中模板关键词：{keyword_text}")
        if _get(condition, "textOnly", "text_only") and not _looks_like_asset_request(text):
            score += 0.25
            reasons.append("模板适合纯文本描述")
        for input_type in _get(condition, "hasInputTypes", "has_input_types") or []:
            input_text = _text(input_type).lower()
            if input_text and input_text in text:
                score += 0.5
                reasons.append(f"命中输入类型：{input_text}")
    template_id = _text(template.get("id"))
    if template_id and template_id.lower().replace("-", " ") in text:
        score += 0.75
        reasons.append(f"命中模板标识：{template_id}")
    for alias in _string_list(template.get("aliases")):
        alias_text = alias.lower()
        if not alias_text:
            continue
        if alias_text == text:
            score += 3.0
            reasons.append(f"精确命中模板别名：{alias}")
        elif alias_text in text:
            score += 1.5
            reasons.append(f"命中模板别名：{alias}")
    return score, reasons[:8]


def _looks_like_asset_request(text: str) -> bool:
    return any(keyword in text for keyword in ("图片", "图像", "素材", "image", "asset", "已有图"))


def _requested_workflow_type(args: dict[str, Any]) -> str:
    raw = args.get("workflow_type") or args.get("workflowType") or args.get("type")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    value = _text(raw)
    alias_key = _alias_key(value)
    if alias_key.startswith(CATALOG_PREFIX):
        return alias_key
    return catalog_workflow_aliases().get(alias_key, alias_key)


def _parse_catalog_type(value: str) -> tuple[str, str | None] | None:
    text = _alias_key(value)
    if not text.startswith(CATALOG_PREFIX):
        return None
    body = text[len(CATALOG_PREFIX) :]
    if not body:
        return None
    parts = [part for part in body.split(".") if part]
    if not parts:
        return None
    skill_id = parts[0].replace("_", "-")
    template_id = parts[1].replace("_", "-") if len(parts) > 1 else None
    return skill_id, template_id


def _catalog_type(skill_id: str, template_id: str | None = None) -> str:
    base = f"{CATALOG_PREFIX}{_alias_key(skill_id).replace('-', '_')}"
    if template_id:
        return f"{base}.{_alias_key(template_id).replace('-', '_')}"
    return base


def _catalog_aliases(skill: dict[str, Any], template: dict[str, Any] | None = None) -> list[str]:
    skill_id = _text(skill.get("id"))
    label = _catalog_label(skill)
    template_id = _text(template.get("id")) if template else ""
    aliases = [
        skill_id,
        _alias_key(skill_id),
        f"catalog_{skill_id}",
        f"json_{skill_id}",
        f"配置{label}",
        f"{label}配置",
    ]
    aliases.extend(_string_list(skill.get("aliases")))
    if template_id:
        aliases.extend(
            [
                template_id,
                _alias_key(template_id),
                f"{skill_id}_{template_id}",
                f"catalog_{skill_id}_{template_id}",
                f"json_{skill_id}_{template_id}",
            ]
        )
        aliases.extend(_string_list(template.get("aliases")))
    return _unique_texts(aliases)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = _text(value)
        if not text:
            continue
        key = _alias_key(text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _load_skill(skill_id: str) -> dict[str, Any] | None:
    wanted = _alias_key(skill_id)
    for skill in _load_skills():
        if _alias_key(_text(skill.get("id"))) == wanted:
            return skill
    return None


def _load_skills() -> list[dict[str, Any]]:
    return _load_agent_config_items("skills", _SKILLS_DIR)


def _recipe_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for recipe in _load_agent_config_items("recipes", _RECIPES_DIR):
        if recipe.get("enabled") is False:
            continue
        keys = [_text(recipe.get("id"))]
        for field in ("operationTypes", "operation_types", "actionKeys", "action_keys"):
            keys.extend(_text(item) for item in recipe.get(field) or [])
        for key in keys:
            if key:
                index.setdefault(key, recipe)
    return index


def _load_agent_config_items(kind: str, fallback_dir: Path) -> list[dict[str, Any]]:
    fallback_items = _load_json_dir(fallback_dir)
    if not fallback_items:
        fallback_items = _fallback_agent_config_items(kind)
    if list_user_agent_config_items is not None:
        username = _catalog_username()
        if username:
            try:
                loaded_items = list_user_agent_config_items(username, kind)
                return _merge_agent_config_items(fallback_items, loaded_items)
            except Exception:
                pass
    return fallback_items


def _merge_agent_config_items(
    builtin_items: list[dict[str, Any]],
    loaded_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge code fallback builtins with user/config-store items."""

    by_id: dict[str, dict[str, Any]] = {
        _text(item.get("id")): {**item, "_catalog_source": item.get("_catalog_source") or "builtin"}
        for item in builtin_items
        if _text(item.get("id"))
    }
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in loaded_items:
        if not isinstance(item, dict):
            continue
        item_id = _text(item.get("id"))
        if not item_id:
            continue
        if item.get("hidden") is True:
            by_id.pop(item_id, None)
            seen.add(item_id)
            continue
        base = by_id.pop(item_id, {})
        merged = {**base, **item}
        merged.setdefault("_catalog_source", item.get("_catalog_source") or "user")
        ordered.append(merged)
        seen.add(item_id)
    ordered.extend(item for item_id, item in sorted(by_id.items()) if item_id not in seen)
    return ordered


def _fallback_agent_config_items(kind: str) -> list[dict[str, Any]]:
    if kind == "skills":
        return [_fallback_skill(spec) for spec in _FALLBACK_WORKFLOW_SPECS]
    if kind == "recipes":
        return [_fallback_recipe(spec) for spec in _FALLBACK_WORKFLOW_SPECS] + [
            {
                "id": "video-storyboard-grid",
                "name": "广告多宫格分镜图",
                "output_kind": "image",
                "action_keys": ["video-storyboard-grid"],
                "system_prompt": "Image generation AI prompt generation. 输出用于生成多宫格广告分镜图的提示词/指令。",
                "requires_source_media": True,
                "_catalog_source": "builtin",
            }
        ]
    return []


def _fallback_skill(spec: dict[str, Any]) -> dict[str, Any]:
    template_id = _text(spec.get("template_id"))
    steps = spec.get("steps")
    if not isinstance(steps, list):
        steps = [
            {
                "id": template_id,
                "step_number": 1,
                "goal_template": _text(spec.get("goal")),
                "node_type": _text(spec.get("node_type")),
                "action_key": _text(spec.get("operation_type")),
                "prompt_strategy": "llm_refine",
                "input_strategy": {"type": "user_assets"},
            }
        ]
    return {
        "id": _text(spec.get("id")),
        "name": _text(spec.get("name")),
        "description": _text(spec.get("description")),
        "category": "builtin",
        "aliases": list(spec.get("aliases") or []),
        "triggers": {"keywords": list(spec.get("keywords") or [])},
        "workflow_templates": [
            {
                "id": template_id,
                "name": _text(spec.get("template_name")),
                "description": _text(spec.get("description")),
                "condition": {"message_keywords": list(spec.get("keywords") or [])},
                "steps": steps,
            }
        ],
        "_catalog_source": "builtin",
    }


def _fallback_recipe(spec: dict[str, Any]) -> dict[str, Any]:
    operation_type = _text(spec.get("operation_type"))
    return {
        "id": operation_type,
        "name": _text(spec.get("goal")) or _text(spec.get("name")),
        "output_kind": _text(spec.get("generation_type")) or "text",
        "action_keys": [operation_type],
        "system_prompt": "Prompt generation recipe. 输出可交给下游节点执行的提示词/指令。",
        "requires_source_media": True,
        "_catalog_source": "builtin",
    }


def _catalog_username() -> str:
    if os.environ.get("ST_EDITION", "").strip().lower() == "ce":
        return "local"
    return (
        os.environ.get("DRAMACLAW_USER")
        or os.environ.get("SUPERTALE_USER")
        or os.environ.get("FREEZONE_USER")
        or "local"
    ).strip()


def _recipe_ref(recipe: dict[str, Any]) -> str:
    recipe_id = _text(recipe.get("id"))
    if recipe.get("_catalog_source") == "user":
        return f"output/{{user}}/_account/freezone/agent_config/recipes/{recipe_id}.json"
    return f"agent_catalog/builtins/recipes/{recipe_id}.json"


def _catalog_source(payload: dict[str, Any]) -> str:
    return _text(payload.get("_catalog_source")) or "builtin"


def _catalog_source_label(payload: dict[str, Any]) -> str:
    source = _catalog_source(payload)
    if source == "user" and _text(payload.get("_catalog_base_source")) == "builtin":
        return "用户覆盖内置"
    if source == "user":
        return "用户自定义"
    return "内置"


def _load_json_dir(path: Path) -> list[dict[str, Any]]:
    if not path.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for file_path in sorted(path.glob("*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _templates(skill: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _get(skill, "workflowTemplates", "workflow_templates") or []
    return [item for item in raw if isinstance(item, dict)]


def _catalog_label(skill: dict[str, Any]) -> str:
    return _text(skill.get("name") or skill.get("label") or skill.get("id")) or "配置工作流"


def _template_label(template: dict[str, Any]) -> str:
    return _text(template.get("name") or template.get("label") or template.get("id")) or "默认模板"


def _workflow_goal_text(args: dict[str, Any]) -> str:
    for field in (
        "user_goal",
        "userGoal",
        "goal",
        "brief",
        "description",
        "message",
        "prompt",
        "title",
        "name",
    ):
        value = args.get(field)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value.strip())
    return ""


def _alias_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _safe_id(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", value.strip())
    text = re.sub(r"_+", "_", text).strip("_-")
    return text[:64] or "catalog_step"


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _get(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "status": "catalog_workflow_error", "error": message}
