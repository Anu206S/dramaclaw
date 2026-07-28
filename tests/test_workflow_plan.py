from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from novelvideo.freezone.workflow_plan import validate_workflow_plan

_MINIMAL_ECOMMERCE_SKILL = {
    "id": "ecommerce-product",
    "name": "电商产品图",
    "version": 6,
    "description": "测试用电商产品图 Skill",
    "enabled": True,
    "triggers": {"node_scopes": ["imageGeneration"]},
    "allowed_recipe_ids": [
        "ecommerce-ad-image",
        "general-image",
        "custom-shot-image",
    ],
}

_MINIMAL_ECOMMERCE_RECIPES = [
    {
        "id": "ecommerce-ad-image",
        "name": "电商广告图",
        "version": 5,
        "enabled": True,
        "output_kind": "image",
        "requires_source_media": True,
    },
    {
        "id": "general-image",
        "name": "通用图片",
        "version": 1,
        "enabled": True,
        "output_kind": "image",
        "requires_source_media": False,
    },
    {
        "id": "general-video",
        "name": "通用视频",
        "version": 1,
        "enabled": True,
        "output_kind": "video",
        "requires_source_media": False,
    },
    {
        "id": "custom-shot-image",
        "name": "自定义分镜图",
        "version": 1,
        "enabled": True,
        "output_kind": "image",
        "requires_source_media": False,
    },
]


def _load_catalog_module():
    path = (
        Path(__file__).resolve().parents[1]
        / ".hermes"
        / "plugins"
        / "freezone"
        / "json_workflow_catalog.py"
    )
    spec = importlib.util.spec_from_file_location("test_dynamic_workflow_catalog", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_minimal_builtin_catalog(monkeypatch, catalog) -> None:
    def fake_load_json_dir(path):
        if path == catalog._SKILLS_DIR:
            return copy.deepcopy([_MINIMAL_ECOMMERCE_SKILL])
        if path == catalog._RECIPES_DIR:
            return copy.deepcopy(_MINIMAL_ECOMMERCE_RECIPES)
        return []

    monkeypatch.setattr(catalog, "_load_json_dir", fake_load_json_dir)
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)


def _dynamic_plan(*, image_count: int = 1) -> dict:
    nodes = [
        {
            "id": "brief",
            "node_type": "textAnnotationNode",
            "stage": "input",
            "data": {"displayName": "用户需求", "content": "运动鞋电商图"},
        }
    ]
    edges = []
    for index in range(image_count):
        node_id = f"product_image_{index + 1}"
        nodes.append(
            {
                "id": node_id,
                "node_type": "imageGenNode",
                "stage": "image",
                "data": {
                    "displayName": f"商品图 {index + 1}",
                    "referenceImageUrl": "/static/product.png",
                    "workflowCatalog": {
                        "skillId": "ecommerce-product",
                        "recipeId": "ecommerce-ad-image",
                        "recipeVersion": "5",
                    },
                },
            }
        )
        edges.append({"source": "brief", "target": node_id, "link_type": "prompt_for"})
    return {
        "schema_version": "freezone_workflow_plan.v1",
        "workflow_type": "dynamic.ecommerce-product",
        "skill": {"id": "ecommerce-product", "version": 6},
        "summary": f"{image_count} 张运动鞋电商图",
        "nodes": nodes,
        "edges": edges,
        "layout": {"direction": "left_to_right", "groups": []},
    }


def _use_parameterized_catalog(monkeypatch, catalog):
    def fake_list_user_agent_config_items(_username, kind):
        if kind == "skills":
            return [
                {
                    "id": "cinematic-short",
                    "triggers": {"node_scopes": ["textGeneration"]},
                    "allowed_recipe_ids": ["general-text"],
                    "input_parameters": [
                        {
                            "id": "duration",
                            "label": "成片时长",
                            "type": "single_select",
                            "required": True,
                            "default": "60",
                            "options": [
                                {"value": "60", "label": "60秒"},
                                {"value": "90", "label": "90秒"},
                            ],
                        },
                        {
                            "id": "execution_mode",
                            "label": "执行模式",
                            "type": "single_select",
                            "required": True,
                            "default": "auto",
                            "options": [
                                {"value": "auto", "label": "全自动"},
                                {"value": "manual", "label": "只创建画布"},
                            ],
                        },
                        {
                            "id": "aspect_ratio",
                            "label": "画幅比例",
                            "type": "single_select",
                            "required": False,
                            "default": "16:9",
                            "options": [
                                {"value": "16:9", "label": "16:9 横屏"},
                                {"value": "9:16", "label": "9:16 竖屏"},
                            ],
                        },
                    ],
                    "planning": {"planning_notes": "动态规划电影短片"},
                }
            ]
        if kind == "recipes":
            return [
                {
                    "id": "general-text",
                    "version": 1,
                    "output_kind": "text",
                    "system_prompt": "生成文本",
                }
            ]
        raise AssertionError(kind)

    monkeypatch.setattr(
        catalog, "list_user_agent_config_items", fake_list_user_agent_config_items
    )
    monkeypatch.setattr(catalog, "_catalog_username", lambda: "local")


def test_workflow_skill_package_supports_skill_without_template(monkeypatch):
    catalog = _load_catalog_module()

    def fake_list_user_agent_config_items(_username, kind):
        if kind == "skills":
            return [
                {
                    "id": "director-method",
                    "description": "没有固定模板的导演方法",
                    "triggers": {"node_scopes": ["imageGeneration"]},
                    "planning": {"planning_notes": "根据用户要求动态规划镜头"},
                    "allowed_recipe_ids": ["director-frame"],
                }
            ]
        if kind == "recipes":
            return [
                {
                    "id": "director-frame",
                    "name": "导演关键帧",
                    "version": 2,
                    "output_kind": "image",
                    "planning_prompt": "生成关键帧",
                    "result_summary": "关键帧图片",
                }
            ]
        raise AssertionError(kind)

    monkeypatch.setattr(
        catalog, "list_user_agent_config_items", fake_list_user_agent_config_items
    )
    monkeypatch.setattr(catalog, "_catalog_username", lambda: "local")

    package = catalog.get_workflow_skill(
        {"skill_id": "director-method", "user_goal": "规划 8 个镜头"}
    )

    assert package["ok"] is True
    assert "workflow_templates" not in package["skill"]
    assert package["allowed_node_types"] == ["imageGenNode"]
    assert "director-frame" in {recipe["id"] for recipe in package["available_recipes"]}
    assert package["planning_contract"]["strict_validation"] is True


def test_dynamic_item_supports_ordered_recipe_pipeline(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)

    compiled = catalog.compile_workflow_intent(
        {
            "skill_id": "ecommerce-product",
            "user_goal": "先按通用构图，再按自定义分镜方法生成商品图",
            "items": [
                {
                    "id": "hero-shot",
                    "title": "商品英雄镜头",
                    "recipe_id": "general-image",
                    "recipe_pipeline": ["custom-shot-image", "general-image"],
                }
            ],
            "include_compose": False,
        }
    )

    assert compiled["ok"] is True
    workflow_catalog = compiled["plan"]["nodes"][1]["data"]["workflowCatalog"]
    assert workflow_catalog["recipeId"] == "general-image"
    assert workflow_catalog["recipePipeline"] == [
        {"id": "custom-shot-image", "version": 1}
    ]


def test_user_agent_config_merges_with_builtin_catalog(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)

    def fake_list_user_agent_config_items(_username, kind):
        if kind == "skills":
            return [
                {
                    "id": "director-method",
                    "description": "用户自定义导演方法",
                    "triggers": {"node_scopes": ["imageGeneration"]},
                    "allowed_recipe_ids": ["director-frame"],
                }
            ]
        if kind == "recipes":
            return [
                {
                    "id": "director-frame",
                    "name": "导演关键帧",
                    "version": 1,
                    "output_kind": "image",
                }
            ]
        raise AssertionError(kind)

    monkeypatch.setattr(
        catalog, "list_user_agent_config_items", fake_list_user_agent_config_items
    )
    monkeypatch.setattr(catalog, "_catalog_username", lambda: "local")

    custom_package = catalog.get_workflow_skill({"skill_id": "director-method"})
    builtin_package = catalog.get_workflow_skill({"skill_id": "ecommerce-product"})

    assert custom_package["ok"] is True
    assert builtin_package["ok"] is False


def test_workflow_skill_limits_recipes_and_identifies_source_anchor(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)

    package = catalog.get_workflow_skill({"skill_id": "ecommerce-product"})

    recipe_ids = {item["id"] for item in package["available_recipes"]}
    assert recipe_ids == {
        "ecommerce-ad-image",
        "general-image",
        "custom-shot-image",
    }
    assert package["planning_contract"]["recipe_ids_by_output_kind"] == {
        "image": [
            "custom-shot-image",
            "ecommerce-ad-image",
            "general-image",
        ]
    }
    assert package["planning_contract"]["missing_source_media"][
        "source_anchor_recipe_ids"
    ] == {"image": ["custom-shot-image", "general-image"]}


def test_compact_dynamic_intent_compiles_recipe_items_to_valid_plan(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)

    compiled = catalog.compile_workflow_intent(
        {
            "schema_version": "freezone_workflow_intent.v1",
            "skill_id": "pixar-ip-ad-video",
            "user_goal": "为黑色运动相机制作 15 秒 9:16 竖屏广告",
            "inputs": {"aspect_ratio": "9:16", "duration": "15"},
            "items": [
                {
                    "id": "character_anchor",
                    "title": "角色锚点",
                    "prompt": "设计品牌动画角色",
                    "recipe_id": "ad-ip-character-anchor",
                },
                {
                    "id": "storyboard",
                    "title": "广告分镜",
                    "prompt": "生成五镜头广告分镜",
                    "recipe_id": "storyboard-sketch",
                    "depends_on": ["character_anchor"],
                },
                {
                    "id": "video_clip",
                    "title": "广告视频",
                    "prompt": "生成品牌广告视频",
                    "recipe_id": "shot-video",
                    "depends_on": ["storyboard"],
                },
            ],
        }
    )

    assert compiled["ok"] is True
    assert compiled["node_count"] == 5
    plan = compiled["plan"]
    assert plan["mode"] == "tool_compiled_dynamic"
    node_catalog = plan["nodes"][1]["data"]["workflowCatalog"]
    assert node_catalog["recipeId"] == "ad-ip-character-anchor"
    assert node_catalog["skillVersion"] == plan["skill"]["version"]
    assert node_catalog["confirmedInputs"]["aspect_ratio"] == "9:16"
    assert plan["nodes"][-1]["node_type"] == "videoComposeNode"
    assert catalog.validate_agent_workflow_plan(plan)["ok"] is True


def test_validator_rejects_skill_version_mismatch_and_recipe_outside_whitelist():
    plan = _dynamic_plan()
    plan["nodes"][1]["data"]["workflowCatalog"]["skillVersion"] = "5"
    result = validate_workflow_plan(
        plan,
        skills_by_id={"ecommerce-product": _MINIMAL_ECOMMERCE_SKILL},
        recipes_by_id={item["id"]: item for item in _MINIMAL_ECOMMERCE_RECIPES},
    )
    assert result["ok"] is False
    assert any(issue["path"].endswith("skillVersion") for issue in result["errors"])

    plan = _dynamic_plan()
    plan["nodes"][1]["data"]["workflowCatalog"]["recipeId"] = "general-video"
    result = validate_workflow_plan(
        plan,
        skills_by_id={"ecommerce-product": _MINIMAL_ECOMMERCE_SKILL},
        recipes_by_id={item["id"]: item for item in _MINIMAL_ECOMMERCE_RECIPES},
    )
    assert result["ok"] is False
    assert any("not allowed by skill" in issue["message"] for issue in result["errors"])


def test_compiler_uses_explicit_anchor_and_skips_audio_only_compose(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)

    ecommerce = catalog.compile_workflow_intent(
        {
            "skill_id": "pixar-ip-ad-video",
            "user_goal": "为一款新产品制作动画广告",
            "items": [
                {
                    "id": "anchor",
                    "title": "角色锚点",
                    "prompt": "生成品牌角色",
                    "recipe_id": "ad-ip-character-anchor",
                },
                {
                    "id": "video",
                    "title": "广告视频",
                    "prompt": "生成品牌广告视频",
                    "recipe_id": "shot-video",
                    "depends_on": ["anchor"],
                },
            ],
        }
    )
    audio = catalog.compile_workflow_intent(
        {
            "skill_id": "video-tutorial",
            "user_goal": "把欢迎使用转换成中文语音",
            "items": [
                {
                    "id": "audio",
                    "title": "广告音频",
                    "prompt": "欢迎使用",
                    "narration": "欢迎使用",
                    "recipe_id": "general-audio",
                }
            ],
        }
    )

    assert ecommerce["ok"] is True
    assert ecommerce["plan"]["nodes"][1]["id"] == "anchor"
    assert audio["ok"] is True
    assert all(
        node["node_type"] != "videoComposeNode" for node in audio["plan"]["nodes"]
    )
    audio_node = next(
        node for node in audio["plan"]["nodes"] if node["node_type"] == "audioNode"
    )
    assert audio_node["data"]["workflowCatalog"]["recipeId"] == "general-audio"


def test_parameterized_skill_uses_stateless_input_contract(monkeypatch):
    catalog = _load_catalog_module()
    _use_parameterized_catalog(monkeypatch, catalog)

    package = catalog.get_workflow_skill(
        {
            "skill_id": "cinematic-short",
            "user_goal": "生成一支竖屏电影感短片",
            "inputs": {"duration": "90"},
        }
    )

    assert package["ok"] is True
    assert "type" not in package["skill"]
    assert "parameters" not in package["skill"]
    assert package["skill"]["input_parameters"]
    assert package["input_contract"]["ready_for_planning"] is True
    assert package["input_contract"]["resolved"]["duration"] == "90"
    assert package["input_contract"]["resolved"]["aspect_ratio"] == "9:16"
    assert package["input_contract"]["inferred"] == {"aspect_ratio": "9:16"}
    assert (
        next(
            field
            for field in package["input_contract"]["fields"]
            if field["id"] == "aspect_ratio"
        )["source"]
        == "inferred"
    )
    assert package["input_contract"]["recommended_run_after_create"] is True
    recipe_ids = {item["id"] for item in package["available_recipes"]}
    assert "general-text" in recipe_ids


def test_explicit_skill_inputs_override_deterministic_inference(monkeypatch):
    catalog = _load_catalog_module()
    _use_parameterized_catalog(monkeypatch, catalog)

    package = catalog.get_workflow_skill(
        {
            "skill_id": "cinematic-short",
            "user_goal": "生成一支 90 秒竖屏短片并自动执行",
            "inputs": {
                "duration": "60",
                "aspect_ratio": "16:9",
                "execution_mode": "manual",
            },
        }
    )

    contract = package["input_contract"]
    assert contract["resolved"] == {
        "duration": "60",
        "execution_mode": "manual",
        "aspect_ratio": "16:9",
    }
    assert contract["inferred"] == {
        "duration": "90",
        "execution_mode": "auto",
        "aspect_ratio": "9:16",
    }
    assert contract["recommended_run_after_create"] is False


def test_workflow_skill_input_contract_rejects_unknown_option(monkeypatch):
    catalog = _load_catalog_module()
    _use_parameterized_catalog(monkeypatch, catalog)

    package = catalog.get_workflow_skill(
        {
            "skill_id": "cinematic-short",
            "inputs": {"duration": "120"},
        }
    )

    assert package["ok"] is True
    assert package["input_contract"]["ready_for_planning"] is False
    assert package["input_contract"]["errors"] == [
        {"path": "inputs.duration", "message": "unsupported option: 120"}
    ]


def test_dynamic_workflow_plan_accepts_different_node_counts(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)

    three = catalog.validate_agent_workflow_plan(_dynamic_plan(image_count=3))
    six = catalog.validate_agent_workflow_plan(_dynamic_plan(image_count=6))

    assert three["ok"] is True
    assert three["node_count"] == 4
    assert six["ok"] is True
    assert six["node_count"] == 7


def test_dynamic_workflow_plan_validates_skill_inputs(monkeypatch):
    catalog = _load_catalog_module()
    _use_parameterized_catalog(monkeypatch, catalog)
    plan = {
        "schema_version": "freezone_workflow_plan.v1",
        "workflow_type": "dynamic.cinematic-short",
        "skill": {"id": "cinematic-short"},
        "inputs": {"duration": "120", "execution_mode": "manual"},
        "nodes": [
            {
                "id": "concept",
                "node_type": "textAnnotationNode",
                "stage": "story",
                "data": {
                    "prompt": "生成电影短片概念",
                    "workflowCatalog": {
                        "skillId": "cinematic-short",
                        "recipeId": "general-text",
                        "recipeVersion": "1",
                    },
                },
            }
        ],
        "edges": [],
    }

    invalid = catalog.validate_agent_workflow_plan(plan)
    assert invalid["ok"] is False
    assert invalid["errors"][0] == {
        "path": "inputs.duration",
        "message": "unsupported option: 120",
    }

    plan["inputs"]["duration"] = "90"
    valid = catalog.validate_agent_workflow_plan(plan)
    assert valid["ok"] is True
    assert valid["execution_mode"] == "manual"
    assert valid["recommended_run_after_create"] is False


def test_strict_workflow_plan_rejects_unknown_node_bad_edge_and_cycle():
    plan = _dynamic_plan()
    plan["nodes"].append({"id": "invalid", "node_type": "inventedImageNode"})
    plan["edges"].append(
        {"source": "missing", "target": "brief", "link_type": "context_for"}
    )
    plan["edges"].append(
        {"source": "product_image_1", "target": "brief", "link_type": "media_input_for"}
    )

    result = validate_workflow_plan(plan)

    assert result["ok"] is False
    assert result["status"] == "invalid_dynamic_workflow_plan"
    paths = {error["path"] for error in result["errors"]}
    assert "nodes[2].node_type" in paths
    assert "edges[1].source" in paths
    assert any("cycle" in error["message"] for error in result["errors"])


def test_catalog_validation_rejects_unknown_recipe_and_version_mismatch(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)
    unknown = _dynamic_plan()
    unknown["nodes"][1]["data"]["workflowCatalog"]["recipeId"] = "not-a-recipe"
    mismatch = _dynamic_plan()
    mismatch["nodes"][1]["data"]["workflowCatalog"]["recipeVersion"] = "999"

    unknown_result = catalog.validate_agent_workflow_plan(unknown)
    mismatch_result = catalog.validate_agent_workflow_plan(mismatch)

    assert unknown_result["ok"] is False
    assert "unknown recipe" in unknown_result["error"]
    assert mismatch_result["ok"] is False
    assert "version mismatch" in mismatch_result["error"]


def test_catalog_validation_requires_recipe_and_skill_capability(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)
    missing_recipe = _dynamic_plan()
    missing_recipe["nodes"][1]["data"].pop("workflowCatalog")
    unsupported_capability = _dynamic_plan()
    unsupported_capability["nodes"][1]["node_type"] = "videoNode"
    unsupported_catalog = unsupported_capability["nodes"][1]["data"]["workflowCatalog"]
    unsupported_catalog["recipeId"] = "general-video"
    unsupported_catalog["recipeVersion"] = "1"

    missing_result = catalog.validate_agent_workflow_plan(missing_recipe)
    unsupported_result = catalog.validate_agent_workflow_plan(unsupported_capability)

    assert missing_result["ok"] is False
    assert "requires an explicit recipeId" in missing_result["error"]
    assert unsupported_result["ok"] is False
    assert any(
        "not allowed by skill" in error["message"]
        for error in unsupported_result["errors"]
    )


def test_catalog_validation_requires_real_or_generated_source_media(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)
    missing_source = _dynamic_plan()
    missing_source["nodes"][1]["data"].pop("referenceImageUrl")

    missing_result = catalog.validate_agent_workflow_plan(missing_source)

    assert missing_result["ok"] is False
    assert "requires source media" in missing_result["error"]

    anchor = {
        "id": "product_anchor",
        "node_type": "imageGenNode",
        "stage": "asset",
        "data": {
            "prompt": "中性背景的运动鞋产品基准图",
            "workflowCatalog": {
                "skillId": "ecommerce-product",
                "recipeId": "general-image",
                "recipeVersion": "1",
            },
        },
    }
    missing_source["nodes"].insert(1, anchor)
    missing_source["edges"].append(
        {
            "source": "product_anchor",
            "target": "product_image_1",
            "link_type": "media_input_for",
        }
    )

    anchored_result = catalog.validate_agent_workflow_plan(missing_source)

    assert anchored_result["ok"] is True


def test_project_catalog_uses_canonical_pixar_skill_and_recipes(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)

    skills = {item["id"]: item for item in catalog._load_skills()}
    recipes = {
        item["id"]: item
        for item in catalog._load_agent_config_items("recipes", catalog._RECIPES_DIR)
    }

    assert skills["ecommerce-ad"]["name"] == "电商广告"
    assert skills["video-tutorial"]["name"] == "视频解说教程"
    assert skills["text-to-image-video"]["name"] == "文生图生视频（动态）"
    assert skills["short-drama-quick"]["name"] == "短剧（快速测试）"
    assert skills["pixar-ip-ad-video"]["name"] == "皮克斯 IP 品牌广告短片"
    assert skills["lego-minifigure-animation-video"]["name"] == "乐高小人动画短片"
    assert "pixar-ip-brand-ad-short-film" not in skills
    assert skills["pixar-ip-ad-video"]["allowed_recipe_ids"] == [
        "ad-ip-character-anchor",
        "ad-product-prop-anchor",
        "storyboard-sketch",
        "shot-video",
        "ad-video-audio-layer",
    ]
    assert skills["lego-minifigure-animation-video"]["allowed_recipe_ids"] == [
        "workflow-input-analysis",
        "short-film-script-outline",
        "storyboard-plan",
        "visual-key-elements",
        "storyboard-shot-video",
        "video-audio-layer",
    ]
    assert "ad-ip-character-anchor" in recipes
    assert "ad-product-prop-anchor" in recipes
    assert "storyboard-sketch" in recipes
    assert "shot-video" in recipes
    assert "ad-video-audio-layer" in recipes
    assert "workflow-input-analysis" in recipes
    assert "short-film-script-outline" in recipes
    assert "storyboard-plan" in recipes
    assert "visual-key-elements" in recipes
    assert "storyboard-shot-video" in recipes
    assert "video-audio-layer" in recipes
    assert "pixar-ip-character-design" not in recipes
    assert "pixar-ip-prop-anchor" not in recipes
    assert "pixar-ip-storyboard-sketch" not in recipes
    assert "pixar-ip-shot-video" not in recipes
    assert "pixar-ip-audio-layers" not in recipes
    assert "pixar-ip-compose-plan" not in recipes
    assert "pixar-shot-video-clip" not in recipes
    assert "ad-audio-production" not in recipes
    assert "lego-minifig-input-analysis" not in recipes
    assert "lego-minifig-script-outline" not in recipes
    assert "lego-minifig-video-spec" not in recipes
    assert "lego-minifig-storyboard" not in recipes
    assert "lego-minifig-key-elements" not in recipes
    assert "lego-minifig-shot-video" not in recipes
    assert "lego-minifig-audio-layers" not in recipes


def test_pixar_skill_keeps_methodology_while_recipes_stay_stage_focused(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)

    skills = {item["id"]: item for item in catalog._load_skills()}
    recipes = {
        item["id"]: item
        for item in catalog._load_agent_config_items("recipes", catalog._RECIPES_DIR)
    }
    pixar_skill = skills["pixar-ip-ad-video"]
    planning_text = "\n".join(
        [
            pixar_skill["planning"]["planning_notes"],
            pixar_skill["planning"]["prompt_guide"],
            "\n".join(pixar_skill["planning"]["conduct_rules"]),
            "\n".join(pixar_skill["evaluation"]["domain_constraints"]),
        ]
    )
    planning_notes = pixar_skill["planning"]["planning_notes"]
    prompt_guide = pixar_skill["planning"]["prompt_guide"]

    assert "闸门 1" in planning_text
    assert "角色属性表" in planning_text
    assert "产品道具" in planning_text
    assert "角色关联道具" in planning_text
    assert "15 秒广告 = 9 个面板" in planning_text
    assert "15 秒广告拆分为 4 个视频片段" in planning_text
    assert "角色设计" in planning_text and "分镜" in planning_text
    assert "皮克斯 3D 卡通渲染" in prompt_guide
    assert "C4D + Octane" in prompt_guide
    assert "【执行路径】" not in prompt_guide
    assert "【皮克斯视觉方向】" not in planning_notes

    recipe_text = "\n".join(
        item
        for recipe_id in [
            "ad-ip-character-anchor",
            "ad-product-prop-anchor",
            "storyboard-sketch",
            "shot-video",
            "ad-video-audio-layer",
        ]
        for item in [
            recipes[recipe_id]["system_prompt"],
            recipes[recipe_id]["planning_prompt"],
            "\n".join(recipes[recipe_id]["must_have_items"]),
        ]
    )
    assert "自创风格" not in recipe_text
    assert "覆盖 Skill" not in recipe_text
    assert "Recipe 内" not in recipe_text

    character_anchor = recipes["ad-ip-character-anchor"]
    character_text = "\n".join(
        [
            character_anchor["name"],
            character_anchor["system_prompt"],
            character_anchor["planning_prompt"],
            character_anchor["result_summary"],
            "\n".join(character_anchor["must_have_items"]),
        ]
    )
    assert "广告 IP 角色锚点" in character_text
    assert "身体附属结构" in character_text
    assert "品牌、Logo、产品卖点和产品外观留给道具锚点阶段" in character_text
    assert "尾巴状态必须明确" not in character_text
    assert "no tail / tailless" not in character_text


def test_lego_skill_keeps_style_while_recipes_are_shared_workflow_stages(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)

    skills = {item["id"]: item for item in catalog._load_skills()}
    recipes = {
        item["id"]: item
        for item in catalog._load_agent_config_items("recipes", catalog._RECIPES_DIR)
    }
    lego_skill = skills["lego-minifigure-animation-video"]
    planning = lego_skill["planning"]
    planning_text = "\n".join(
        [
            planning["planning_notes"],
            planning["prompt_guide"],
            "\n".join(planning["conduct_rules"]),
            "\n".join(lego_skill["evaluation"]["domain_constraints"]),
        ]
    )

    assert "LEGO Minifigure animation" in planning["prompt_guide"]
    assert "ABS 塑料材质" in planning["prompt_guide"]
    assert "LEGO building logic" in planning["prompt_guide"]
    assert "输入分析" in planning["planning_notes"]
    assert "剧本大纲" in planning["planning_notes"]
    assert "三层分镜" in planning["planning_notes"]
    assert "视觉关键元素" in planning["planning_notes"]
    assert "视频片段" in planning["planning_notes"]
    assert "音频" in planning["planning_notes"]
    assert "Final_Video_Spec" not in planning_text
    assert "input_parameters" not in planning_text
    assert "planning.prompt_guide" not in planning_text
    assert "conduct_rules" not in planning_text
    assert "workflow-input-analysis" not in planning_text
    assert "short-film-script-outline" not in planning_text
    assert "storyboard-plan" not in planning_text
    assert "visual-key-elements" not in planning_text
    assert "storyboard-shot-video" not in planning_text
    assert "video-audio-layer" not in planning_text

    recipe_text = "\n".join(
        item
        for recipe_id in [
            "workflow-input-analysis",
            "short-film-script-outline",
            "storyboard-plan",
            "visual-key-elements",
            "storyboard-shot-video",
            "video-audio-layer",
        ]
        for item in [
            recipes[recipe_id]["name"],
            recipes[recipe_id]["system_prompt"],
            recipes[recipe_id]["planning_prompt"],
            recipes[recipe_id]["result_summary"],
            "\n".join(recipes[recipe_id]["must_have_items"]),
        ]
    )
    assert "LEGO Minifigure" not in recipe_text
    assert "official LEGO style" not in recipe_text
    assert "ABS plastic material" not in recipe_text
    assert "Final_Video_Spec" not in recipe_text
    assert "Skill 输入参数" not in recipe_text
    assert "覆盖 Skill" not in recipe_text
    assert "Recipe 内" not in recipe_text


def test_project_catalog_skills_compile_dynamic_multi_item_workflows(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)
    skill_recipes = {
        "ecommerce-ad": ("video-clip-generation", "general-image"),
        "video-tutorial": ("general-video", None),
        "text-to-image-video": ("general-video", None),
        "short-drama-quick": ("general-video", None),
        "pixar-ip-ad-video": ("shot-video", "ad-ip-character-anchor"),
        "lego-minifigure-animation-video": (
            "storyboard-shot-video",
            "visual-key-elements",
        ),
    }

    for skill_id, (recipe_id, anchor_recipe_id) in skill_recipes.items():
        anchor_items = (
            [
                {
                    "id": "anchor",
                    "title": "素材锚点",
                    "prompt": "生成一致性素材锚点",
                    "recipe_id": anchor_recipe_id,
                }
            ]
            if anchor_recipe_id
            else []
        )
        compiled = catalog.compile_workflow_intent(
            {
                "schema_version": "freezone_workflow_intent.v1",
                "skill_id": skill_id,
                "user_goal": f"测试 {skill_id}",
                "items": anchor_items + [
                    {
                        "id": f"shot_{index}",
                        "title": f"镜头 {index}",
                        "prompt": f"测试镜头 {index}",
                        "recipe_id": recipe_id,
                        **({"depends_on": ["anchor"]} if anchor_recipe_id else {}),
                    }
                    for index in range(1, 4)
                ],
            }
        )

        assert compiled["ok"] is True, (skill_id, compiled)
        assert catalog.validate_agent_workflow_plan(compiled["plan"])["ok"] is True
        assert compiled["plan"]["nodes"][-1]["node_type"] == "videoComposeNode"


def test_short_drama_quick_expands_shot_voice_and_background_music(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setattr(catalog, "list_user_agent_config_items", None)

    compiled = catalog.compile_workflow_intent(
        {
            "schema_version": "freezone_workflow_intent.v1",
            "skill_id": "short-drama-quick",
            "user_goal": "制作两镜头悬疑短剧",
            "items": [
                {
                    "id": "clip_1",
                    "title": "镜头一",
                    "prompt": "便利店外景",
                    "recipe_id": "general-video",
                },
                {
                    "id": "clip_2",
                    "title": "镜头二",
                    "prompt": "店员看向监控",
                    "recipe_id": "general-video",
                },
                {
                    "id": "voice_1",
                    "title": "镜头一旁白",
                    "prompt": "深夜的便利店，只有他一个人。",
                    "narration": "深夜的便利店，只有他一个人。",
                    "recipe_id": "drama-shot-voice",
                    "depends_on": ["clip_1"],
                    "timeline_role": "shot_voice",
                },
                {
                    "id": "voice_2",
                    "title": "镜头二旁白",
                    "prompt": "监控里的自己，为什么没有同步动作？",
                    "narration": "监控里的自己，为什么没有同步动作？",
                    "recipe_id": "drama-shot-voice",
                    "depends_on": ["clip_2"],
                    "timeline_role": "shot_voice",
                },
                {
                    "id": "background_music",
                    "title": "背景音乐",
                    "prompt": "悬疑氛围纯音乐",
                    "recipe_id": "drama-background-music",
                    "timeline_role": "background_music",
                },
            ],
        }
    )

    assert compiled["ok"] is True
    plan = compiled["plan"]
    voice_nodes = [
        node
        for node in plan["nodes"]
        if node["data"].get("workflowCatalog", {}).get("timelineRole") == "shot_voice"
    ]
    bgm_nodes = [
        node
        for node in plan["nodes"]
        if node["data"].get("workflowCatalog", {}).get("timelineRole") == "background_music"
    ]
    assert [node["data"]["text"] for node in voice_nodes] == [
        "深夜的便利店，只有他一个人。",
        "监控里的自己，为什么没有同步动作？",
    ]
    assert all(node["data"]["audioKind"] == "speech" for node in voice_nodes)
    assert all(
        node["data"]["workflowCatalog"]["timelineRole"] == "shot_voice"
        for node in voice_nodes
    )
    assert len(bgm_nodes) == 1
    assert bgm_nodes[0]["data"]["audioKind"] == "music"
    assert bgm_nodes[0]["data"]["workflowCatalog"]["timelineRole"] == "background_music"
    assert {
        (edge["source"], edge["target"])
        for edge in plan["edges"]
        if edge["target"].startswith("voice_")
    } == {
        ("clip_1", "voice_1"),
        ("clip_2", "voice_2"),
    }
