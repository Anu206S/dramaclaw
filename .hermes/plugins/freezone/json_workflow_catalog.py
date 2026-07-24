"""Resolve Workflow Skills and validate agent-authored dynamic workflow plans."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from novelvideo.freezone.agent_config_store import list_user_agent_config_items
except Exception:  # pragma: no cover - Hermes can run before app imports are available.
    list_user_agent_config_items = None

try:
    from novelvideo.freezone.workflow_plan import (
        ALLOWED_LINK_TYPES,
        ALLOWED_NODE_TYPES,
        validate_workflow_plan,
    )
except Exception:  # pragma: no cover - Hermes can run before app imports are available.
    validate_workflow_plan = None
    ALLOWED_LINK_TYPES = set()
    ALLOWED_NODE_TYPES = set()

PLAN_SCHEMA_VERSION = "freezone_workflow_plan.v1"
WORKFLOW_INTENT_SCHEMA_VERSION = "freezone_workflow_intent.v1"

_ROOT = Path(__file__).resolve().parents[3]
_CATALOG_ROOT = _ROOT / "src" / "novelvideo" / "freezone" / "agent_catalog" / "builtins"
_SKILLS_DIR = _CATALOG_ROOT / "skills"
_RECIPES_DIR = _CATALOG_ROOT / "recipes"
_PLUGIN_CATALOG_ROOT = Path(__file__).resolve().parent / "catalog"
_PLUGIN_SKILLS_DIR = _PLUGIN_CATALOG_ROOT / "skills"
_PLUGIN_RECIPES_DIR = _PLUGIN_CATALOG_ROOT / "recipes"

_NODE_TYPE_BY_STEP = {
    "textGeneration": "textAnnotationNode",
    "imageGeneration": "imageGenNode",
    "videoGeneration": "videoNode",
    "audioGeneration": "audioNode",
    "videoCompose": "videoComposeNode",
}

_NODE_TYPE_BY_OUTPUT_KIND = {
    "text": "textAnnotationNode",
    "image": "imageGenNode",
    "video": "videoNode",
    "audio": "audioNode",
}

_STAGE_BY_NODE_TYPE = {
    "textAnnotationNode": "story",
    "scriptNode": "story",
    "beatContextNode": "beat",
    "imageGenNode": "image",
    "videoNode": "video",
    "audioNode": "audio",
    "videoComposeNode": "compose",
}

_CAPABILITY_BY_NODE_TYPE = {
    "textAnnotationNode": "textGeneration",
    "scriptNode": "textGeneration",
    "beatContextNode": "textGeneration",
    "imageGenNode": "imageGeneration",
    "videoNode": "videoGeneration",
    "audioNode": "audioGeneration",
    "videoComposeNode": "videoCompose",
}

_OUTPUT_KIND_BY_CAPABILITY = {
    "textGeneration": "text",
    "imageGeneration": "image",
    "videoGeneration": "video",
    "audioGeneration": "audio",
}

# These built-in prompt Recipes consume the user goal or upstream structured text.
# Older catalog copies marked them as requiring binary media, which makes valid
# text-first blueprints impossible to compile.
_TEXT_FIRST_BUILTIN_RECIPE_IDS = {
    "digital-product-text-plan",
    "drama-character-extraction",
    "drama-character-turnaround",
    "drama-plot-outline",
    "drama-prop-extraction",
    "drama-prop-image",
    "drama-scene-extraction",
    "drama-scene-image",
    "drama-shot-group-detail",
    "drama-shot-planning",
    "ecommerce-text-plan",
    "keyframe-scene-script",
    "social-copywriting",
    "video-ad-brief",
    "video-ad-creative-outline",
    "video-creative-outline",
    "video-storyboard-grid",
    "video-storyboard-script",
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
        "id": "ecommerce-product",
        "name": "电商产品图",
        "description": "电商产品素材制作，包括详情页、广告图、场景图等图片生成流程。",
        "aliases": ["ecommerce_product", "ecommerce", "product_image"],
        "keywords": ["详情页", "广告图", "场景图", "产品图", "商品图", "电商"],
        "template_id": "ecommerce-scene-images",
        "template_name": "产品场景图",
        "operation_type": "ecommerce-scene-image",
        "goal": "并行生成产品场景图",
        "node_type": "imageGeneration",
        "generation_type": "image",
        "steps": [
            {
                "id": "scene-images",
                "step_number": 1,
                "goal_template": "并行生成 {count} 张产品场景图，每张展示产品在不同场景中的效果",
                "node_type": "imageGeneration",
                "action_key": "ecommerce-scene-image",
                "prompt_strategy": "llm_refine",
                "input_strategy": {"type": "user_assets", "filter": "image"},
                "aspect_ratio": "3:4",
                "multiplicity": {
                    "type": "fixed_count",
                    "default_count": 4,
                    "user_overridable": True,
                    "min": 2,
                    "max": 12,
                },
            }
        ],
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
                "id": "ad-brief",
                "step_number": 2,
                "goal_template": "生成视频广告脚本",
                "node_type": "textGeneration",
                "action_key": "video-ad-brief",
                "prompt_strategy": "llm_refine",
                "input_strategy": {"type": "previous_step", "step_id": "ad-outline"},
            },
            {
                "id": "storyboard-grid",
                "step_number": 3,
                "goal_template": "将广告脚本中的所有 Shot 合成为多宫格分镜图",
                "node_type": "imageGeneration",
                "action_key": "video-storyboard-grid",
                "prompt_strategy": "llm_refine",
                "input_strategy": {"type": "previous_step", "step_id": "ad-brief"},
                "model": "nano-banana-2",
            },
            {
                "id": "storyboard-upscaled-images",
                "step_number": 4,
                "goal_template": "基于多宫格分镜图逐镜放大生成高清广告分镜图（{count} 张）",
                "node_type": "imageGeneration",
                "action_key": "video-frame-extraction",
                "prompt_strategy": "llm_refine",
                "input_strategy": {"type": "previous_step", "step_id": "storyboard-grid"},
                "model": "nano-banana-2",
                "multiplicity": {
                    "type": "fixed_count",
                    "default_count": 6,
                    "user_overridable": True,
                    "min": 1,
                    "max": 24,
                },
            },
            {
                "id": "video-clips",
                "step_number": 5,
                "goal_template": "基于高清广告分镜图生成视频片段（{count} 段）",
                "node_type": "videoGeneration",
                "action_key": "video-clip-generation",
                "prompt_strategy": "llm_refine",
                "input_strategy": {"type": "previous_step", "step_id": "storyboard-upscaled-images"},
                "model": "omni-flash",
                "multiplicity": {
                    "type": "fixed_count",
                    "default_count": 6,
                    "user_overridable": True,
                    "min": 1,
                    "max": 24,
                },
            },
        ],
    },
)


def _workflow_input_values(args: dict[str, Any]) -> dict[str, Any]:
    value = args.get("inputs")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _parameter_option_values(parameter: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for option in parameter.get("options") or []:
        value = (
            _text(option.get("value")) if isinstance(option, dict) else _text(option)
        )
        if value:
            values.append(value)
    return values


def _is_missing_parameter_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def _allowed_inferred_option(parameter: dict[str, Any], value: str) -> str | None:
    return value if value in _parameter_option_values(parameter) else None


def _infer_parameter_value(parameter: dict[str, Any], user_goal: str) -> Any:
    """Extract only unambiguous structured values from the user's own words."""
    parameter_id = _text(parameter.get("id"))
    goal = user_goal.strip()
    lowered = goal.lower()
    if not parameter_id or not goal:
        return None

    options = [
        item for item in parameter.get("options") or [] if isinstance(item, dict)
    ]
    for option in options:
        value = _text(option.get("value"))
        label = _text(option.get("label"))
        if label and label.lower() in lowered:
            return value

    if parameter_id in {"aspect_ratio", "aspectRatio"}:
        ratio_match = re.search(r"(?<!\d)(\d{1,2}\s*:\s*\d{1,2})(?!\d)", goal)
        if ratio_match:
            ratio = re.sub(r"\s+", "", ratio_match.group(1))
            return _allowed_inferred_option(parameter, ratio)
        aliases = (
            (("竖屏", "竖版", "vertical", "portrait"), "9:16"),
            (("横屏", "横版", "landscape"), "16:9"),
            (("方形", "正方形", "square"), "1:1"),
            (("宽画幅", "超宽屏", "ultrawide"), "21:9"),
        )
        for keywords, value in aliases:
            if any(keyword in lowered for keyword in keywords):
                return _allowed_inferred_option(parameter, value)

    if parameter_id == "execution_mode":
        if any(
            keyword in lowered
            for keyword in (
                "只创建",
                "仅创建",
                "不执行",
                "不自动执行",
                "不要执行",
                "手动执行",
            )
        ):
            return _allowed_inferred_option(parameter, "manual")
        if any(
            keyword in lowered
            for keyword in ("自动执行", "自动运行", "直接执行", "直接生成")
        ):
            return _allowed_inferred_option(parameter, "auto")

    if parameter_id == "voice_mode":
        voice_aliases = (
            (("无对白", "不要对白", "纯音乐"), "no_dialogue"),
            (("旁白", "解说"), "voiceover"),
            (("对白", "对话"), "dialogue"),
        )
        for keywords, value in voice_aliases:
            if any(keyword in lowered for keyword in keywords):
                return _allowed_inferred_option(parameter, value)

    if parameter_id in {"duration", "duration_seconds"}:
        duration_match = re.search(
            r"(?<!\d)(\d{1,4})\s*(?:秒|s\b|sec(?:ond)?s?\b)", lowered
        )
        if duration_match:
            seconds = int(duration_match.group(1))
            exact = _allowed_inferred_option(parameter, str(seconds))
            if exact is not None:
                return exact
            for option in options:
                value = _text(option.get("value"))
                range_match = re.fullmatch(r"(\d+)[_-](\d+)", value)
                if range_match and int(range_match.group(1)) <= seconds <= int(
                    range_match.group(2)
                ):
                    return value

    if parameter_id in {
        "count",
        "item_count",
        "image_count",
        "shot_count",
        "beat_count",
    }:
        count_match = re.search(
            r"(?<!\d)(\d{1,2})\s*(?:张|幅|屏|个|段|条|镜头|镜)(?!\d)", goal
        )
        if count_match:
            return int(count_match.group(1))

    return None


def _infer_workflow_inputs(
    skill: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    user_goal = _workflow_goal_text(args)
    inferred: dict[str, Any] = {}
    for parameter in skill.get("input_parameters") or []:
        if not isinstance(parameter, dict):
            continue
        parameter_id = _text(parameter.get("id"))
        value = _infer_parameter_value(parameter, user_goal)
        if parameter_id and not _is_missing_parameter_value(value):
            inferred[parameter_id] = value
    return inferred


def _skill_input_contract(
    skill: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    raw_parameters = skill.get("input_parameters") or []
    parameters = [item for item in raw_parameters if isinstance(item, dict)]
    provided = _workflow_input_values(args)
    inferred = _infer_workflow_inputs(skill, args)
    effective = {**inferred, **provided}
    resolved: dict[str, Any] = {}
    missing_required: list[str] = []
    errors: list[dict[str, str]] = []
    fields: list[dict[str, Any]] = []

    for parameter in parameters:
        parameter_id = _text(parameter.get("id"))
        if not parameter_id:
            continue
        has_provided_value = parameter_id in provided
        has_inferred_value = parameter_id in inferred and not has_provided_value
        value = (
            effective.get(parameter_id)
            if parameter_id in effective
            else deepcopy(parameter.get("default"))
        )
        required = bool(parameter.get("required"))
        parameter_type = _text(parameter.get("type")) or "text"
        option_values = _parameter_option_values(parameter)
        if required and _is_missing_parameter_value(value):
            missing_required.append(parameter_id)
        elif not _is_missing_parameter_value(value):
            if parameter_type == "multi_select":
                if not isinstance(value, list):
                    errors.append(
                        {
                            "path": f"inputs.{parameter_id}",
                            "message": "must be an array",
                        }
                    )
                else:
                    invalid = [
                        str(item)
                        for item in value
                        if option_values and str(item) not in option_values
                    ]
                    if invalid:
                        errors.append(
                            {
                                "path": f"inputs.{parameter_id}",
                                "message": f"unsupported option: {invalid[0]}",
                            }
                        )
            elif option_values and str(value) not in option_values:
                errors.append(
                    {
                        "path": f"inputs.{parameter_id}",
                        "message": f"unsupported option: {value}",
                    }
                )
            resolved[parameter_id] = value
        fields.append(
            {
                "id": parameter_id,
                "label": _text(parameter.get("label")) or parameter_id,
                "type": parameter_type,
                "required": required,
                "default": deepcopy(parameter.get("default")),
                "options": deepcopy(parameter.get("options") or []),
                "value": deepcopy(value),
                "source": (
                    "user"
                    if has_provided_value
                    else "inferred" if has_inferred_value else "default"
                ),
            }
        )

    execution_mode = _text(resolved.get("execution_mode")) or "manual"
    return {
        "schema_version": "freezone_skill_inputs.v1",
        "fields": fields,
        "provided": provided,
        "inferred": inferred,
        "resolved": resolved,
        "missing_required": missing_required,
        "errors": errors,
        "ready_for_planning": not missing_required and not errors,
        "requires_confirmation": bool(fields),
        "execution_mode": execution_mode,
        "recommended_run_after_create": execution_mode == "auto",
        "execution_policy": deepcopy(skill.get("execution_policy") or {}),
    }


def get_workflow_skill(args: dict[str, Any]) -> dict[str, Any]:
    """Return one complete planning package for an explicitly selected Skill."""
    skill_id = _text(args.get("skill_id") or args.get("skillId") or args.get("id"))
    if not skill_id:
        return {
            "ok": False,
            "status": "skill_id_required",
            "error": "skill_id is required",
        }
    skill = _load_skill(skill_id)
    if skill is None or skill.get("_disabled") is True:
        return {
            "ok": False,
            "status": "workflow_skill_not_found",
            "error": f"workflow skill not found: {skill_id}",
            "available_skill_ids": sorted(
                _text(item.get("id"))
                for item in _load_skills()
                if _text(item.get("id")) and item.get("_disabled") is not True
            ),
        }

    recipes = [
        recipe
        for recipe in _load_agent_config_items("recipes", _RECIPES_DIR)
        if recipe.get("enabled") is not False and _text(recipe.get("id"))
    ]
    allowed_capabilities = _skill_capabilities(skill)
    candidate_recipes = _workflow_skill_recipe_candidates(
        skill,
        recipes,
        allowed_capabilities=allowed_capabilities,
    )
    referenced_recipe_ids = _skill_referenced_recipe_ids(skill)
    full_recipes = [
        _without_private_fields(recipe)
        for recipe in candidate_recipes
        if _recipe_matches_references(recipe, referenced_recipe_ids)
    ]
    recipe_summaries = [
        _recipe_planning_summary(recipe) for recipe in candidate_recipes
    ]
    recipes_by_output_kind: dict[str, list[str]] = {}
    source_anchor_recipe_ids: dict[str, list[str]] = {}
    for recipe in recipe_summaries:
        output_kind = _text(recipe.get("output_kind"))
        recipe_id = _text(recipe.get("id"))
        if not output_kind or not recipe_id:
            continue
        recipes_by_output_kind.setdefault(output_kind, []).append(recipe_id)
        if not recipe.get("requires_source_media"):
            source_anchor_recipe_ids.setdefault(output_kind, []).append(recipe_id)
    input_contract = _skill_input_contract(skill, args)
    compact = bool(args.get("compact"))
    planning_skill = _without_private_fields(skill)
    if isinstance(planning_skill, dict):
        planning_skill.pop("workflow_templates", None)
        planning_skill.pop("templates", None)
    return {
        "ok": True,
        "schema_version": "freezone_workflow_skill_package.v1",
        "skill_id": _text(skill.get("id")),
        "user_goal": _workflow_goal_text(args),
        "source": _catalog_source(skill),
        "skill": planning_skill,
        "recipes": [] if compact else full_recipes,
        "recipe_definitions_omitted": compact,
        "available_recipes": recipe_summaries,
        "capabilities": [
            {
                "id": capability,
                "output_kind": _OUTPUT_KIND_BY_CAPABILITY.get(
                    capability, "composition"
                ),
                "node_type": next(
                    (
                        node_type
                        for node_type, mapped_capability in _CAPABILITY_BY_NODE_TYPE.items()
                        if mapped_capability == capability
                    ),
                    "",
                ),
            }
            for capability in allowed_capabilities
        ],
        "allowed_node_types": sorted(
            node_type
            for node_type, capability in _CAPABILITY_BY_NODE_TYPE.items()
            if capability in allowed_capabilities
        ),
        "allowed_link_types": sorted(ALLOWED_LINK_TYPES),
        "input_contract": input_contract,
        "planning_contract": {
            "schema_version": PLAN_SCHEMA_VERSION,
            "workflow_type_prefix": "dynamic.",
            "mode": "dynamic_only",
            "requires_agent_authored_topology": True,
            "fixed_templates_enabled": False,
            "requires_explicit_skill_id": True,
            "requires_explicit_recipe_id": True,
            "strict_validation": True,
            "plan_inputs_field": "inputs",
            "max_nodes": 200,
            "max_edges": 400,
            "missing_source_media": {
                "strategy": "generate_anchor_then_continue",
                "anchor_recipe_requires_source_media": False,
                "dependency_link_type": "media_input_for",
                "source_anchor_recipe_ids": source_anchor_recipe_ids,
            },
            "recipe_ids_by_output_kind": recipes_by_output_kind,
            "recipe_selection_rule": (
                "Recipe output_kind must match the node type. For a generated source-media "
                "anchor, choose a same-output Recipe listed in source_anchor_recipe_ids; "
                "never copy a downstream text Recipe onto an image anchor."
            ),
        },
        "message": (
            "已加载完整 Workflow Skill 包，可直接规划 freezone_workflow_plan.v1。"
            if input_contract["ready_for_planning"]
            else "已加载 Workflow Skill，但必须先补全或修正 input_contract。"
        ),
    }


def compile_workflow_intent(intent: Any) -> dict[str, Any]:
    """Compile a compact Agent decision into a complete, validated dynamic plan."""
    if not isinstance(intent, dict):
        return _intent_error("intent must be an object", path="intent")
    schema_version = _text(intent.get("schema_version"))
    if schema_version and schema_version != WORKFLOW_INTENT_SCHEMA_VERSION:
        return _intent_error(
            f"schema_version must equal {WORKFLOW_INTENT_SCHEMA_VERSION}",
            path="schema_version",
        )
    skill_id = _text(intent.get("skill_id") or intent.get("skillId"))
    if not skill_id:
        return _intent_error("skill_id is required", path="skill_id")
    skill = _load_skill(skill_id)
    if skill is None or skill.get("_disabled") is True:
        return _intent_error(f"workflow skill not found: {skill_id}", path="skill_id")

    user_goal = _workflow_goal_text(intent)
    if not user_goal:
        return _intent_error("user_goal is required", path="user_goal")
    input_contract = _skill_input_contract(skill, intent)
    if input_contract["errors"] or input_contract["missing_required"]:
        errors = list(input_contract["errors"])
        errors.extend(
            {
                "path": f"inputs.{parameter_id}",
                "message": "required Skill input is missing",
            }
            for parameter_id in input_contract["missing_required"]
        )
        return {
            "ok": False,
            "status": "invalid_workflow_intent",
            "error": errors[0]["message"],
            "errors": errors,
        }

    template = _select_intent_template(skill, intent)
    if template is None:
        return _intent_error(
            f"skill {skill_id} does not define a workflow blueprint",
            path="skill_id",
        )
    recipes = _intent_recipe_index()
    items = _intent_items(intent)
    excluded_steps = {
        _safe_id(_text(item))
        for item in intent.get("exclude_steps", [])
        if _text(item)
    }
    include_audio = _intent_bool(intent, "include_audio", True)
    include_compose = _intent_bool(intent, "include_compose", True)
    resolved_inputs = input_contract["resolved"]
    title = _text(intent.get("title")) or _catalog_label(skill)
    template_id = _text(template.get("id"))

    nodes: list[dict[str, Any]] = [
        {
            "id": "workflow_input",
            "node_type": "textAnnotationNode",
            "name": "用户需求 / 输入素材",
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
    node_types = {"workflow_input": "textAnnotationNode"}
    node_recipes: dict[str, dict[str, Any] | None] = {"workflow_input": None}
    edges: list[dict[str, str]] = []
    expanded_steps: dict[str, list[str]] = {}
    previous_step_ids: list[str] = []
    step_counts: dict[str, int] = {}

    raw_anchor = intent.get("source_anchor", intent.get("sourceAnchor"))
    anchor_explicit = raw_anchor is not None and raw_anchor is not False
    anchor_disabled = raw_anchor is False
    anchor = _intent_source_anchor(intent, skill_id, user_goal, recipes)
    if anchor is not None:
        nodes.append(anchor)
        node_types[anchor["id"]] = anchor["node_type"]
        node_recipes[anchor["id"]] = recipes.get("general-image")

    raw_steps = [step for step in template.get("steps") or [] if isinstance(step, dict)]
    raw_steps.sort(
        key=lambda item: (
            _int(_get(item, "stepNumber", "step_number"), 999),
            _text(item.get("id")),
        )
    )
    for step in raw_steps:
        step_id = _safe_id(_text(step.get("id")) or f"step_{len(previous_step_ids) + 1}")
        if step_id in excluded_steps:
            continue
        node_type = _intent_step_node_type(step)
        if node_type == "audioNode" and not include_audio:
            continue
        recipe = _intent_step_recipe(step, node_type, recipes)
        if node_type != "videoComposeNode" and recipe is None:
            return _intent_error(
                f"no compatible Recipe found for step {step_id}",
                path=f"steps.{step_id}",
            )
        count, step_items = _intent_step_instances(
            step,
            step_id=step_id,
            intent=intent,
            items=items,
            expanded_steps=expanded_steps,
            previous_step_ids=previous_step_ids,
        )
        instance_ids = (
            [step_id]
            if count == 1
            else [f"{step_id}_{index + 1}" for index in range(count)]
        )
        expanded_steps[step_id] = instance_ids
        step_counts[step_id] = count
        for index, instance_id in enumerate(instance_ids):
            item = step_items[index] if index < len(step_items) else {}
            node = _intent_step_node(
                skill=skill,
                template=template,
                step=step,
                recipe=recipe,
                node_type=node_type,
                instance_id=instance_id,
                instance_index=index,
                instance_count=count,
                item=item,
                user_goal=user_goal,
                resolved_inputs=resolved_inputs,
            )
            nodes.append(node)
            node_types[instance_id] = node_type
            node_recipes[instance_id] = recipe
        source_step_ids = _intent_dependency_steps(step, previous_step_ids)
        for source_step_id in source_step_ids:
            source_ids = (
                ["workflow_input"]
                if source_step_id == "workflow_input"
                else expanded_steps.get(source_step_id, [])
            )
            edges.extend(
                _intent_dependency_edges(
                    source_ids,
                    instance_ids,
                    node_types=node_types,
                )
            )
        previous_step_ids.append(step_id)

    unsatisfied_source_nodes = _intent_unsatisfied_source_nodes(
        node_types=node_types,
        node_recipes=node_recipes,
        edges=edges,
    )
    if unsatisfied_source_nodes and anchor is None and not anchor_disabled:
        anchor = _intent_source_anchor(
            {"source_anchor": {}},
            skill_id,
            user_goal,
            recipes,
        )
        if anchor is not None:
            nodes.insert(1, anchor)
            node_types[anchor["id"]] = anchor["node_type"]
            node_recipes[anchor["id"]] = recipes.get("general-image")
    if anchor is not None:
        anchor_targets = (
            [
                _text(node.get("id"))
                for node in nodes
                if node.get("node_type") == "imageGenNode"
                and _text(node.get("id")) != anchor["id"]
            ]
            if anchor_explicit
            else unsatisfied_source_nodes
        )
        for node_id in anchor_targets:
            edges.append(
                {
                    "source": anchor["id"],
                    "target": node_id,
                    "link_type": "media_input_for",
                }
            )

    if include_compose:
        compose_sources = [
            node_id
            for node_id, node_type in node_types.items()
            if node_type in {"videoNode", "audioNode"}
        ]
        has_video_source = any(
            node_types.get(source_id) == "videoNode" for source_id in compose_sources
        )
        if compose_sources and has_video_source:
            compose_id = "final_compose"
            nodes.append(
                {
                    "id": compose_id,
                    "node_type": "videoComposeNode",
                    "name": "成片合成",
                    "description": "汇总视频片段、配乐和旁白，进入时间线完成最终编排。",
                    "stage": "compose",
                    "data": {
                        "displayName": "成片合成",
                        "title": "成片合成",
                        "content": "汇总视频片段、配乐和旁白，进入时间线完成最终编排。",
                        "prompt": "汇总视频片段、配乐和旁白，进入时间线完成最终编排。",
                        "workflowCatalog": {
                            "skillId": skill_id,
                            "templateId": template_id,
                            "stepId": compose_id,
                            "promptBuilder": {"userGoal": user_goal},
                        },
                    },
                }
            )
            node_types[compose_id] = "videoComposeNode"
            node_recipes[compose_id] = None
            edges.extend(
                {
                    "source": source_id,
                    "target": compose_id,
                    "link_type": "composition_input_for",
                }
                for source_id in compose_sources
            )

    edges = _dedupe_intent_edges(edges)
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "workflow_type": f"dynamic.{skill_id}",
        "mode": "tool_compiled_dynamic",
        "skill": {"id": skill_id, "version": skill.get("version")},
        "summary": _text(intent.get("summary")) or user_goal,
        "source_context": {
            "user_goal": user_goal,
            "canvas_context": [],
            "input_assets": [],
        },
        "analysis": {"entities": [], "production_units": [], "risks": []},
        "phases": [
            _text(_get(step, "goalTemplate", "goal_template"))
            for step in raw_steps
            if _text(_get(step, "goalTemplate", "goal_template"))
        ],
        "assumptions": list(intent.get("assumptions") or []),
        "missing_inputs": [],
        "expansion_rules": {"step_counts": step_counts},
        "inputs": resolved_inputs,
        "nodes": nodes,
        "edges": edges,
        "layout": {
            "direction": "left_to_right",
            "groups": [
                {
                    "label": title,
                    "node_ids": [_text(node.get("id")) for node in nodes],
                }
            ],
        },
        "execution_policy": {
            "requires_user_confirmation": True,
            "auto_create_nodes": False,
            "auto_generate_content": False,
            "handoff_tool": "freezone_create_workflow_from_intent",
        },
    }
    validated = validate_agent_workflow_plan(plan)
    if not validated.get("ok"):
        return {
            **validated,
            "status": "compiled_workflow_plan_invalid",
            "compiled_plan": plan,
        }
    return {
        "ok": True,
        "status": "workflow_intent_compiled",
        "schema_version": WORKFLOW_INTENT_SCHEMA_VERSION,
        "skill_id": skill_id,
        "template_id": template_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "step_counts": step_counts,
        "plan": plan,
    }


def _intent_error(message: str, *, path: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "invalid_workflow_intent",
        "error": message,
        "errors": [{"path": path, "message": message}],
    }


def _intent_bool(intent: dict[str, Any], key: str, default: bool) -> bool:
    value = intent.get(key)
    if value is None:
        return default
    return value if isinstance(value, bool) else default


def _select_intent_template(
    skill: dict[str, Any], intent: dict[str, Any]
) -> dict[str, Any] | None:
    templates = _templates(skill)
    requested = _text(intent.get("template_id") or intent.get("templateId"))
    if requested:
        normalized = _alias_key(requested)
        return next(
            (
                template
                for template in templates
                if _alias_key(_text(template.get("id"))) == normalized
            ),
            None,
        )
    has_source_media = bool(intent.get("has_source_media") or intent.get("source_assets"))
    if has_source_media:
        for template in templates:
            condition = template.get("condition")
            if isinstance(condition, dict) and _get(
                condition, "hasInputTypes", "has_input_types"
            ):
                return template
    for template in templates:
        condition = template.get("condition")
        if isinstance(condition, dict) and _get(condition, "textOnly", "text_only"):
            return template
    return templates[0] if templates else None


def _intent_recipe_index() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for recipe in _load_agent_config_items("recipes", _RECIPES_DIR):
        if recipe.get("enabled") is False:
            continue
        recipe_id = _text(recipe.get("id"))
        if recipe_id:
            result[recipe_id] = recipe
        for field in ("actionKeys", "action_keys", "operationTypes", "operation_types"):
            for action_key in recipe.get(field) or []:
                if _text(action_key):
                    result.setdefault(_text(action_key), recipe)
    return result


def _intent_items(intent: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = intent.get("items") or intent.get("shots") or []
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for raw_item in raw_items[:24]:
        if isinstance(raw_item, str) and raw_item.strip():
            items.append({"title": raw_item.strip(), "prompt": raw_item.strip()})
        elif isinstance(raw_item, dict):
            title = _text(raw_item.get("title") or raw_item.get("name"))
            prompt = _text(
                raw_item.get("prompt")
                or raw_item.get("description")
                or raw_item.get("goal")
            )
            narration = _text(
                raw_item.get("narration")
                or raw_item.get("voiceover")
                or raw_item.get("dialogue")
                or raw_item.get("speech_text")
                or raw_item.get("speechText")
            )
            step_id = _text(raw_item.get("step_id") or raw_item.get("stepId"))
            if title or prompt or narration:
                items.append(
                    {
                        "title": title or prompt or narration,
                        "prompt": prompt or title or narration,
                        **({"narration": narration} if narration else {}),
                        **({"step_id": _safe_id(step_id)} if step_id else {}),
                    }
                )
    return items


def _intent_source_anchor(
    intent: dict[str, Any],
    skill_id: str,
    user_goal: str,
    recipes: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    raw_anchor = (
        intent.get("source_anchor")
        if "source_anchor" in intent
        else intent.get("sourceAnchor")
    )
    if raw_anchor is True:
        raw_anchor = {}
    if not isinstance(raw_anchor, dict) or raw_anchor.get("enabled") is False:
        return None
    recipe = recipes.get("general-image")
    if recipe is None:
        return None
    title = _text(raw_anchor.get("title")) or "产品基准图"
    prompt = _text(raw_anchor.get("prompt") or raw_anchor.get("description"))
    prompt = prompt or f"根据用户需求生成清晰、完整、可复用的视觉基准图：{user_goal}"
    return {
        "id": "source_anchor",
        "node_type": "imageGenNode",
        "name": title,
        "description": prompt,
        "stage": "asset",
        "data": {
            "displayName": title,
            "title": title,
            "content": prompt,
            "prompt": prompt,
            "description": prompt,
            "workflowCatalog": {
                "skillId": skill_id,
                "stepId": "source_anchor",
                "recipeId": _text(recipe.get("id")),
                "recipeVersion": recipe.get("version"),
                "promptBuilder": {
                    "userGoal": user_goal,
                    "recipeId": _text(recipe.get("id")),
                },
            },
        },
    }


def _intent_step_node_type(step: dict[str, Any]) -> str:
    return _NODE_TYPE_BY_STEP.get(
        _text(_get(step, "nodeType", "node_type")),
        "textAnnotationNode",
    )


def _intent_step_recipe(
    step: dict[str, Any],
    node_type: str,
    recipes: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    reference = _text(
        _get(step, "recipeId", "recipe_id")
        or _get(step, "operationType", "operation_type", "actionKey", "action_key")
    )
    recipe = recipes.get(reference) if reference else None
    capability = _CAPABILITY_BY_NODE_TYPE.get(node_type, "")
    output_kind = _OUTPUT_KIND_BY_CAPABILITY.get(capability, "")
    recipe_output_kind = _text(
        recipe.get("output_kind")
        or recipe.get("generationType")
        or recipe.get("generation_type")
    ) if recipe else ""
    if recipe is None or (output_kind and recipe_output_kind != output_kind):
        recipe = recipes.get(f"general-{output_kind}") if output_kind else None
    return recipe


def _intent_unsatisfied_source_nodes(
    *,
    node_types: dict[str, str],
    node_recipes: dict[str, dict[str, Any] | None],
    edges: list[dict[str, str]],
) -> list[str]:
    satisfied = {
        edge["target"]
        for edge in edges
        if edge.get("link_type") in {"media_input_for", "derived_from"}
        and node_types.get(edge.get("source", ""))
        in {"imageGenNode", "videoNode", "audioNode"}
    }
    return [
        node_id
        for node_id, recipe in node_recipes.items()
        if recipe
        and bool(recipe.get("requires_source_media") or recipe.get("requiresSourceMedia"))
        and node_id not in satisfied
    ]


def _intent_step_instances(
    step: dict[str, Any],
    *,
    step_id: str,
    intent: dict[str, Any],
    items: list[dict[str, Any]],
    expanded_steps: dict[str, list[str]],
    previous_step_ids: list[str],
) -> tuple[int, list[dict[str, Any]]]:
    explicit_items = [item for item in items if item.get("step_id") == step_id]
    generic_items = [item for item in items if not item.get("step_id")]
    multiplicity = step.get("multiplicity", "single")
    if multiplicity is None or multiplicity == "single":
        return 1, explicit_items[:1]
    step_items = explicit_items or generic_items
    if multiplicity == "per_plan_item":
        return max(1, len(step_items)), step_items
    if multiplicity == "per_input":
        sources = _intent_dependency_steps(step, previous_step_ids)
        count = sum(len(expanded_steps.get(source, [])) for source in sources)
        return max(1, count), step_items
    if not isinstance(multiplicity, dict):
        return 1, step_items[:1]
    default_count = max(1, _int(_get(multiplicity, "defaultCount", "default_count"), 1))
    step_counts = intent.get("step_counts") if isinstance(intent.get("step_counts"), dict) else {}
    requested = _int(step_counts.get(step_id), 0)
    if not requested:
        requested = len(step_items)
    if not requested:
        requested = _intent_requested_count(intent)
    if not requested and _get(multiplicity, "userOverridable", "user_overridable"):
        sources = _intent_dependency_steps(step, previous_step_ids)
        if len(sources) == 1:
            requested = len(expanded_steps.get(sources[0], []))
    count = requested or default_count
    minimum = max(1, _int(multiplicity.get("min"), 1))
    maximum = max(minimum, _int(multiplicity.get("max"), count))
    return max(minimum, min(maximum, count)), step_items


def _intent_requested_count(intent: dict[str, Any]) -> int:
    inputs = intent.get("inputs") if isinstance(intent.get("inputs"), dict) else {}
    for source in (intent, inputs):
        for key in ("count", "shot_count", "image_count", "beat_count", "item_count"):
            value = _int(source.get(key), 0)
            if value > 0:
                return value
    return 0


def _intent_dependency_steps(
    step: dict[str, Any], previous_step_ids: list[str]
) -> list[str]:
    strategy = _get(step, "inputStrategy", "input_strategy")
    if not isinstance(strategy, dict):
        return previous_step_ids[-1:] or ["workflow_input"]
    step_id = _text(_get(strategy, "stepId", "step_id"))
    if step_id:
        return [_safe_id(step_id)]
    step_ids = _get(strategy, "stepIds", "step_ids")
    if isinstance(step_ids, list):
        normalized = [_safe_id(_text(item)) for item in step_ids if _text(item)]
        if normalized:
            return normalized
    strategy_type = _text(strategy.get("type"))
    if strategy_type == "none":
        return []
    if strategy_type == "user_assets":
        return ["workflow_input"]
    if strategy_type in {"previous_steps", "previous_steps_and_user_assets"}:
        return previous_step_ids or ["workflow_input"]
    return previous_step_ids[-1:] or ["workflow_input"]


def _intent_dependency_edges(
    source_ids: list[str],
    target_ids: list[str],
    *,
    node_types: dict[str, str],
) -> list[dict[str, str]]:
    pairs = (
        list(zip(source_ids, target_ids, strict=True))
        if len(source_ids) == len(target_ids) and len(source_ids) > 1
        else [(source_id, target_id) for source_id in source_ids for target_id in target_ids]
    )
    return [
        {
            "source": source_id,
            "target": target_id,
            "link_type": _intent_link_type(
                node_types.get(source_id, ""),
                node_types.get(target_id, ""),
            ),
        }
        for source_id, target_id in pairs
    ]


def _intent_link_type(source_type: str, target_type: str) -> str:
    if target_type == "videoComposeNode":
        return "composition_input_for"
    if source_type in {"textAnnotationNode", "scriptNode", "beatContextNode"}:
        if target_type in {"textAnnotationNode", "scriptNode", "beatContextNode"}:
            return "context_for"
        return "prompt_for"
    if source_type in {"imageGenNode", "videoNode", "audioNode"}:
        return "media_input_for"
    return "context_for"


def _intent_step_node(
    *,
    skill: dict[str, Any],
    template: dict[str, Any],
    step: dict[str, Any],
    recipe: dict[str, Any] | None,
    node_type: str,
    instance_id: str,
    instance_index: int,
    instance_count: int,
    item: dict[str, Any],
    user_goal: str,
    resolved_inputs: dict[str, Any],
) -> dict[str, Any]:
    base_label = _text(_get(step, "goalTemplate", "goal_template")) or _text(step.get("id"))
    base_label = base_label.replace("{count}", str(instance_count))
    model = _text(step.get("model"))
    item_title = _text(item.get("title"))
    if instance_count > 1:
        kind = {"imageGenNode": "高清分镜", "videoNode": "视频"}.get(node_type, "节点")
        label = f"Shot {instance_index + 1} {kind}"
        if item_title:
            label = f"{label} · {item_title}"
    else:
        label = item_title or base_label
    label = label[:64]
    item_prompt = _text(item.get("prompt"))
    if node_type == "audioNode" and model in {
        "edge-tts",
        "LingShan-TTS-2",
        "qwen3-tts-flash",
    }:
        item_prompt = _text(item.get("narration")) or item_prompt
    prompt = item_prompt or base_label
    timeline_role = _text(_get(step, "timelineRole", "timeline_role"))
    data: dict[str, Any] = {
        "displayName": label,
        "title": label,
        "content": prompt,
        "prompt": prompt,
        "description": prompt,
        "workflowCatalog": {
            "skillId": _text(skill.get("id")),
            "templateId": _text(template.get("id")),
            "stepId": _safe_id(_text(step.get("id"))),
            "stepInstance": instance_index + 1,
            "stepInstanceCount": instance_count,
            **({"timelineRole": timeline_role} if timeline_role else {}),
            "operationType": _text(
                _get(step, "operationType", "operation_type", "actionKey", "action_key")
            ),
            "recipeId": _text(recipe.get("id") if recipe else ""),
            "recipeVersion": recipe.get("version") if recipe else None,
            "promptStrategy": _text(_get(step, "promptStrategy", "prompt_strategy")),
            "inputStrategy": _get(step, "inputStrategy", "input_strategy") or {},
            "promptBuilder": {
                "userGoal": user_goal,
                "goalTemplate": base_label,
                "recipeId": _text(recipe.get("id") if recipe else ""),
                **({"planItem": item} if item else {}),
            },
        },
    }
    if model:
        data["model"] = model
    aspect_ratio = _text(resolved_inputs.get("aspect_ratio")) or _text(
        _get(step, "aspectRatio", "aspect_ratio")
    )
    if aspect_ratio and node_type in {"imageGenNode", "videoNode"}:
        data["aspectRatio"] = aspect_ratio
    if node_type == "audioNode":
        data["text"] = prompt
        if model == "suno_music":
            data["audioKind"] = "music"
            data["makeInstrumental"] = True
            data["sunoGptDescriptionPrompt"] = prompt
        elif model in {"edge-tts", "LingShan-TTS-2", "qwen3-tts-flash"}:
            data["audioKind"] = "speech"
            data["speechMode"] = "preset"
            data["presetModel"] = (
                "edge-tts" if model in {"LingShan-TTS-2", "qwen3-tts-flash"} else model
            )
            data["presetVoice"] = "Serena"
            data["voice"] = "Serena"
            data["languageType"] = "Chinese"
    return {
        "id": instance_id,
        "node_type": node_type,
        "name": label,
        "description": prompt,
        "stage": _STAGE_BY_NODE_TYPE.get(node_type, "story"),
        "data": data,
    }


def _dedupe_intent_edges(edges: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (edge["source"], edge["target"], edge["link_type"])
        if key not in seen:
            result.append(edge)
            seen.add(key)
    return result


def validate_agent_workflow_plan(plan: Any) -> dict[str, Any]:
    """Strictly validate an agent-authored plan against the live catalog."""
    if validate_workflow_plan is None:
        return {
            "ok": False,
            "status": "workflow_plan_validation_unavailable",
            "error": "workflow plan validation is unavailable",
        }
    skills = {
        _text(skill.get("id")): skill
        for skill in _load_skills()
        if _text(skill.get("id")) and skill.get("_disabled") is not True
    }
    recipes = {
        _text(recipe.get("id")): recipe
        for recipe in _load_agent_config_items("recipes", _RECIPES_DIR)
        if _text(recipe.get("id")) and recipe.get("enabled") is not False
    }
    validated = validate_workflow_plan(
        plan,
        skills_by_id=skills,
        recipes_by_id=recipes,
    )
    if not validated.get("ok"):
        return validated
    skill_id = _text(validated.get("skill_id"))
    allowed_capabilities = _skill_capabilities(skills[skill_id])
    allowed_node_types = {
        node_type
        for node_type, capability in _CAPABILITY_BY_NODE_TYPE.items()
        if capability in allowed_capabilities
    }
    allowed_node_types.add("textAnnotationNode")
    if "videoNode" in allowed_node_types:
        allowed_node_types.add("videoComposeNode")
    allowed_recipe_ids = {
        _text(recipe.get("id"))
        for recipe in _workflow_skill_recipe_candidates(
            skills[skill_id], list(recipes.values())
        )
    }
    errors: list[dict[str, str]] = []
    plan_inputs = plan.get("inputs", {})
    if not isinstance(plan_inputs, dict):
        errors.append({"path": "inputs", "message": "must be an object"})
        plan_inputs = {}
    input_contract = _skill_input_contract(skills[skill_id], {"inputs": plan_inputs})
    errors.extend(input_contract["errors"])
    errors.extend(
        {
            "path": f"inputs.{parameter_id}",
            "message": "required Skill input is missing",
        }
        for parameter_id in input_contract["missing_required"]
    )
    for index, node in enumerate(plan.get("nodes") or []):
        node_type = _text(node.get("node_type")) if isinstance(node, dict) else ""
        if node_type not in allowed_node_types:
            errors.append(
                {
                    "path": f"nodes[{index}].node_type",
                    "message": f"node type {node_type} is not allowed by skill {skill_id}",
                }
            )
        data = node.get("data") if isinstance(node, dict) else None
        catalog = data.get("workflowCatalog") if isinstance(data, dict) else None
        recipe_id = _text(catalog.get("recipeId")) if isinstance(catalog, dict) else ""
        stage = _text(node.get("stage")) if isinstance(node, dict) else ""
        requires_recipe = node_type in {
            "imageGenNode",
            "videoNode",
            "audioNode",
            "scriptNode",
            "beatContextNode",
        } or (
            node_type == "textAnnotationNode"
            and stage not in {"input", "resource", "asset"}
        )
        if requires_recipe and not recipe_id:
            errors.append(
                {
                    "path": f"nodes[{index}].data.workflowCatalog.recipeId",
                    "message": f"executable node {node.get('id')} requires an explicit recipeId",
                }
            )
        if recipe_id and recipe_id not in allowed_recipe_ids:
            errors.append(
                {
                    "path": f"nodes[{index}].data.workflowCatalog.recipeId",
                    "message": f"recipe {recipe_id} is not allowed by skill {skill_id}",
                }
            )
    if errors:
        return {
            "ok": False,
            "status": "invalid_dynamic_workflow_plan",
            "error": errors[0]["message"],
            "errors": errors,
        }
    validated["resolved_inputs"] = input_contract["resolved"]
    validated["execution_mode"] = input_contract["execution_mode"]
    validated["recommended_run_after_create"] = input_contract[
        "recommended_run_after_create"
    ]
    return validated


def _load_skill(skill_id: str) -> dict[str, Any] | None:
    wanted = _alias_key(skill_id)
    for skill in _load_skills():
        if _alias_key(_text(skill.get("id"))) == wanted:
            return skill
    return None


def _load_skills() -> list[dict[str, Any]]:
    return _load_agent_config_items("skills", _SKILLS_DIR, _PLUGIN_SKILLS_DIR)


def _skill_capabilities(skill: dict[str, Any]) -> list[str]:
    capabilities: list[str] = []
    triggers = skill.get("triggers") if isinstance(skill.get("triggers"), dict) else {}
    raw_scopes = triggers.get("node_scopes") or triggers.get("nodeScopes") or []
    for scope in raw_scopes if isinstance(raw_scopes, list) else []:
        normalized = _text(scope)
        aliases = {
            "text": "textGeneration",
            "image": "imageGeneration",
            "video": "videoGeneration",
            "audio": "audioGeneration",
            "compose": "videoCompose",
        }
        capability = aliases.get(normalized, normalized)
        if capability in _OUTPUT_KIND_BY_CAPABILITY or capability == "videoCompose":
            if capability not in capabilities:
                capabilities.append(capability)
    for template in _templates(skill):
        for step in template.get("steps") or []:
            if not isinstance(step, dict):
                continue
            capability = _text(_get(step, "nodeType", "node_type"))
            if capability in _NODE_TYPE_BY_STEP and capability not in capabilities:
                capabilities.append(capability)
    if not capabilities:
        capabilities = list(_OUTPUT_KIND_BY_CAPABILITY)
    return capabilities


def _skill_referenced_recipe_ids(skill: dict[str, Any]) -> set[str]:
    references = {
        _text(item)
        for field in (
            "recipe_ids",
            "recipeIds",
            "allowed_recipe_ids",
            "allowedRecipeIds",
        )
        for item in (skill.get(field) if isinstance(skill.get(field), list) else [])
        if _text(item)
    }
    for template in _templates(skill):
        for step in template.get("steps") or []:
            if not isinstance(step, dict):
                continue
            reference = _text(
                _get(
                    step,
                    "recipeId",
                    "recipe_id",
                    "operationType",
                    "operation_type",
                    "actionKey",
                    "action_key",
                )
            )
            if reference:
                references.add(reference)
    return references


def _workflow_skill_recipe_candidates(
    skill: dict[str, Any],
    recipes: list[dict[str, Any]],
    *,
    allowed_capabilities: list[str] | None = None,
) -> list[dict[str, Any]]:
    capabilities = allowed_capabilities or _skill_capabilities(skill)
    output_kinds = {
        _OUTPUT_KIND_BY_CAPABILITY[capability]
        for capability in capabilities
        if capability in _OUTPUT_KIND_BY_CAPABILITY
    }
    references = _skill_referenced_recipe_ids(skill)
    general_recipe_ids = {
        f"general-{output_kind}"
        for output_kind in output_kinds
    }
    candidates: list[dict[str, Any]] = []
    for recipe in recipes:
        recipe_id = _text(recipe.get("id"))
        action_keys = {
            _text(item)
            for field in (
                "actionKeys",
                "action_keys",
                "operationTypes",
                "operation_types",
            )
            for item in (
                recipe.get(field) if isinstance(recipe.get(field), list) else []
            )
            if _text(item)
        }
        output_kind = _text(
            recipe.get("output_kind")
            or recipe.get("generationType")
            or recipe.get("generation_type")
        )
        explicitly_referenced = recipe_id in references or bool(
            action_keys & references
        )
        if (
            explicitly_referenced
            or recipe_id in general_recipe_ids
            or (not references and (not output_kinds or output_kind in output_kinds))
        ):
            candidates.append(recipe)
    candidates.sort(key=lambda item: _text(item.get("id")))
    return candidates


def _recipe_matches_references(recipe: dict[str, Any], references: set[str]) -> bool:
    if _text(recipe.get("id")) in references:
        return True
    return any(
        _text(item) in references
        for field in ("actionKeys", "action_keys", "operationTypes", "operation_types")
        for item in (recipe.get(field) if isinstance(recipe.get(field), list) else [])
    )


def _recipe_planning_summary(recipe: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(recipe.get("id")),
        "name": _text(recipe.get("name") or recipe.get("label")),
        "version": recipe.get("version"),
        "output_kind": _text(
            recipe.get("output_kind")
            or recipe.get("generationType")
            or recipe.get("generation_type")
        ),
        "action_keys": [
            _text(item)
            for field in (
                "actionKeys",
                "action_keys",
                "operationTypes",
                "operation_types",
            )
            for item in (
                recipe.get(field) if isinstance(recipe.get(field), list) else []
            )
            if _text(item)
        ],
        "planning_prompt": _text(
            recipe.get("planning_prompt") or recipe.get("planningPrompt")
        ),
        "result_summary": _text(
            recipe.get("result_summary") or recipe.get("resultSummary")
        ),
        "requires_source_media": bool(
            recipe.get("requires_source_media") or recipe.get("requiresSourceMedia")
        ),
    }


def _without_private_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_private_fields(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [_without_private_fields(item) for item in value]
    return value


def _load_agent_config_items(
    kind: str, fallback_dir: Path, project_dir: Path | None = None
) -> list[dict[str, Any]]:
    if project_dir is None:
        project_dir = _PLUGIN_RECIPES_DIR if kind == "recipes" else _PLUGIN_SKILLS_DIR
    fallback_items = _load_json_dir(fallback_dir)
    if not fallback_items:
        fallback_items = _fallback_agent_config_items(kind)
    if project_dir is not None:
        project_items = [
            {**item, "_catalog_source": "builtin"}
            for item in _load_json_dir(project_dir)
        ]
        if project_items:
            fallback_items = _merge_agent_config_items(fallback_items, project_items)
    if list_user_agent_config_items is not None:
        username = _catalog_username()
        if username:
            try:
                loaded_items = list_user_agent_config_items(username, kind)
                if loaded_items:
                    return _normalize_agent_config_items(
                        kind,
                        _merge_agent_config_items(fallback_items, loaded_items),
                    )
            except Exception:
                pass
    return _normalize_agent_config_items(kind, fallback_items)


def _normalize_agent_config_items(
    kind: str, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if kind != "recipes":
        return items
    normalized: list[dict[str, Any]] = []
    for item in items:
        if _text(item.get("id")) in _TEXT_FIRST_BUILTIN_RECIPE_IDS:
            normalized.append({**item, "requires_source_media": False})
        else:
            normalized.append(item)
    return normalized


def _merge_agent_config_items(
    builtin_items: list[dict[str, Any]],
    loaded_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge code fallback builtins with user/config-store items."""

    by_id: dict[str, dict[str, Any]] = {
        _text(item.get("id")): {
            **item,
            "_catalog_source": item.get("_catalog_source") or "builtin",
        }
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
    ordered.extend(
        item for item_id, item in sorted(by_id.items()) if item_id not in seen
    )
    return ordered


def _fallback_agent_config_items(kind: str) -> list[dict[str, Any]]:
    if kind == "skills":
        return [_fallback_skill(spec) for spec in _FALLBACK_WORKFLOW_SPECS]
    if kind == "recipes":
        return _fallback_recipes()
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


def _fallback_recipes() -> list[dict[str, Any]]:
    recipes: dict[str, dict[str, Any]] = {}
    for spec in _FALLBACK_WORKFLOW_SPECS:
        fallback = _fallback_recipe(spec)
        if fallback["id"]:
            recipes[fallback["id"]] = fallback
        for step in spec.get("steps") or []:
            if not isinstance(step, dict):
                continue
            action_key = _text(
                _get(step, "recipeId", "recipe_id")
                or _get(step, "operationType", "operation_type", "actionKey", "action_key")
            )
            if not action_key or action_key in recipes:
                continue
            node_type = _text(_get(step, "nodeType", "node_type"))
            output_kind = _OUTPUT_KIND_BY_CAPABILITY.get(
                node_type,
                _OUTPUT_KIND_BY_CAPABILITY.get(
                    _CAPABILITY_BY_NODE_TYPE.get(node_type, ""),
                    _text(spec.get("generation_type")) or "text",
                ),
            )
            recipes[action_key] = {
                "id": action_key,
                "name": _text(_get(step, "goalTemplate", "goal_template"))
                or _text(spec.get("goal"))
                or action_key,
                "output_kind": output_kind,
                "action_keys": [action_key],
                "system_prompt": "Prompt generation recipe. 输出可交给下游节点执行的提示词/指令。",
                "requires_source_media": output_kind != "text",
                "_catalog_source": "builtin",
            }
    return [recipes[key] for key in sorted(recipes)]


def _catalog_username() -> str:
    if os.environ.get("ST_EDITION", "").strip().lower() == "ce":
        return "local"
    return (
        os.environ.get("DRAMACLAW_USER")
        or os.environ.get("SUPERTALE_USER")
        or os.environ.get("FREEZONE_USER")
        or "local"
    ).strip()


def _catalog_source(payload: dict[str, Any]) -> str:
    return _text(payload.get("_catalog_source")) or "builtin"


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
        elif isinstance(payload, list):
            items.extend(item for item in payload if isinstance(item, dict))
    return items


def _templates(skill: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _get(skill, "workflowTemplates", "workflow_templates") or []
    return [item for item in raw if isinstance(item, dict)]


def _catalog_label(skill: dict[str, Any]) -> str:
    return (
        _text(skill.get("name") or skill.get("label") or skill.get("id"))
        or "配置工作流"
    )


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


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "status": "catalog_workflow_error", "error": message}
