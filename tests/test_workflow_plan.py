from __future__ import annotations

import importlib.util
from pathlib import Path

from novelvideo.freezone.workflow_plan import validate_workflow_plan


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


def test_dynamic_workflow_plan_accepts_different_node_counts():
    catalog = _load_catalog_module()

    three = catalog.validate_agent_workflow_plan(_dynamic_plan(image_count=3))
    six = catalog.validate_agent_workflow_plan(_dynamic_plan(image_count=6))

    assert three["ok"] is True
    assert three["node_count"] == 4
    assert six["ok"] is True
    assert six["node_count"] == 7


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


def test_catalog_validation_rejects_unknown_recipe_and_version_mismatch():
    catalog = _load_catalog_module()
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


def test_catalog_validation_requires_recipe_and_skill_capability():
    catalog = _load_catalog_module()
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


def test_catalog_validation_requires_real_or_generated_source_media():
    catalog = _load_catalog_module()
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
