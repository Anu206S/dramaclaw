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
    "category": "image",
    "triggers": {
        "keywords": ["电商产品图"],
        "node_scopes": ["imageGeneration"],
    },
    "allowed_recipe_ids": ["ecommerce-ad-image", "general-image"],
    "planning": {
        "planning_notes": "根据商品素材动态规划电商图。",
        "conduct_rules": ["保留商品主体。"],
    },
    "evaluation": {
        "rating_bands": [{"score": 5, "description": "商品表达清晰。"}],
        "quality_threshold": 4,
        "domain_constraints": ["不得改变商品关键外观。"],
    },
}

_MINIMAL_ECOMMERCE_RECIPES = [
    {
        "id": "ecommerce-ad-image",
        "name": "电商广告图",
        "version": 5,
        "enabled": True,
        "output_kind": "image",
        "action_keys": ["ecommerce-ad-image"],
        "system_prompt": "输出电商广告图提示词。",
        "planning_prompt": "规划电商广告图。",
        "result_summary": "电商广告图已生成。",
        "requires_source_media": True,
    },
    {
        "id": "general-image",
        "name": "通用图片",
        "version": 1,
        "enabled": True,
        "output_kind": "image",
        "action_keys": ["general-image"],
        "system_prompt": "输出通用图片提示词。",
        "planning_prompt": "规划通用图片。",
        "result_summary": "通用图片已生成。",
        "requires_source_media": False,
    },
    {
        "id": "general-video",
        "name": "通用视频",
        "version": 1,
        "enabled": True,
        "output_kind": "video",
        "action_keys": ["general-video"],
        "system_prompt": "输出通用视频提示词。",
        "planning_prompt": "规划通用视频。",
        "result_summary": "通用视频已生成。",
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
        edges.append(
            {"source": "brief", "target": node_id, "link_type": "prompt_for"}
        )
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

    monkeypatch.setattr(catalog, "list_user_agent_config_items", fake_list_user_agent_config_items)
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

    monkeypatch.setattr(catalog, "list_user_agent_config_items", fake_list_user_agent_config_items)
    monkeypatch.setattr(catalog, "_catalog_username", lambda: "local")

    package = catalog.get_workflow_skill(
        {"skill_id": "director-method", "user_goal": "规划 8 个镜头"}
    )

    assert package["ok"] is True
    assert "workflow_templates" not in package["skill"]
    assert package["allowed_node_types"] == ["imageGenNode"]
    assert "director-frame" in {
        recipe["id"] for recipe in package["available_recipes"]
    }
    assert package["planning_contract"]["strict_validation"] is True


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

    monkeypatch.setattr(catalog, "list_user_agent_config_items", fake_list_user_agent_config_items)
    monkeypatch.setattr(catalog, "_catalog_username", lambda: "local")

    custom_package = catalog.get_workflow_skill({"skill_id": "director-method"})
    builtin_package = catalog.get_workflow_skill({"skill_id": "ecommerce-product"})

    assert custom_package["ok"] is True
    assert builtin_package["ok"] is True


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
    assert package["input_contract"]["recommended_run_after_create"] is True
    recipe_ids = {item["id"] for item in package["available_recipes"]}
    assert "general-text" in recipe_ids


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
