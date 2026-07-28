import importlib.util
from pathlib import Path


def _load_workflow_drafts_module():
    path = (
        Path(__file__).resolve().parents[1]
        / ".hermes"
        / "plugins"
        / "freezone"
        / "workflow_drafts.py"
    )
    spec = importlib.util.spec_from_file_location("test_workflow_drafts_module", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_plan_preview_explains_ordered_recipe_pipeline():
    preview = _load_workflow_drafts_module()._plan_preview(
        {
            "skill_id": "video-ad",
            "edge_count": 1,
            "plan": {
                "summary": "运动相机广告",
                "phases": ["visual"],
                "inputs": {},
                "nodes": [
                    {
                        "id": "hero",
                        "name": "商品英雄镜头",
                        "stage": "visual",
                        "node_type": "imageGenNode",
                        "data": {
                            "workflowCatalog": {
                                "recipeId": "product-hero",
                                "recipeName": "商品首图",
                                "recipeVersion": "1",
                                "recipePipeline": [
                                    {
                                        "id": "cinematic-lighting",
                                        "name": "电影灯光",
                                        "version": "2",
                                    }
                                ],
                            }
                        },
                    }
                ],
            },
        }
    )

    assert preview["recipe_pipelines"] == [
        {
            "node_id": "hero",
            "node_name": "商品英雄镜头",
            "steps": [
                {
                    "role": "primary",
                    "id": "product-hero",
                    "name": "商品首图",
                    "version": "1",
                },
                {
                    "role": "supplemental",
                    "id": "cinematic-lighting",
                    "name": "电影灯光",
                    "version": "2",
                },
            ],
        }
    ]
