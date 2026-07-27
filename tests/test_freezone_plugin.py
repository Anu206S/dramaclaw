from __future__ import annotations

import copy
import importlib.util
import json
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_MINIMAL_ECOMMERCE_SKILL = {
    "id": "ecommerce-product",
    "name": "电商产品图",
    "version": 6,
    "description": "测试用电商产品图 Skill",
    "enabled": True,
    "triggers": {"node_scopes": ["imageGeneration"]},
    "allowed_recipe_ids": ["ecommerce-ad-image", "general-image"],
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
]


def _load_plugin_module():
    tools_module = types.ModuleType("tools")
    registry_module = types.ModuleType("tools.registry")
    registry_module.tool_error = lambda value: value
    registry_module.tool_result = lambda value: value
    sys.modules["tools"] = tools_module
    sys.modules["tools.registry"] = registry_module

    path = Path(__file__).resolve().parents[1] / ".hermes" / "plugins" / "freezone" / "__init__.py"
    spec = importlib.util.spec_from_file_location("test_freezone_plugin", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_plugin_module_with_registry_result(registry_result):
    tools_module = types.ModuleType("tools")
    registry_module = types.ModuleType("tools.registry")
    registry_module.tool_error = lambda value: json.dumps({"ok": False, "error": str(value)}, ensure_ascii=False)
    registry_module.tool_result = registry_result
    sys.modules["tools"] = tools_module
    sys.modules["tools.registry"] = registry_module

    path = Path(__file__).resolve().parents[1] / ".hermes" / "plugins" / "freezone" / "__init__.py"
    spec = importlib.util.spec_from_file_location("test_freezone_plugin_structured", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_catalog_module():
    path = (
        Path(__file__).resolve().parents[1]
        / ".hermes"
        / "plugins"
        / "freezone"
        / "json_workflow_catalog.py"
    )
    spec = importlib.util.spec_from_file_location("test_freezone_json_workflow_catalog", path)
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


def test_freezone_plugin_registers_canvas_command_tools():
    plugin = _load_plugin_module()

    names = {name for name, _schema, _handler in plugin.TOOLS}
    schemas = {name: schema for name, schema, _handler in plugin.TOOLS}

    assert "freezone_request_user_clarification" in names
    assert "freezone_emit_canvas_command" in names
    assert "freezone_create_node" in names
    assert "freezone_update_node_data" in names
    assert "freezone_run_node_action" in names
    assert "freezone_run_workflow" in names
    assert "freezone_get_mainline_projection_assets" in names
    assert "freezone_list_workflows" not in names
    assert "freezone_build_workflow_plan" not in names
    assert "freezone_resolve_catalog_workflow" not in names
    assert "freezone_get_workflow_skill" in names
    assert not any(name.startswith("freezone_skill_") for name in names)
    assert "freezone_prepare_workflow_draft" in names
    assert "freezone_patch_workflow_draft" in names
    assert "freezone_confirm_workflow_draft" in names
    assert "freezone_create_workflow_from_intent" in names
    assert "freezone_create_workflow_graph" in names
    assert "freezone_present_agent_catalog_draft" in names
    assert "freezone_begin_agent_catalog_draft" in names
    assert "freezone_put_agent_catalog_skill" in names
    assert "freezone_put_agent_catalog_recipe" in names
    assert "freezone_patch_agent_catalog_draft" in names
    assert "freezone_finish_agent_catalog_draft" in names
    assert "freezone_get_saved_skill" in names
    assert "freezone_get_saved_recipe" in names
    create_schema = schemas["freezone_create_workflow_graph"]["parameters"]
    assert create_schema["required"] == ["plan"]
    assert "workflow_type" not in create_schema["properties"]
    assert "items" not in create_schema["properties"]
    intent_schema = schemas["freezone_create_workflow_from_intent"]["parameters"]
    assert intent_schema["required"] == ["intent"]
    assert intent_schema["properties"]["intent"]["required"] == [
        "skill_id",
        "user_goal",
    ]
    draft_schema = schemas["freezone_confirm_workflow_draft"]["parameters"]
    assert draft_schema["required"] == ["draft_id", "revision"]
    patch_draft_schema = schemas["freezone_patch_workflow_draft"]["parameters"]
    assert patch_draft_schema["required"] == [
        "draft_id",
        "expected_revision",
        "changes",
    ]


def test_freezone_run_workflow_emits_one_deterministic_runner_command(monkeypatch):
    plugin = _load_plugin_module()
    captured = {}

    def fake_single_write(args, command):
        captured["args"] = args
        captured["command"] = command
        return "queued"

    monkeypatch.setattr(plugin, "_single_write_command", fake_single_write)

    result = plugin._handle_run_workflow(
        {
            "node_ids": ["shot-2"],
            "direction": "downstream",
            "regenerate": True,
        }
    )

    assert result == "queued"
    assert captured["command"] == {
        "type": "run_workflow",
        "node_ids": ["shot-2"],
        "direction": "downstream",
        "regenerate": True,
    }


def test_freezone_run_workflow_command_passes_write_shape_validation():
    plugin = _load_plugin_module()

    error = plugin._validate_write_commands_shape(
        "project-a",
        "canvas-a",
        [{"type": "run_workflow", "scope": "canvas", "direction": "connected"}],
    )

    assert error is None


def test_dynamic_workflow_plan_is_rejected_before_canvas_bridge():
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    result = handlers["freezone_create_workflow_graph"](
        {
            "plan": {
                "schema_version": "freezone_workflow_plan.v1",
                "workflow_type": "dynamic.ecommerce-product",
                "skill": {"id": "ecommerce-product"},
                "nodes": [{"id": "bad", "node_type": "inventedNode"}],
                "edges": [],
            }
        }
    )

    assert result["ok"] is False
    assert result["status"] == "invalid_dynamic_workflow_plan"
    assert result["errors"][0]["path"] == "nodes[0].node_type"


def test_fixed_workflow_creation_is_rejected_before_canvas_bridge():
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    result = handlers["freezone_create_workflow_graph"](
        {"workflow_type": "catalog.ecommerce_product.ecommerce_scene_images", "count": 3}
    )

    assert result["ok"] is False
    assert result["status"] == "dynamic_workflow_plan_required"


def test_handwritten_workflow_batch_cannot_bypass_dynamic_plan():
    plugin = _load_plugin_module()

    result = plugin._handle_emit_canvas_command(
        {
            "commands": [
                {
                    "type": "create_node",
                    "node_type": "textAnnotationNode",
                    "data": {"displayName": "广告视频工作流"},
                },
                {"type": "create_node", "node_type": "imageGenNode"},
                {"type": "create_node", "node_type": "videoNode"},
            ]
        }
    )

    assert result["ok"] is False
    assert result["status"] == "wrong_tool_dynamic_workflow"


def test_dynamic_workflow_creation_reaches_canvas_bridge(monkeypatch):
    plugin = _load_plugin_module()
    plan = {
        "schema_version": "freezone_workflow_plan.v1",
        "workflow_type": "dynamic.ecommerce-product",
        "skill": {"id": "ecommerce-product"},
        "nodes": [],
        "edges": [],
    }
    commands = [{"type": "create_node", "node_type": "textAnnotationNode"}]
    captured = {}

    monkeypatch.setattr(plugin, "validate_agent_workflow_plan", lambda value: {"ok": value is plan})
    monkeypatch.setattr(
        plugin,
        "build_workflow_graph_commands",
        lambda args: {"ok": True, "commands": commands, "plan": args["plan"]},
    )

    def fake_emit(project, canvas, emitted, **kwargs):
        captured.update(
            {"project": project, "canvas": canvas, "commands": emitted, "kwargs": kwargs}
        )
        return "created"

    monkeypatch.setattr(plugin, "_emit_canvas_commands", fake_emit)

    result = plugin._handle_create_workflow_graph(
        {"project_id": "project-a", "canvas_id": "canvas-a", "plan": plan}
    )

    assert result == "created"
    assert captured["commands"] == commands
    assert captured["kwargs"]["allow_dynamic_workflow_batch"] is True


def test_workflow_graph_connects_existing_canvas_anchor_to_new_node():
    plugin = _load_plugin_module()
    result = plugin.build_workflow_graph_commands(
        {
            "plan": {
                "schema_version": "freezone_workflow_plan.v1",
                "workflow_type": "dynamic.ecommerce-product",
                "skill": {"id": "ecommerce-product"},
                "nodes": [
                    {
                        "id": "hero-shot",
                        "node_type": "imageGenNode",
                        "stage": "image",
                        "data": {"displayName": "商品英雄镜头"},
                    }
                ],
                "edges": [],
                "external_edges": [
                    {
                        "source": "existing-product-node",
                        "target": "hero-shot",
                        "link_type": "media_input_for",
                    }
                ],
            }
        }
    )

    assert result["ok"] is True
    assert {
        "type": "create_edge",
        "source": "existing-product-node",
        "target": "hero-shot",
        "link_type": "media_input_for",
    } in result["commands"]


def test_compact_workflow_intent_compiles_before_canvas_bridge(monkeypatch):
    plugin = _load_plugin_module()
    intent = {"skill_id": "video-ad", "user_goal": "制作五镜广告"}
    plan = {"schema_version": "freezone_workflow_plan.v1", "nodes": []}
    commands = [{"type": "create_node", "node_type": "textAnnotationNode"}]
    captured = {}

    monkeypatch.setattr(
        plugin,
        "compile_workflow_intent",
        lambda value: {"ok": value is intent, "plan": plan},
    )
    monkeypatch.setattr(
        plugin,
        "build_workflow_graph_commands",
        lambda args: {"ok": args["plan"] is plan, "commands": commands},
    )

    def fake_emit(project, canvas, emitted, **kwargs):
        captured.update(
            {"project": project, "canvas": canvas, "commands": emitted, "kwargs": kwargs}
        )
        return "created-from-intent"

    monkeypatch.setattr(plugin, "_emit_canvas_commands", fake_emit)

    result = plugin._handle_create_workflow_from_intent(
        {"project_id": "project-a", "canvas_id": "canvas-a", "intent": intent}
    )

    assert result == "created-from-intent"
    assert captured["commands"] == commands
    assert captured["kwargs"]["allow_dynamic_workflow_batch"] is True


def test_workflow_draft_can_be_prepared_patched_and_confirmed_once(monkeypatch, tmp_path):
    plugin = _load_plugin_module()
    monkeypatch.setenv("DRAMACLAW_WORKFLOW_DRAFT_DIR", str(tmp_path))
    emitted = []

    def fake_compile(intent):
        items = list(intent.get("items") or [])
        nodes = [
            {
                "id": "workflow_input",
                "name": "用户需求",
                "node_type": "textAnnotationNode",
                "stage": "input",
            },
            *[
                {
                    "id": f"shot_{index + 1}",
                    "name": str(item),
                    "node_type": "videoNode",
                    "stage": "video",
                }
                for index, item in enumerate(items)
            ],
        ]
        return {
            "ok": True,
            "skill_id": intent["skill_id"],
            "node_count": len(nodes),
            "edge_count": max(0, len(nodes) - 1),
            "plan": {
                "summary": intent["user_goal"],
                "inputs": dict(intent.get("inputs") or {}),
                "creative_settings": dict(intent.get("creative_settings") or {}),
                "phases": ["脚本", "视频"],
                "nodes": nodes,
                "edges": [],
            },
        }

    monkeypatch.setattr(plugin, "compile_workflow_intent", fake_compile)
    monkeypatch.setattr(
        plugin,
        "build_workflow_graph_commands",
        lambda args: {
            "ok": True,
            "commands": [
                {
                    "type": "create_node",
                    "node_type": "textAnnotationNode",
                    "data": {"displayName": "用户需求"},
                }
            ],
        },
    )

    def fake_emit(project, canvas, commands, **kwargs):
        emitted.append((project, canvas, commands, kwargs))
        return {
            "ok": True,
            "canvas_apply_status": "applied",
            "applied": True,
        }

    monkeypatch.setattr(plugin, "_emit_canvas_commands", fake_emit)
    prepared = plugin._handle_prepare_workflow_draft(
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "intent": {
                "skill_id": "video-ad",
                "user_goal": "制作广告",
                "items": ["开场", "卖点"],
                "creative_settings": {
                    "aesthetic": {
                        "label": "王家卫电影感",
                        "prompt_guide": "霓虹色与手持摄影",
                    },
                    "recipe_extensions": ["lengyi-shotlist"],
                    "anchor_bindings": [
                        {
                            "node_id": "character-node",
                            "label": "女主角",
                            "target_item_ids": ["shot_1"],
                        }
                    ],
                },
            },
            "run_after_create": True,
        }
    )

    assert prepared["ok"] is True
    assert prepared["revision"] == 1
    assert prepared["preview"]["node_count"] == 3
    assert prepared["preview"]["creative_settings"] == {
        "uses_skill_defaults": False,
        "aesthetic": "王家卫电影感",
        "recipe_extensions": ["lengyi-shotlist"],
        "anchors": [
            {
                "label": "女主角",
                "node_id": "character-node",
                "target_item_ids": ["shot_1"],
            }
        ],
    }
    assert prepared["run_after_create"] is True

    patched = plugin._handle_patch_workflow_draft(
        {
            "draft_id": prepared["draft_id"],
            "expected_revision": 1,
            "changes": {"items": ["开场", "卖点", "收尾"]},
        }
    )

    assert patched["ok"] is True
    assert patched["revision"] == 2
    assert patched["preview"]["node_count"] == 4

    stale_patch = plugin._handle_patch_workflow_draft(
        {
            "draft_id": prepared["draft_id"],
            "expected_revision": 1,
            "changes": {"include_audio": False},
        }
    )
    confirmed = plugin._handle_confirm_workflow_draft(
        {"draft_id": prepared["draft_id"], "revision": 2}
    )
    repeated = plugin._handle_confirm_workflow_draft(
        {"draft_id": prepared["draft_id"], "revision": 2}
    )

    assert stale_patch["status"] == "workflow_draft_revision_conflict"
    assert confirmed["ok"] is True
    assert len(emitted) == 1
    assert emitted[0][0:2] == ("project-a", "canvas-a")
    assert repeated["status"] == "workflow_draft_already_confirmed"


def test_workflow_draft_concurrent_confirmation_emits_once(monkeypatch, tmp_path):
    plugin = _load_plugin_module()
    monkeypatch.setenv("DRAMACLAW_WORKFLOW_DRAFT_DIR", str(tmp_path))
    compiled = {
        "ok": True,
        "skill_id": "video-ad",
        "edge_count": 0,
        "plan": {
            "summary": "广告",
            "inputs": {},
            "phases": [],
            "nodes": [
                {
                    "id": "input",
                    "name": "输入",
                    "node_type": "textAnnotationNode",
                    "stage": "input",
                }
            ],
            "edges": [],
        },
    }
    monkeypatch.setattr(plugin, "compile_workflow_intent", lambda _intent: compiled)
    monkeypatch.setattr(
        plugin,
        "build_workflow_graph_commands",
        lambda args: {
            "ok": True,
            "commands": [{"type": "create_node", "node_type": "textAnnotationNode"}],
            "workflow_instance_id": args["workflow_instance_id"],
        },
    )
    started = threading.Event()
    release = threading.Event()
    emitted = []

    def fake_emit(*args, **kwargs):
        emitted.append((args, kwargs))
        started.set()
        assert release.wait(timeout=5)
        return {"ok": True, "canvas_apply_status": "applied", "applied": True}

    monkeypatch.setattr(plugin, "_emit_canvas_commands", fake_emit)
    prepared = plugin._handle_prepare_workflow_draft(
        {"intent": {"skill_id": "video-ad", "user_goal": "广告"}}
    )
    confirm_args = {"draft_id": prepared["draft_id"], "revision": 1}

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(plugin._handle_confirm_workflow_draft, confirm_args)
        assert started.wait(timeout=5)
        second = executor.submit(plugin._handle_confirm_workflow_draft, confirm_args)
        second_result = second.result(timeout=5)
        release.set()
        first_result = first.result(timeout=5)

    assert first_result["ok"] is True
    assert second_result["status"] == "workflow_draft_confirmation_in_progress"
    assert len(emitted) == 1


def test_workflow_draft_timeout_retry_reuses_instance_id(monkeypatch, tmp_path):
    plugin = _load_plugin_module()
    monkeypatch.setenv("DRAMACLAW_WORKFLOW_DRAFT_DIR", str(tmp_path))
    compiled = {
        "ok": True,
        "skill_id": "video-ad",
        "edge_count": 0,
        "plan": {
            "summary": "广告",
            "inputs": {},
            "phases": [],
            "nodes": [
                {
                    "id": "input",
                    "name": "输入",
                    "node_type": "textAnnotationNode",
                    "stage": "input",
                }
            ],
            "edges": [],
        },
    }
    monkeypatch.setattr(plugin, "compile_workflow_intent", lambda _intent: compiled)
    built_instance_ids = []

    def fake_build(args):
        built_instance_ids.append(args["workflow_instance_id"])
        return {
            "ok": True,
            "commands": [{"type": "create_node", "node_type": "textAnnotationNode"}],
        }

    monkeypatch.setattr(plugin, "build_workflow_graph_commands", fake_build)
    emitted = []

    def fake_emit(*args, **kwargs):
        emitted.append((args, kwargs))
        return {"ok": True, "canvas_apply_status": "timeout", "applied": False}

    monkeypatch.setattr(plugin, "_emit_canvas_commands", fake_emit)
    prepared = plugin._handle_prepare_workflow_draft(
        {"intent": {"skill_id": "video-ad", "user_goal": "广告"}}
    )
    confirm_args = {"draft_id": prepared["draft_id"], "revision": 1}

    first = plugin._handle_confirm_workflow_draft(confirm_args)
    repeated = plugin._handle_confirm_workflow_draft(confirm_args)

    assert first["canvas_apply_status"] == "timeout"
    assert repeated["canvas_apply_status"] == "timeout"
    assert len(emitted) == 2
    assert built_instance_ids == [prepared["draft_id"], prepared["draft_id"]]


def test_workflow_draft_patch_rejects_skill_replacement(monkeypatch, tmp_path):
    plugin = _load_plugin_module()
    monkeypatch.setenv("DRAMACLAW_WORKFLOW_DRAFT_DIR", str(tmp_path))
    compiled = {
        "ok": True,
        "skill_id": "video-ad",
        "edge_count": 0,
        "plan": {
            "summary": "广告",
            "inputs": {},
            "phases": [],
            "nodes": [
                {
                    "id": "input",
                    "name": "输入",
                    "node_type": "textAnnotationNode",
                    "stage": "input",
                }
            ],
            "edges": [],
        },
    }
    monkeypatch.setattr(plugin, "compile_workflow_intent", lambda _intent: compiled)
    prepared = plugin._handle_prepare_workflow_draft(
        {"intent": {"skill_id": "video-ad", "user_goal": "广告"}}
    )

    result = plugin._handle_patch_workflow_draft(
        {
            "draft_id": prepared["draft_id"],
            "expected_revision": 1,
            "changes": {"skill_id": "short-drama"},
        }
    )

    assert result["ok"] is False
    assert result["status"] == "invalid_workflow_draft_patch"
    assert result["unsupported_fields"] == ["skill_id"]


def test_workflow_graph_can_run_validated_nodes_after_create():
    plugin = _load_plugin_module()
    built = plugin.build_workflow_graph_commands(
        {
            "plan": {
                "schema_version": "freezone_workflow_plan.v1",
                "workflow_type": "dynamic.example",
                "nodes": [
                    {"id": "brief", "node_type": "textAnnotationNode"},
                    {"id": "image", "node_type": "imageGenNode"},
                ],
                "edges": [
                    {"source": "brief", "target": "image", "link_type": "prompt_for"}
                ],
            },
            "run_after_create": True,
        }
    )

    assert built["ok"] is True
    assert built["workflow_instance_id"].startswith("workflow_plan_")
    create_commands = [
        command for command in built["commands"] if command["type"] == "create_node"
    ]
    assert [command["data"]["workflowPlanNodeId"] for command in create_commands] == [
        "brief",
        "image",
    ]
    assert {
        command["data"]["workflowInstanceId"] for command in create_commands
    } == {built["workflow_instance_id"]}
    assert built["commands"][-1] == {
        "type": "run_workflow",
        "node_ids": ["brief", "image"],
        "scope": "selection",
    }


def test_workflow_graph_defaults_speech_audio_to_preset_voice():
    plugin = _load_plugin_module()
    built = plugin.build_workflow_graph_commands(
        {
            "plan": {
                "schema_version": "freezone_workflow_plan.v1",
                "workflow_type": "dynamic.audio",
                "nodes": [
                    {
                        "id": "narration",
                        "node_type": "audioNode",
                        "data": {"text": "欢迎观看"},
                    }
                ],
                "edges": [],
            }
        }
    )

    create_command = next(
        command for command in built["commands"] if command["type"] == "create_node"
    )
    assert create_command["data"]["audioKind"] == "speech"
    assert create_command["data"]["speechMode"] == "preset"
    assert create_command["data"]["presetModel"] == "edge-tts"
    assert create_command["data"]["presetVoice"] == "Serena"


def test_freezone_get_workflow_skill_returns_json_when_registry_summarizes(monkeypatch):
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)
    plugin = _load_plugin_module_with_registry_result(lambda value: "summarized")
    monkeypatch.setattr(plugin, "get_workflow_skill", catalog.get_workflow_skill)
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    loaded = handlers["freezone_get_workflow_skill"]({"skill_id": "ecommerce-product"})

    decoded = json.loads(loaded)
    assert decoded["ok"] is True
    assert decoded["skill_id"] == "ecommerce-product"
    assert isinstance(decoded["available_recipes"], list)


def test_freezone_get_workflow_skill_accepts_native_skill_id(monkeypatch):
    plugin = _load_plugin_module_with_registry_result(lambda value: "summarized")
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    loaded = handlers["freezone_get_workflow_skill"](
        {"skill_id": "pixar-ip-brand-ad-short-film"}
    )

    decoded = json.loads(loaded)
    assert decoded["ok"] is True
    assert decoded["skill_id"] == "pixar-ip-brand-ad-short-film"


def test_freezone_get_workflow_skill_compact_omits_recipe_definitions(monkeypatch):
    plugin = _load_plugin_module_with_registry_result(lambda value: "summarized")
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    loaded = handlers["freezone_get_workflow_skill"](
        {"skill_id": "pixar-ip-brand-ad-short-film", "compact": True}
    )

    decoded = json.loads(loaded)
    assert decoded["ok"] is True
    assert decoded["recipes"] == []
    assert decoded["recipe_definitions_omitted"] is True
    assert decoded["available_recipes"]
    assert decoded["planning_contract"]["mode"] == "dynamic_only"


def test_freezone_get_workflow_skill_records_structured_result_side_channel(monkeypatch, tmp_path):
    result_dir = tmp_path / "freezone-tool-results"
    monkeypatch.setenv("DRAMACLAW_FREEZONE_TOOL_RESULT_DIR", str(result_dir))
    catalog = _load_catalog_module()
    _install_minimal_builtin_catalog(monkeypatch, catalog)
    plugin = _load_plugin_module_with_registry_result(lambda value: "summarized")
    monkeypatch.setattr(plugin, "get_workflow_skill", catalog.get_workflow_skill)
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    handlers["freezone_get_workflow_skill"]({"skill_id": "ecommerce-product"})

    files = list(result_dir.glob("freezone_get_workflow_skill-*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["tool_name"] == "freezone_get_workflow_skill"
    assert payload["result"]["ok"] is True
    assert payload["result"]["skill_id"] == "ecommerce-product"
    assert isinstance(payload["result"]["available_recipes"], list)


def test_freezone_plugin_reads_saved_skill_and_recipe(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    def fake_request(method, path, *, query=None, body=None):  # noqa: ARG001
        assert method == "GET"
        if path == "/api/v1/freezone/agent-config/skills":
            return {
                "ok": True,
                "data": [
                    {"id": "other-skill"},
                    {"id": "home-culture-poster", "description": "完整 Skill 配置"},
                ],
            }
        if path == "/api/v1/freezone/agent-config/recipes":
            return {
                "ok": True,
                "data": [
                    {"id": "home-culture-poster-image", "system_prompt": "完整 Recipe 配置"},
                ],
            }
        raise AssertionError(path)

    monkeypatch.setattr(plugin, "_request", fake_request)

    skill = handlers["freezone_get_saved_skill"]({"skill_id": "home-culture-poster"})
    recipe = handlers["freezone_get_saved_recipe"]({"recipe_id": "home-culture-poster-image"})

    assert skill["ok"] is True
    assert skill["kind"] == "skills"
    assert skill["item"]["description"] == "完整 Skill 配置"
    assert recipe["ok"] is True
    assert recipe["kind"] == "recipes"
    assert recipe["item"]["system_prompt"] == "完整 Recipe 配置"


def test_freezone_plugin_clarification_tool_waits_for_frontend_result(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        assert project_id == "project-a"
        assert canvas_id == "canvas-a"
        assert event["type"] == "assistant.clarification.request"
        return "clarify-key-1"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):
        return {
            "ok": True,
            "status": "clarification_frontend_result",
            "tool_call_status": "completed",
            "clarification_status": "answered",
            "bridge_key": key,
            "answers": {
                "scope": {"option_ids": ["workflow"], "custom_text": "偏海报"},
            },
            "message": "User submitted clarification answers.",
        }

    monkeypatch.setattr(plugin, "clarification_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_clarification_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_clarification_result", fake_wait_result)

    result = handlers["freezone_request_user_clarification"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "clarification_id": "clarify_01",
            "title": "先确认方向",
            "questions": [
                {
                    "id": "scope",
                    "title": "主要做什么？",
                    "mode": "multiple",
                    "options": [{"id": "workflow", "label": "工作流自动化"}],
                    "allow_custom": True,
                }
            ],
            "allow_skip": True,
            "allow_recommended": True,
        }
    )

    assert result["ok"] is True
    assert result["status"] == "clarification_frontend_result"
    assert result["bridge_key"] == "clarify-key-1"
    assert result["answers"]["scope"]["option_ids"] == ["workflow"]
    assert pending_events[0]["event"]["type"] == "assistant.clarification.request"
    assert pending_events[0]["event"]["clarification_id"] == "clarify_01"
    assert pending_events[0]["event"]["questions"][0]["mode"] == "multiple"


def test_freezone_plugin_clarification_tool_generates_missing_id(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        assert project_id == "project-a"
        assert canvas_id == "canvas-a"
        assert event["clarification_id"].startswith("clarify_ss-distill-a_")
        return "clarify-key-2"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):
        return {
            "ok": True,
            "status": "clarification_frontend_result",
            "tool_call_status": "completed",
            "clarification_status": "answered",
            "bridge_key": key,
            "answers": {},
        }

    monkeypatch.setattr(plugin, "clarification_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_clarification_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_clarification_result", fake_wait_result)

    result = handlers["freezone_request_user_clarification"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "ss-distill-a",
            "questions": [
                {
                    "id": "scope",
                    "title": "主要做什么？",
                    "options": [{"id": "workflow", "label": "工作流自动化"}],
                }
            ],
        }
    )

    assert result["ok"] is True
    assert result["bridge_key"] == "clarify-key-2"
    generated_id = pending_events[0]["event"]["clarification_id"]
    assert generated_id.startswith("clarify_ss-distill-a_")
    assert len(generated_id.rsplit("_", 1)[-1]) == 8


def test_freezone_plugin_skill_studio_draft_tool_waits_for_frontend_result(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []
    wait_keys = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        assert project_id == "project-a"
        assert canvas_id == "canvas-a"
        assert event["type"].startswith("skill_studio.")
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):
        wait_keys.append((key, timeout_seconds))
        return {
            "ok": True,
            "status": "skill_studio_frontend_result",
            "tool_call_status": "completed",
            "skill_studio_status": "answered",
            "bridge_key": key,
            "selections": {"scope": "planning"},
            "message": "User submitted Skill Studio choices.",
        }

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    draft = handlers["freezone_present_agent_catalog_draft"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "mode": "create",
            "skill": {"id": "demo_skill"},
            "recipes": [{"id": "demo_recipe"}],
            "summary": "草稿已生成",
            "warnings": ["检查 ID"],
        }
    )

    assert draft["ok"] is True
    assert draft["status"] == "skill_studio_frontend_result"
    assert draft["bridge_key"] == "skill-studio-1"
    assert pending_events[0]["event"]["type"] == "skill_studio.draft"
    assert pending_events[0]["event"]["skill"]["id"] == "demo_skill"
    assert pending_events[0]["event"]["recipes"][0]["id"] == "demo_recipe"
    assert wait_keys[0][0] == "skill-studio-1"


def test_freezone_plugin_skill_studio_chunked_draft_tools_emit_progress_and_finish(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []
    wait_keys = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        assert project_id == "project-a"
        assert canvas_id == "canvas-a"
        assert event["type"].startswith("skill_studio.")
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):
        wait_keys.append((key, timeout_seconds))
        return {
            "ok": True,
            "status": "skill_studio_frontend_result",
            "tool_call_status": "completed",
            "skill_studio_status": "answered",
            "bridge_key": key,
            "message": "User submitted Skill Studio draft.",
        }

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    begin = handlers["freezone_begin_agent_catalog_draft"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "mode": "create",
            "summary": "正在生成公益短片 Skill",
            "expected_recipe_count": 2,
        }
    )
    skill = handlers["freezone_put_agent_catalog_skill"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "skill": {"id": "public-service-video", "description": "公益短片 Skill"},
        }
    )
    recipe_1 = handlers["freezone_put_agent_catalog_recipe"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "index": 0,
            "recipe": {"id": "story-outline", "name": "故事大纲"},
        }
    )
    recipe_2 = handlers["freezone_put_agent_catalog_recipe"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "index": 1,
            "recipe": {"id": "video-render", "name": "视频生成"},
        }
    )
    finished = handlers["freezone_finish_agent_catalog_draft"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
        }
    )

    assert begin["ok"] is True
    assert skill["ok"] is True
    assert "remaining Recipe chunks: 2" in skill["agent_instruction"]
    assert "Next call MUST be freezone_put_agent_catalog_recipe with index=0" in skill["agent_instruction"]
    assert "Do not call freezone_finish_agent_catalog_draft yet" in skill["agent_instruction"]
    assert recipe_1["ok"] is True
    assert recipe_2["ok"] is True
    assert finished["ok"] is True
    assert wait_keys == [("skill-studio-5", 600)]
    event_types = [item["event"]["type"] for item in pending_events]
    assert event_types == [
        "skill_studio.status",
        "skill_studio.status",
        "skill_studio.status",
        "skill_studio.status",
        "skill_studio.draft",
    ]
    assert pending_events[0]["event"]["status"] == "draft_begin"
    assert pending_events[1]["event"]["message"] == "已生成 Skill 基础配置"
    assert "Next call MUST be freezone_put_agent_catalog_recipe" in (
        pending_events[1]["event"]["debug"]["agent_instruction"]
    )
    assert pending_events[2]["event"]["message"] == "已生成 Recipe 1 / 2"
    assert "Do not write pseudo tool calls" in pending_events[2]["event"]["debug"]["agent_instruction"]
    assert pending_events[3]["event"]["message"] == "已生成 Recipe 2 / 2"
    draft_event = pending_events[-1]["event"]
    assert draft_event["skill"]["id"] == "public-service-video"
    assert [recipe["id"] for recipe in draft_event["recipes"]] == ["story-outline", "video-render"]


def test_freezone_plugin_chunked_draft_skill_result_directs_first_recipe_before_finish(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)

    handlers["freezone_begin_agent_catalog_draft"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "mode": "create",
            "expected_recipe_count": 5,
        }
    )
    result = handlers["freezone_put_agent_catalog_skill"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "skill": {"id": "public-service-video", "description": "公益短片 Skill"},
        }
    )

    instruction = result["agent_instruction"]
    assert "Skill chunk was delivered" in instruction
    assert "0 of 5 Recipe chunks submitted" in instruction
    assert "remaining Recipe chunks: 5" in instruction
    assert "Next call MUST be freezone_put_agent_catalog_recipe with index=0" in instruction
    assert "Do not answer with prose" in instruction
    assert "Do not write pseudo tool calls" in instruction
    assert "Call the actual tool directly" in instruction
    assert "Do not call freezone_finish_agent_catalog_draft yet" in instruction


def test_freezone_plugin_chunked_draft_skill_without_recipes_directs_finish(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)

    handlers["freezone_begin_agent_catalog_draft"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "mode": "create",
            "expected_recipe_count": 0,
        }
    )
    result = handlers["freezone_put_agent_catalog_skill"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "skill": {"id": "public-service-video", "description": "公益短片 Skill"},
        }
    )

    instruction = result["agent_instruction"]
    assert "no Recipe chunks are expected" in instruction
    assert "Next call MUST be freezone_finish_agent_catalog_draft" in instruction
    assert "freezone_put_agent_catalog_recipe" not in instruction


def test_freezone_plugin_chunked_draft_recipe_progress_without_expected_count_avoids_fake_total(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {"ok": True, "bridge_key": key, "skill_studio_status": "answered"}

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    handlers["freezone_begin_agent_catalog_draft"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "mode": "create",
        }
    )
    handlers["freezone_put_agent_catalog_recipe"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "index": 0,
            "recipe": {"id": "story-outline", "name": "故事大纲"},
        }
    )

    assert pending_events[-1]["event"]["message"] == "已生成第 1 个 Recipe"
    assert "recipe_count" not in pending_events[-1]["event"]


def test_freezone_plugin_chunked_draft_recipe_result_directs_next_recipe_before_finish(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)

    handlers["freezone_begin_agent_catalog_draft"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "mode": "create",
            "expected_recipe_count": 6,
        }
    )
    for index in range(4):
        handlers["freezone_put_agent_catalog_recipe"](
            {
                "project_id": "project-a",
                "canvas_id": "canvas-a",
                "skill_studio_session_id": "skill_studio_01",
                "index": index,
                "recipe": {"id": f"recipe-{index}", "name": f"Recipe {index}"},
            }
        )
    result = handlers["freezone_put_agent_catalog_recipe"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "index": 4,
            "recipe": {"id": "audio-layer", "name": "音频层"},
        }
    )

    instruction = result["agent_instruction"]
    assert "remaining Recipe chunks: 1" in instruction
    assert "freezone_put_agent_catalog_recipe" in instruction
    assert "index=5" in instruction
    assert "Do not answer with prose" in instruction
    assert "Do not write pseudo tool calls" in instruction
    assert "Call the actual tool directly" in instruction
    assert "Do not call skill_view" in instruction
    assert "Do not handle slash commands" in instruction
    assert "Do not call freezone_finish_agent_catalog_draft yet" in instruction


def test_freezone_plugin_chunked_draft_revision_preserves_unchanged_recipes(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {
            "ok": True,
            "status": "skill_studio_frontend_result",
            "tool_call_status": "completed",
            "skill_studio_status": "answered",
            "bridge_key": key,
        }

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    base_args = {
        "project_id": "project-a",
        "canvas_id": "canvas-a",
        "skill_studio_session_id": "skill_studio_01",
    }
    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "create", "expected_recipe_count": 2})
    handlers["freezone_put_agent_catalog_skill"]({**base_args, "skill": {"id": "public-service-video"}})
    handlers["freezone_put_agent_catalog_recipe"]({**base_args, "index": 0, "recipe": {"id": "story-outline"}})
    handlers["freezone_put_agent_catalog_recipe"]({**base_args, "index": 1, "recipe": {"id": "video-render"}})
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "edit", "expected_recipe_count": 2})
    handlers["freezone_put_agent_catalog_recipe"](
        {**base_args, "index": 1, "recipe": {"id": "video-render-v2"}}
    )
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    draft_events = [item["event"] for item in pending_events if item["event"]["type"] == "skill_studio.draft"]
    assert [recipe["id"] for recipe in draft_events[-1]["recipes"]] == [
        "story-outline",
        "video-render-v2",
    ]


def test_freezone_plugin_patch_draft_skill_keywords_preserves_recipes(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {"ok": True, "bridge_key": key, "skill_studio_status": "answered"}

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    base_args = {
        "project_id": "project-a",
        "canvas_id": "canvas-a",
        "skill_studio_session_id": "skill_studio_patch",
    }
    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "create", "expected_recipe_count": 2})
    handlers["freezone_put_agent_catalog_skill"](
        {
            **base_args,
            "skill": {
                "id": "public-service-video",
                "triggers": {"keywords": ["公益短片", "公益广告"]},
            },
        }
    )
    handlers["freezone_put_agent_catalog_recipe"]({**base_args, "index": 0, "recipe": {"id": "story-outline"}})
    handlers["freezone_put_agent_catalog_recipe"]({**base_args, "index": 1, "recipe": {"id": "video-render"}})
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "edit", "expected_recipe_count": 2})
    patched = handlers["freezone_patch_agent_catalog_draft"](
        {
            **base_args,
            "target": "skill",
            "patch": [
                {
                    "op": "replace",
                    "path": "/triggers/keywords",
                    "value": ["公益短片", "公益视频"],
                }
            ],
        }
    )
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    assert patched["ok"] is True
    assert patched["status"] == "draft_patch_applied"
    assert pending_events[-2]["event"]["message"] == "已更新 Skill 触发关键词"
    draft_events = [item["event"] for item in pending_events if item["event"]["type"] == "skill_studio.draft"]
    assert draft_events[-1]["skill"]["triggers"]["keywords"] == ["公益短片", "公益视频"]
    assert [recipe["id"] for recipe in draft_events[-1]["recipes"]] == ["story-outline", "video-render"]


def test_freezone_plugin_patch_draft_recipe_system_prompt_by_recipe_id(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {"ok": True, "bridge_key": key, "skill_studio_status": "answered"}

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    base_args = {
        "project_id": "project-a",
        "canvas_id": "canvas-a",
        "skill_studio_session_id": "skill_studio_patch_recipe",
    }
    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "create", "expected_recipe_count": 2})
    handlers["freezone_put_agent_catalog_skill"]({**base_args, "skill": {"id": "public-service-video"}})
    handlers["freezone_put_agent_catalog_recipe"](
        {**base_args, "index": 0, "recipe": {"id": "story-outline", "system_prompt": "旧大纲提示词"}}
    )
    handlers["freezone_put_agent_catalog_recipe"](
        {**base_args, "index": 1, "recipe": {"id": "video-script", "system_prompt": "旧脚本提示词"}}
    )
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "edit", "expected_recipe_count": 2})
    patched = handlers["freezone_patch_agent_catalog_draft"](
        {
            **base_args,
            "target": "recipe",
            "recipe_id": "video-script",
            "patch": [{"op": "replace", "path": "/system_prompt", "value": "新脚本提示词"}],
        }
    )
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    assert patched["ok"] is True
    assert pending_events[-2]["event"]["message"] == "已更新 Recipe：video-script"
    draft_events = [item["event"] for item in pending_events if item["event"]["type"] == "skill_studio.draft"]
    assert [recipe["system_prompt"] for recipe in draft_events[-1]["recipes"]] == [
        "旧大纲提示词",
        "新脚本提示词",
    ]


def test_freezone_plugin_patch_draft_removes_entire_recipe_by_recipe_id(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {"ok": True, "bridge_key": key, "skill_studio_status": "answered"}

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    base_args = {
        "project_id": "project-a",
        "canvas_id": "canvas-a",
        "skill_studio_session_id": "skill_studio_patch_remove_recipe",
    }
    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "create", "expected_recipe_count": 2})
    handlers["freezone_put_agent_catalog_skill"]({**base_args, "skill": {"id": "public-service-video"}})
    handlers["freezone_put_agent_catalog_recipe"]({**base_args, "index": 0, "recipe": {"id": "story-outline"}})
    handlers["freezone_put_agent_catalog_recipe"]({**base_args, "index": 1, "recipe": {"id": "video-script"}})

    result = handlers["freezone_patch_agent_catalog_draft"](
        {
            **base_args,
            "target": "recipe",
            "recipe_id": "video-script",
            "patch": [{"op": "remove", "path": ""}],
        }
    )
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    assert result["ok"] is True
    assert result["removed"] is True
    assert pending_events[-2]["event"]["message"] == "已移除 Recipe：video-script"
    draft_events = [item["event"] for item in pending_events if item["event"]["type"] == "skill_studio.draft"]
    assert [recipe["id"] for recipe in draft_events[-1]["recipes"]] == ["story-outline"]


def test_freezone_plugin_patch_draft_invalid_path_does_not_mutate(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {"ok": True, "bridge_key": key, "skill_studio_status": "answered"}

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    base_args = {
        "project_id": "project-a",
        "canvas_id": "canvas-a",
        "skill_studio_session_id": "skill_studio_patch_invalid",
    }
    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "create", "expected_recipe_count": 0})
    handlers["freezone_put_agent_catalog_skill"](
        {
            **base_args,
            "skill": {
                "id": "public-service-video",
                "triggers": {"keywords": ["公益短片", "公益广告"]},
            },
        }
    )

    result = handlers["freezone_patch_agent_catalog_draft"](
        {
            **base_args,
            "target": "skill",
            "patch": [{"op": "replace", "path": "/triggers/missing/0", "value": "公益视频"}],
        }
    )
    finished = handlers["freezone_finish_agent_catalog_draft"](base_args)

    assert result["ok"] is False
    assert result["status"] == "draft_patch_failed"
    assert finished["ok"] is True
    draft_events = [item["event"] for item in pending_events if item["event"]["type"] == "skill_studio.draft"]
    assert draft_events[-1]["skill"]["triggers"]["keywords"] == ["公益短片", "公益广告"]


def test_freezone_plugin_patch_draft_rejects_recipe_root_path_with_guidance(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {"ok": True, "bridge_key": key, "skill_studio_status": "answered"}

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    base_args = {
        "project_id": "project-a",
        "canvas_id": "canvas-a",
        "skill_studio_session_id": "skill_studio_patch_recipe_path",
    }
    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "create", "expected_recipe_count": 1})
    handlers["freezone_put_agent_catalog_skill"]({**base_args, "skill": {"id": "public-service-video"}})
    handlers["freezone_put_agent_catalog_recipe"](
        {
            **base_args,
            "index": 0,
            "recipe": {
                "id": "public-welfare-storyboard-images",
                "must_have_items": ["旧字段"],
            },
        }
    )

    result = handlers["freezone_patch_agent_catalog_draft"](
        {
            **base_args,
            "target": "recipe",
            "recipe_id": "public-welfare-storyboard-images",
            "patch": [
                {
                    "op": "replace",
                    "path": "/recipes/public-welfare-storyboard-images/must_have_items",
                    "value": ["新字段"],
                }
            ],
        }
    )
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    assert result["ok"] is False
    assert result["status"] == "draft_patch_failed"
    assert "target=recipe" in result["error"]
    assert "/must_have_items" in result["error"]
    assert "/recipes/public-welfare-storyboard-images/must_have_items" in result["error"]
    draft_events = [item["event"] for item in pending_events if item["event"]["type"] == "skill_studio.draft"]
    assert draft_events[-1]["recipes"][0]["must_have_items"] == ["旧字段"]


def test_freezone_plugin_patch_draft_removes_keyword_list_item(monkeypatch):
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}
    pending_events = []

    def fake_bridge_key(*, project_id, canvas_id, event):
        return f"skill-studio-{len(pending_events) + 1}"

    def fake_put_pending_event(**kwargs):
        pending_events.append(kwargs)

    def fake_wait_result(key, timeout_seconds):  # noqa: ARG001
        return {"ok": True, "bridge_key": key, "skill_studio_status": "answered"}

    monkeypatch.setattr(plugin, "skill_studio_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_skill_studio_event", fake_put_pending_event)
    monkeypatch.setattr(plugin, "wait_skill_studio_result", fake_wait_result)

    base_args = {
        "project_id": "project-a",
        "canvas_id": "canvas-a",
        "skill_studio_session_id": "skill_studio_patch_remove",
    }
    handlers["freezone_begin_agent_catalog_draft"]({**base_args, "mode": "create", "expected_recipe_count": 0})
    handlers["freezone_put_agent_catalog_skill"](
        {
            **base_args,
            "skill": {
                "id": "public-service-video",
                "triggers": {"keywords": ["公益短片", "公益广告", "纪录片"]},
            },
        }
    )
    result = handlers["freezone_patch_agent_catalog_draft"](
        {
            **base_args,
            "target": "skill",
            "patch": [{"op": "remove", "path": "/triggers/keywords/1"}],
        }
    )
    handlers["freezone_finish_agent_catalog_draft"](base_args)

    assert result["ok"] is True
    draft_events = [item["event"] for item in pending_events if item["event"]["type"] == "skill_studio.draft"]
    assert draft_events[-1]["skill"]["triggers"]["keywords"] == ["公益短片", "纪录片"]


def test_freezone_plugin_skill_studio_tool_schemas_expose_nested_contracts():
    plugin = _load_plugin_module()
    schemas = {name: schema for name, schema, _handler in plugin.TOOLS}

    clarification_schema = schemas["freezone_request_user_clarification"]["parameters"]
    clarification_description = schemas["freezone_request_user_clarification"]["description"]
    clarification_question_item = clarification_schema["properties"]["questions"]["items"]
    clarification_option_item = clarification_question_item["properties"]["options"]["items"]
    draft_schema = schemas["freezone_present_agent_catalog_draft"]["parameters"]
    begin_schema = schemas["freezone_begin_agent_catalog_draft"]["parameters"]
    put_recipe_schema = schemas["freezone_put_agent_catalog_recipe"]["parameters"]
    patch_schema = schemas["freezone_patch_agent_catalog_draft"]["parameters"]
    patch_description = schemas["freezone_patch_agent_catalog_draft"]["description"]
    finish_schema = schemas["freezone_finish_agent_catalog_draft"]["parameters"]
    finish_description = schemas["freezone_finish_agent_catalog_draft"]["description"]
    skill_schema = draft_schema["properties"]["skill"]
    recipe_item = draft_schema["properties"]["recipes"]["items"]
    input_parameter_schema = skill_schema["properties"]["input_parameters"]["items"]

    assert "including Skill Studio setup questions" in clarification_description
    assert "decide the next step from the current context" in clarification_description
    assert "Ask only the questions needed for the next decision" in clarification_schema["properties"]["questions"]["description"]
    assert "exactly one question" not in clarification_schema["properties"]["questions"]["description"]
    assert "freezone_present_skill_studio_questions" not in schemas
    assert clarification_schema["required"] == ["questions"]
    assert "Freezone will generate it automatically" in clarification_schema["properties"]["clarification_id"]["description"]
    assert "skill_studio_session_id" in clarification_schema["properties"]
    assert clarification_question_item["required"] == ["id", "title", "options"]
    assert clarification_option_item["required"] == ["id", "label"]
    assert "Do not include Recipe drafts inside skill" in skill_schema["description"]
    patch_field_description = patch_schema["properties"]["patch"]["description"]
    assert "Top-level field name must be patch" in patch_field_description
    assert "do not use operation, operations, or patches" in patch_field_description
    assert 'patch=[{"op":"remove","path":""}]' in patch_field_description
    assert "top-level recipes parameter" in draft_schema["properties"]["recipes"]["description"]
    assert begin_schema["required"] == ["skill_studio_session_id", "mode", "expected_recipe_count"]
    assert put_recipe_schema["required"] == ["skill_studio_session_id", "recipe"]
    assert patch_schema["required"] == ["skill_studio_session_id", "target", "patch"]
    assert patch_schema["properties"]["target"]["enum"] == ["skill", "recipe"]
    assert "local edits" in patch_description
    assert "recipe_id" in patch_schema["properties"]
    assert "target=recipe" in patch_schema["properties"]["patch"]["description"]
    assert "/system_prompt" in patch_schema["properties"]["patch"]["items"]["properties"]["path"]["description"]
    assert "/recipes/" in patch_schema["properties"]["patch"]["items"]["properties"]["path"]["description"]
    assert "Do not pass the full Skill/Recipe catalog" in finish_description
    assert "skill" not in finish_schema["properties"]
    assert "recipes" not in finish_schema["properties"]
    assert skill_schema["required"] == [
        "id",
        "name",
        "schema_version",
        "version",
        "description",
        "category",
        "triggers",
        "planning",
        "evaluation",
        "allowed_recipe_ids",
    ]
    assert input_parameter_schema["required"] == ["id", "label", "type", "required"]
    assert input_parameter_schema["properties"]["type"]["enum"] == [
        "single_select",
        "multi_select",
        "text",
        "number",
        "boolean",
    ]
    assert skill_schema["properties"]["triggers"]["required"] == ["keywords", "node_scopes"]
    assert skill_schema["properties"]["triggers"]["properties"]["node_scopes"]["items"]["enum"] == [
        "textGeneration",
        "imageGeneration",
        "videoGeneration",
        "audioGeneration",
    ]
    assert "workflow_templates" not in skill_schema["properties"]
    assert "videoCompose" not in skill_schema["properties"]["triggers"]["properties"]["node_scopes"]["items"]["enum"]
    assert skill_schema["properties"]["planning"]["required"] == [
        "planning_notes",
        "prompt_guide",
        "conduct_rules",
    ]
    assert "executable path summary" in skill_schema["properties"]["planning"]["properties"][
        "planning_notes"
    ]["description"]
    assert "hard execution rules" in skill_schema["properties"]["planning"]["properties"][
        "conduct_rules"
    ]["description"]
    assert "model_preferences" not in skill_schema["properties"]["planning"]["properties"]
    assert "default_aspect_ratios" not in skill_schema["properties"]["planning"]["properties"]
    assert skill_schema["properties"]["evaluation"]["required"] == [
        "rating_bands",
        "quality_threshold",
        "domain_constraints",
        "visual_review_items",
        "text_review_items",
    ]
    assert recipe_item["required"] == [
        "id",
        "name",
        "output_kind",
        "action_keys",
        "system_prompt",
        "must_have_items",
        "planning_prompt",
        "result_summary",
        "requires_source_media",
    ]
    recipe_system_prompt_description = recipe_item["properties"]["system_prompt"]["description"]
    assert "must never be the final downstream prompt itself" in recipe_system_prompt_description
    assert "重要：你的输出是一条提示词/指令" in recipe_system_prompt_description
    assert recipe_item["properties"]["output_kind"]["enum"] == ["text", "image", "video", "audio"]
    legacy_system_prompt_key = "system" + "Prompt"
    assert legacy_system_prompt_key not in json.dumps(recipe_item, ensure_ascii=False)
    legacy_recipe_keys = [
        "required" + "_elements",
        "planner" + "_cue",
        "output" + "_summary",
        "needs" + "_multimodal_input",
    ]
    for legacy_key in legacy_recipe_keys:
        assert legacy_key not in recipe_item["properties"]
    system_prompt_description = recipe_item["properties"]["system_prompt"]["description"]
    assert "节点" in system_prompt_description
    assert "提示词/指令" in system_prompt_description
    assert "不要直接生成最终内容" in system_prompt_description
    assert "送入对应节点" in system_prompt_description
    assert "终端生成型" not in system_prompt_description
    assert "不要把所有 Recipe 都写成 prompt compiler" not in system_prompt_description
    assert "角色设定" in system_prompt_description
    assert "输出结构" in system_prompt_description
    assert "禁止事项" in system_prompt_description
    planning_prompt_description = recipe_item["properties"]["planning_prompt"]["description"]
    result_summary_description = recipe_item["properties"]["result_summary"]["description"]
    assert "short business description" in planning_prompt_description
    assert "根据 X" in planning_prompt_description
    assert "Do not describe scheduling mechanics" in planning_prompt_description
    assert "short business description" in result_summary_description
    assert "Do not mention downstream execution" in result_summary_description


def test_freezone_get_workflow_skill_includes_current_user_agent_config(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setenv("DRAMACLAW_USER", "alice")

    def fake_list_user_agent_config_items(username, kind):
        assert username == "alice"
        if kind == "skills":
            return [
                {
                    "id": "custom-fruit-ad",
                    "name": "自定义水果广告",
                    "description": "用户导入的水果广告工作流",
                    "_catalog_source": "user",
                    "triggers": {"keywords": ["水果广告"]},
                    "allowed_recipe_ids": ["custom-fruit-outline"],
                }
            ]
        if kind == "recipes":
            return [
                {
                    "id": "custom-fruit-outline",
                    "name": "水果广告创意",
                    "_catalog_source": "user",
                    "generationType": "text",
                    "system_prompt": "输出一条提示词/指令。",
                }
            ]
        raise AssertionError(kind)

    monkeypatch.setattr(catalog, "list_user_agent_config_items", fake_list_user_agent_config_items)

    package = catalog.get_workflow_skill({"skill_id": "custom-fruit-ad"})

    assert package["ok"] is True
    assert package["skill_id"] == "custom-fruit-ad"
    assert package["source"] == "user"


def test_freezone_catalog_username_uses_local_for_ce(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setenv("ST_EDITION", "ce")
    monkeypatch.setenv("DRAMACLAW_USER", "dengyuxuan")
    monkeypatch.setenv("SUPERTALE_USER", "dengyuxuan")
    monkeypatch.setenv("USER", "tao")

    assert catalog._catalog_username() == "local"


def test_freezone_catalog_username_uses_login_user_for_supertale(monkeypatch):
    catalog = _load_catalog_module()
    monkeypatch.setenv("ST_EDITION", "ee")
    monkeypatch.setenv("DRAMACLAW_USER", "dengyuxuan")
    monkeypatch.setenv("USER", "tao")

    assert catalog._catalog_username() == "dengyuxuan"


def test_freezone_canvas_command_slim_result_omits_large_details():
    plugin = _load_plugin_module()

    summary = plugin._summarize_canvas_command_result(
        {
            "ok": True,
            "tool_call_status": "completed",
            "canvas_apply_status": "applied",
            "applied": True,
            "cancelled": False,
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "applied_count": 2,
            "opened_ui_actions": 0,
            "created_node_ids": ["node-a", "node-b"],
            "command_results": [{"very": "large"}],
            "message": "Frontend executor applied the canvas command.",
        },
        bridge_key="bridge-a",
        commands=[
            {
                "type": "create_node",
                "client_id": "outline",
                "node_type": "textAnnotationNode",
                "data": {"displayName": "生成广告创意大纲"},
            },
            {"type": "create_edge"},
            {
                "type": "create_node",
                "client_id": "storyboard",
                "node_type": "imageGenNode",
                "data": {"displayName": "多宫格分镜图"},
            },
        ],
    )

    assert summary["ok"] is True
    assert summary["created_node_count"] == 2
    assert summary["command_counts"] == {"create_node": 2, "create_edge": 1}
    assert summary["created_nodes"] == [
        {
            "client_id": "outline",
            "node_type": "textAnnotationNode",
            "displayName": "生成广告创意大纲",
        },
        {
            "client_id": "storyboard",
            "node_type": "imageGenNode",
            "displayName": "多宫格分镜图",
        },
    ]
    assert "copy every non-empty displayName" in summary["agent_instruction"]
    assert "created_node_ids" not in summary
    assert "command_results" not in summary


def test_freezone_canvas_command_slim_result_reports_background_acceptance():
    plugin = _load_plugin_module()

    summary = plugin._summarize_canvas_command_result(
        {
            "ok": True,
            "tool_call_status": "completed",
            "canvas_apply_status": "accepted",
            "applied": True,
            "cancelled": False,
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "message": "Frontend accepted the canvas workflow for background execution.",
        },
        bridge_key="bridge-workflow",
        commands=[{"type": "run_workflow", "scope": "canvas"}],
    )

    assert summary["ok"] is True
    assert summary["canvas_apply_status"] == "accepted"
    assert "workflow was accepted" in summary["agent_instruction"]
    assert "continuing on the canvas" in summary["agent_instruction"]
    assert "Do not claim generation is complete" in summary["agent_instruction"]


def test_freezone_canvas_command_slim_result_reports_node_action_submission():
    plugin = _load_plugin_module()

    summary = plugin._summarize_canvas_command_result(
        {
            "ok": True,
            "tool_call_status": "completed",
            "canvas_apply_status": "accepted",
            "applied": True,
            "cancelled": False,
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "message": "Canvas command was submitted to the canvas.",
        },
        bridge_key="bridge-node-action",
        commands=[
            {
                "type": "run_node_action",
                "node_id": "image-node",
                "action": "run_matting_tool",
            }
        ],
    )

    assert summary["ok"] is True
    assert summary["canvas_apply_status"] == "accepted"
    assert "submitted to the canvas" in summary["agent_instruction"]
    assert "do not say a tool was opened" in summary["agent_instruction"]
    assert "run nodes manually" not in summary["agent_instruction"]


def test_freezone_canvas_command_slim_result_reports_open_node_action_as_opened_panel():
    plugin = _load_plugin_module()

    summary = plugin._summarize_canvas_command_result(
        {
            "ok": True,
            "tool_call_status": "completed",
            "canvas_apply_status": "applied",
            "applied": True,
            "cancelled": False,
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "message": "Frontend executor applied the canvas command.",
        },
        bridge_key="bridge-open-light",
        commands=[
            {
                "type": "run_node_action",
                "node_id": "image-node",
                "action": "open_light_tool",
            }
        ],
    )

    assert summary["ok"] is True
    assert "panel has been opened" in summary["agent_instruction"]
    assert "processing" in summary["agent_instruction"]
    assert "submitted for generation" in summary["agent_instruction"]


def test_freezone_single_write_commands_request_slim_result(monkeypatch):
    plugin = _load_plugin_module()
    captured: dict[str, object] = {}

    def fake_emit_canvas_commands(project, canvas, commands, **kwargs):
        captured.update(
            {
                "project": project,
                "canvas": canvas,
                "commands": commands,
                "kwargs": kwargs,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(plugin, "_emit_canvas_commands", fake_emit_canvas_commands)

    result = plugin._handle_delete_nodes(
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "node_ids": ["node-a", "node-b"],
        }
    )

    assert result == {"ok": True}
    assert captured["commands"] == [
        {"type": "delete_nodes", "node_ids": ["node-a", "node-b"]}
    ]
    assert captured["kwargs"]["slim_result"] is True


def test_freezone_delete_nodes_can_clear_canvas_without_agent_listing_ids(monkeypatch):
    plugin = _load_plugin_module()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        plugin,
        "_resolve_canvas_scope_for_write",
        lambda project, canvas: ("project-a", "canvas-a", None),
    )
    monkeypatch.setattr(
        plugin,
        "_request",
        lambda method, path, **kwargs: {
            "ok": True,
            "data": {"nodes": [{"id": "node-a"}, {"id": "node-b"}]},
        },
    )

    def fake_emit_canvas_commands(project, canvas, commands, **kwargs):
        captured.update(
            {
                "project": project,
                "canvas": canvas,
                "commands": commands,
                "kwargs": kwargs,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(plugin, "_emit_canvas_commands", fake_emit_canvas_commands)

    result = plugin._handle_delete_nodes({"scope": "canvas"})

    assert result == {"ok": True}
    assert captured == {
        "project": "project-a",
        "canvas": "canvas-a",
        "commands": [{"type": "delete_nodes", "node_ids": ["node-a", "node-b"]}],
        "kwargs": {"slim_result": True},
    }


def test_freezone_delete_nodes_clear_canvas_is_idempotent(monkeypatch):
    plugin = _load_plugin_module()
    monkeypatch.setattr(
        plugin,
        "_resolve_canvas_scope_for_write",
        lambda project, canvas: ("project-a", "canvas-a", None),
    )
    monkeypatch.setattr(
        plugin,
        "_request",
        lambda method, path, **kwargs: {"ok": True, "data": {"nodes": []}},
    )

    result = plugin._handle_delete_nodes({"scope": "canvas"})

    assert result["ok"] is True
    assert result["canvas_apply_status"] == "already_empty"
    assert result["deleted_node_count"] == 0


def test_freezone_plugin_create_node_schema_hides_internal_node_types():
    plugin = _load_plugin_module()
    create_node_tool = next(
        (schema for name, schema, _handler in plugin.TOOLS if name == "freezone_create_node"),
        None,
    )
    add_next_tool = next(
        (schema for name, schema, _handler in plugin.TOOLS if name == "freezone_add_next_node"),
        None,
    )
    emit_tool = next(
        (schema for name, schema, _handler in plugin.TOOLS if name == "freezone_emit_canvas_command"),
        None,
    )
    group_tool = next(
        (schema for name, schema, _handler in plugin.TOOLS if name == "freezone_group_nodes"),
        None,
    )

    assert create_node_tool is not None
    assert add_next_tool is not None
    assert emit_tool is not None
    assert group_tool is not None
    enum_values = create_node_tool["parameters"]["properties"]["node_type"]["enum"]
    add_next_enum_values = add_next_tool["parameters"]["properties"]["node_type"]["enum"]
    emit_enum_values = (
        emit_tool["parameters"]["properties"]["commands"]["items"]["properties"]["node_type"]["enum"]
    )

    assert "imageGenNode" in enum_values
    assert "uploadNode" in enum_values
    assert "groupNode" not in enum_values
    assert "storyboardNode" not in enum_values
    assert "storyboardGenNode" not in enum_values
    assert "imageNode" not in enum_values
    assert "exportImageNode" not in enum_values
    assert "videoStoryNode" not in enum_values
    assert "skillNode" in enum_values
    assert enum_values == create_node_tool["parameters"]["properties"]["nodeType"]["enum"]
    assert add_next_enum_values == enum_values
    assert emit_enum_values == enum_values


def test_freezone_mcp_default_create_node_uses_frontend_bridge(monkeypatch):
    plugin = _load_plugin_module()
    pending_commands = []

    monkeypatch.setenv("DRAMACLAW_CANVAS_COMMAND_BRIDGE_DIR", "/tmp/dramaclaw-test-bridge")
    monkeypatch.setenv("DRAMACLAW_EXTERNAL_MCP", "1")
    monkeypatch.delenv("DRAMACLAW_MCP_DIRECT_CANVAS_APPLY", raising=False)

    def fake_bridge_key(*, project_id, canvas_id, commands):
        assert project_id == "project-a"
        assert canvas_id == "canvas-a"
        assert commands[0]["type"] == "create_node"
        return "bridge-key-1"

    def fake_put_pending_canvas_command(**kwargs):
        pending_commands.append(kwargs)

    def fake_wait_canvas_command_result(key, **kwargs):
        assert key == "bridge-key-1"
        assert "bridge_dir" in kwargs
        return {
            "ok": True,
            "tool_call_status": "completed",
            "canvas_apply_status": "applied",
            "applied": True,
            "cancelled": False,
            "command_results": [{"type": "create_node", "status": "applied"}],
        }

    monkeypatch.setattr(plugin, "canvas_command_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_canvas_command", fake_put_pending_canvas_command)
    monkeypatch.setattr(plugin, "wait_canvas_command_result", fake_wait_canvas_command_result)

    result = plugin._handle_create_node(
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "node_type": "videoNode",
            "data": {"displayName": "视频节点"},
        }
    )

    assert result["ok"] is True
    assert result["canvas_apply_status"] == "applied"
    assert pending_commands
    envelope = pending_commands[0]["envelope"]
    assert envelope["auto_apply_after_mcp_approval"] is True
    assert envelope["agent_id"] == "main"
    assert envelope["commands"][0]["type"] == "create_node"
    assert str(pending_commands[0]["bridge_dir"]).endswith("freezone_main")


def test_freezone_hermes_bridge_does_not_auto_apply_mcp_marker(monkeypatch):
    plugin = _load_plugin_module()
    pending_commands = []

    monkeypatch.delenv("DRAMACLAW_EXTERNAL_MCP", raising=False)
    monkeypatch.delenv("DRAMACLAW_MCP_DIRECT_CANVAS_APPLY", raising=False)

    def fake_bridge_key(*, project_id, canvas_id, commands):
        assert project_id == "project-a"
        assert canvas_id == "canvas-a"
        return "bridge-key-2"

    def fake_put_pending_canvas_command(**kwargs):
        pending_commands.append(kwargs)

    def fake_wait_canvas_command_result(key, **kwargs):
        assert key == "bridge-key-2"
        return {
            "ok": True,
            "tool_call_status": "completed",
            "canvas_apply_status": "applied",
            "applied": True,
            "cancelled": False,
            "command_results": [{"type": "create_node", "status": "applied"}],
        }

    monkeypatch.setattr(plugin, "canvas_command_bridge_key", fake_bridge_key)
    monkeypatch.setattr(plugin, "put_pending_canvas_command", fake_put_pending_canvas_command)
    monkeypatch.setattr(plugin, "wait_canvas_command_result", fake_wait_canvas_command_result)

    result = plugin._handle_create_node(
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "node_type": "videoNode",
        }
    )

    assert result["ok"] is True
    envelope = pending_commands[0]["envelope"]
    assert "auto_apply_after_mcp_approval" not in envelope
    assert "agent_id" not in envelope


def test_freezone_plugin_uses_frontend_link_type_catalog_values():
    plugin = _load_plugin_module()

    for tool_name in ("freezone_create_edge", "freezone_emit_canvas_command"):
        tool = next((schema for name, schema, _handler in plugin.TOOLS if name == tool_name), None)
        assert tool is not None
        schema_text = json.dumps(tool, ensure_ascii=False)
        assert "media_input_for" in schema_text
        assert "visual_reference_for" not in schema_text
        assert "source_media_for" not in schema_text


def test_freezone_plugin_mainline_projection_assets_schema_is_directional():
    plugin = _load_plugin_module()
    asset_tool = next(
        (schema for name, schema, _handler in plugin.TOOLS if name == "freezone_get_mainline_projection_assets"),
        None,
    )

    assert asset_tool is not None
    schema_text = json.dumps(asset_tool, ensure_ascii=False)

    assert "Mainline -> canvas only" in schema_text
    assert "freezone_open_mainline_projection" in schema_text
    assert "asset_kinds" in schema_text
    assert "query" in schema_text
    assert "limit" in schema_text
    enum_values = asset_tool["parameters"]["properties"]["asset_kinds"]["items"]["enum"]
    assert "character" in enum_values
    assert "identity" not in enum_values
    assert "portrait" not in enum_values


def test_freezone_plugin_mainline_projection_assets_normalizes_people_to_character(monkeypatch):
    plugin = _load_plugin_module()
    captured: dict[str, object] = {}

    def fake_request_canvas_context_from_frontend(**kwargs):
        captured.update(kwargs)
        return json.dumps({"ok": True}, ensure_ascii=False)

    monkeypatch.setattr(
        plugin,
        "_request_canvas_context_from_frontend",
        fake_request_canvas_context_from_frontend,
    )
    asset_handler = next(
        handler for name, _schema, handler in plugin.TOOLS if name == "freezone_get_mainline_projection_assets"
    )
    result = asset_handler(
        {
            "asset_kinds": ["identity", "portrait", "character_identity", "prop"],
            "query": "陈默",
            "limit": 12,
        }
    )

    assert json.loads(result)["ok"] is True
    assert captured["requests"] == [
        {
            "type": "mainline_projection_assets",
            "asset_kinds": ["character", "prop"],
            "query": "陈默",
            "limit": 12,
        }
    ]


def test_freezone_plugin_registers_with_hermes_acp_toolset():
    plugin = _load_plugin_module()

    assert plugin.REGISTER_TOOLSETS == ("hermes-acp",)


def test_freezone_plugin_register_call_exposes_node_tools_on_hermes_acp():
    plugin = _load_plugin_module()
    calls = []

    class FakeContext:
        def register_tool(self, **kwargs):
            calls.append(kwargs)

    plugin.register(FakeContext())

    by_name = {call["name"]: call for call in calls}
    assert by_name["freezone_create_node"]["toolset"] == "hermes-acp"
    assert by_name["freezone_emit_canvas_command"]["toolset"] == "hermes-acp"
    assert len(calls) == len(plugin.TOOLS)
