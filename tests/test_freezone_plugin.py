from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


def _load_plugin_module():
    tools_module = types.ModuleType("tools")
    registry_module = types.ModuleType("tools.registry")
    registry_module.tool_error = lambda value: value
    registry_module.tool_result = lambda value: value
    sys.modules.setdefault("tools", tools_module)
    sys.modules.setdefault("tools.registry", registry_module)

    path = Path(__file__).resolve().parents[1] / ".hermes" / "plugins" / "freezone" / "__init__.py"
    spec = importlib.util.spec_from_file_location("test_freezone_plugin", path)
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


def test_freezone_plugin_registers_canvas_command_tools():
    plugin = _load_plugin_module()

    names = {name for name, _schema, _handler in plugin.TOOLS}

    assert "freezone_request_user_clarification" in names
    assert "freezone_emit_canvas_command" in names
    assert "freezone_create_node" in names
    assert "freezone_update_node_data" in names
    assert "freezone_run_node_action" in names
    assert "freezone_get_mainline_projection_assets" in names
    assert "freezone_list_workflows" in names
    assert "freezone_build_workflow_plan" in names
    assert "freezone_resolve_catalog_workflow" in names
    assert "freezone_create_workflow_graph" in names
    assert "freezone_present_skill_studio_questions" in names
    assert "freezone_present_agent_catalog_draft" in names


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


def test_freezone_plugin_skill_studio_tools_wait_for_frontend_results(monkeypatch):
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

    questions = handlers["freezone_present_skill_studio_questions"](
        {
            "project_id": "project-a",
            "canvas_id": "canvas-a",
            "skill_studio_session_id": "skill_studio_01",
            "title": "确定方向",
            "questions": [
                {
                    "id": "scope",
                    "title": "主要做什么？",
                    "options": [{"id": "planning", "label": "策划"}],
                }
            ],
            "allow_recommended": True,
            "allow_skip": True,
        }
    )
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

    assert questions["ok"] is True
    assert questions["status"] == "skill_studio_frontend_result"
    assert questions["bridge_key"] == "skill-studio-1"
    assert questions["selections"] == {"scope": "planning"}
    assert draft["ok"] is True
    assert draft["status"] == "skill_studio_frontend_result"
    assert draft["bridge_key"] == "skill-studio-2"
    assert pending_events[0]["event"]["type"] == "skill_studio.questions"
    assert pending_events[0]["event"]["questions"][0]["id"] == "scope"
    assert pending_events[1]["event"]["type"] == "skill_studio.draft"
    assert pending_events[1]["event"]["skill"]["id"] == "demo_skill"
    assert pending_events[1]["event"]["recipes"][0]["id"] == "demo_recipe"
    assert wait_keys[0][0] == "skill-studio-1"
    assert wait_keys[1][0] == "skill-studio-2"


def test_freezone_plugin_skill_studio_tool_schemas_expose_nested_contracts():
    plugin = _load_plugin_module()
    schemas = {name: schema for name, schema, _handler in plugin.TOOLS}

    questions_schema = schemas["freezone_present_skill_studio_questions"]["parameters"]
    question_item = questions_schema["properties"]["questions"]["items"]
    option_item = question_item["properties"]["options"]["items"]
    draft_schema = schemas["freezone_present_agent_catalog_draft"]["parameters"]
    skill_schema = draft_schema["properties"]["skill"]
    recipe_item = draft_schema["properties"]["recipes"]["items"]

    assert questions_schema["required"] == ["skill_studio_session_id", "questions"]
    assert question_item["required"] == ["id", "title", "options"]
    assert option_item["required"] == ["id", "label"]
    assert skill_schema["required"] == ["id", "description", "category"]
    assert recipe_item["required"] == ["id", "name", "output_kind", "systemPrompt"]
    assert recipe_item["properties"]["output_kind"]["enum"] == ["text", "image", "video", "audio"]


def test_freezone_catalog_includes_current_user_agent_config(monkeypatch):
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
                    "workflowTemplates": [
                        {
                            "id": "fruit-ad-full",
                            "name": "水果广告完整流程",
                            "condition": {"messageKeywords": ["水果", "广告"]},
                            "steps": [
                                {
                                    "id": "creative",
                                    "stepNumber": 1,
                                    "operationType": "custom-fruit-outline",
                                    "goalTemplate": "生成水果广告创意",
                                    "promptStrategy": "llm_refine",
                                    "inputStrategy": {"type": "none"},
                                }
                            ],
                        }
                    ],
                }
            ]
        if kind == "recipes":
            return [
                {
                    "id": "custom-fruit-outline",
                    "name": "水果广告创意",
                    "_catalog_source": "user",
                    "generationType": "text",
                    "systemPrompt": "输出一条提示词/指令。",
                }
            ]
        raise AssertionError(kind)

    monkeypatch.setattr(catalog, "list_user_agent_config_items", fake_list_user_agent_config_items)

    resolved = catalog.resolve_catalog_workflow({"user_goal": "创建一个水果广告工作流"})
    assert resolved["matched"] is True
    assert resolved["recommended"]["workflow_type"] == "catalog.custom_fruit_ad.fruit_ad_full"

    plan = catalog.build_catalog_workflow_plan(
        {
            "workflow_type": "catalog.custom_fruit_ad.fruit_ad_full",
            "user_goal": "创建一个水果广告工作流",
        }
    )
    assert plan["ok"] is True
    assert plan["nodes"][1]["data"]["workflowCatalog"]["promptBuilder"]["recipeRef"] == (
        "output/{user}/_account/freezone/agent_config/recipes/custom-fruit-outline.json"
    )


def test_freezone_list_workflows_exposes_catalog_source_type(monkeypatch):
    plugin = _load_plugin_module()
    monkeypatch.setenv("DRAMACLAW_USER", "local")
    monkeypatch.setenv("ST_EDITION", "ce")

    result = plugin._handle_list_workflows({})
    by_type = {item["workflow_type"]: item for item in result["workflows"]}

    assert by_type["catalog.text_to_image.text_to_image"]["type"] == "内置"
    assert by_type["catalog.text_to_image.text_to_image"]["catalog_source"] == "builtin"


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


def test_freezone_catalog_requires_user_selection_for_multiple_matched_skills(monkeypatch):
    catalog = _load_catalog_module()

    def fake_list_user_agent_config_items(_username, kind):
        if kind != "skills":
            return []
        return [
            {
                "id": "fruit-ad",
                "name": "水果广告",
                "triggers": {"keywords": ["广告"]},
                "workflowTemplates": [
                    {
                        "id": "detail",
                        "condition": {"messageKeywords": ["水果"]},
                        "steps": [],
                    }
                ],
            },
            {
                "id": "digital-ad",
                "name": "数码广告",
                "triggers": {"keywords": ["广告"]},
                "workflowTemplates": [
                    {
                        "id": "detail",
                        "condition": {"messageKeywords": ["详情页"]},
                        "steps": [],
                    }
                ],
            },
        ]

    monkeypatch.setattr(catalog, "list_user_agent_config_items", fake_list_user_agent_config_items)

    resolved = catalog.resolve_catalog_workflow({"user_goal": "创建一个水果广告详情页"})

    assert resolved["matched"] is True
    assert resolved["ambiguous"] is True
    assert resolved["matched_skill_count"] == 2
    assert resolved["next_step"]["requires_user_selection"] is True
    assert "tool" not in resolved["next_step"]
    assert set(resolved["next_step"]["candidate_workflow_types"]) == {
        "catalog.fruit_ad.detail",
        "catalog.digital_ad.detail",
    }


def test_freezone_plugin_resolves_catalog_workflow_without_canvas_write():
    plugin = _load_plugin_module()

    result = plugin._handle_resolve_catalog_workflow(
        {"user_goal": "我有一个女总裁复仇短剧创意，想按 skills recipes 配置生成工作流"}
    )

    assert result["ok"] is True
    assert result["matched"] is True
    assert result["recommended"]["workflow_type"].startswith("catalog.short_drama")
    assert result["ambiguous"] is True
    assert result["matched_skill_count"] > 1
    assert result["next_step"]["requires_user_selection"] is True
    assert "tool" not in result["next_step"]


def test_freezone_catalog_recipe_fields_are_separated_from_node_prompt():
    plugin = _load_plugin_module()

    plan = plugin.build_workflow_plan(
        {
            "workflow_type": "catalog.video_ad.video_ad_full",
            "user_goal": "创建一个电商产品广告视频工作流",
        }
    )

    assert plan["ok"] is True
    node = next(
        item
        for item in plan["nodes"]
        if item["data"].get("workflowCatalog", {}).get("operationType")
        == "video-ad-creative-outline"
    )
    data = node["data"]
    catalog = data["workflowCatalog"]

    assert "【Recipe Prompt】" not in data["prompt"]
    assert "【建议模型】" not in data["prompt"]
    assert "【输入依赖】" not in data["prompt"]
    assert "【用户需求】" not in data["prompt"]
    assert "【规划提示】" not in data["prompt"]
    assert "【期望输出】" not in data["prompt"]
    assert data["prompt"] == "创建一个电商产品广告视频工作流"
    assert catalog["recipeSettings"]["outputKind"] == "text"
    assert catalog["recipeSettings"]["requiresSourceMedia"] is True
    assert catalog["promptBuilder"]["recipeId"] == "video-ad-creative-outline"
    assert catalog["promptBuilder"]["isPromptRecipe"] is True
    assert (
        catalog["promptBuilder"]["recipeRef"]
        == "agent_catalog/builtins/recipes/video-ad-creative-outline.json"
    )
    assert "systemPrompt" not in catalog["promptBuilder"]

    image_node = next(
        item
        for item in plan["nodes"]
        if item["data"].get("workflowCatalog", {}).get("operationType")
        == "video-storyboard-grid"
    )
    assert "创建一个电商产品广告视频工作流" in image_node["data"]["prompt"]
    assert "任务：将广告脚本中的所有 Shot 合成为多宫格分镜图" in image_node["data"]["prompt"]


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
            {"type": "create_node"},
            {"type": "create_edge"},
            {"type": "create_node"},
        ],
    )

    assert summary["ok"] is True
    assert summary["created_node_count"] == 2
    assert summary["command_counts"] == {"create_node": 2, "create_edge": 1}
    assert "created_node_ids" not in summary
    assert "command_results" not in summary


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


def test_freezone_plugin_routes_registered_workflows_through_builder():
    plugin = _load_plugin_module()

    built = plugin.build_workflow_graph_commands({"workflow_type": "ad_video"})

    assert built["ok"] is True
    assert any(command["type"] == "create_node" for command in built["commands"])
    assert any(command["type"] == "group_nodes" for command in built["commands"])

    manual_result = plugin._handle_emit_canvas_command(
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

    assert manual_result["ok"] is False
    assert manual_result["status"] == "wrong_tool_registered_workflow"


def test_freezone_legacy_workflow_types_route_to_json_catalog():
    plugin = _load_plugin_module()

    expected = {
        "text_to_image": "catalog.text_to_image.text_to_image",
        "image_to_video": "catalog.image_to_video.image_to_video",
        "text_to_video": "catalog.text_to_video.text_to_video",
        "image_to_text": "catalog.image_to_text.image_to_text",
        "text_to_audio": "catalog.text_to_audio.text_to_audio",
        "product_video": "catalog.product_video.product_video",
        "mv": "catalog.music_video.music_video",
        "short_drama": "catalog.short_drama.short_drama_from_script",
        "ad_video": "catalog.video_ad.video_ad_full",
    }

    for workflow_type, expected_type in expected.items():
        plan = plugin.build_workflow_plan(
            {
                "workflow_type": workflow_type,
                "user_goal": "测试工作流",
            }
        )

        assert plan["ok"] is True
        assert plan["workflow_type"] == expected_type
        assert plan["nodes"]
        assert plan["edges"]


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

    assert plugin.REGISTER_TOOLSETS == ("freezone-acp",)


def test_freezone_plugin_register_call_exposes_node_tools_on_hermes_acp():
    plugin = _load_plugin_module()
    calls = []

    class FakeContext:
        def register_tool(self, **kwargs):
            calls.append(kwargs)

    plugin.register(FakeContext())

    by_name = {call["name"]: call for call in calls}
    assert by_name["freezone_create_node"]["toolset"] == "freezone-acp"
    assert by_name["freezone_emit_canvas_command"]["toolset"] == "freezone-acp"
    assert len(calls) == len(plugin.TOOLS)
