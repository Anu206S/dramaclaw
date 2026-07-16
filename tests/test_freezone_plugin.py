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


def _load_skill_runtime_module():
    freezone_dir = Path(__file__).resolve().parents[1] / ".hermes" / "plugins" / "freezone"
    sys.path.insert(0, str(freezone_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "test_freezone_skill_runtime",
            freezone_dir / "skill_runtime.py",
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(freezone_dir))


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
    assert "freezone_skill_list" in names
    assert "freezone_skill_start_session" in names
    assert "freezone_skill_update_config" in names
    assert "freezone_skill_confirm" in names
    assert "freezone_skill_status" in names
    assert "freezone_skill_cancel" in names
    assert "freezone_create_workflow_graph" in names
    assert "freezone_present_agent_catalog_draft" in names
    assert "freezone_begin_agent_catalog_draft" in names
    assert "freezone_put_agent_catalog_skill" in names
    assert "freezone_put_agent_catalog_recipe" in names
    assert "freezone_patch_agent_catalog_draft" in names
    assert "freezone_finish_agent_catalog_draft" in names
    assert "freezone_get_saved_skill" in names
    assert "freezone_get_saved_recipe" in names


def test_skill_session_questions_include_selectable_options_and_current_values():
    runtime = _load_skill_runtime_module()

    skill = {
        "parameters": [
            {
                "id": "duration",
                "label": "成片时长",
                "type": "single_select",
                "default": "30_60",
                "options": [
                    {"id": "30_60", "label": "超短片（30-60 秒）"},
                    {"id": "90", "label": "90 秒"},
                ],
            },
            {
                "id": "aspect_ratio",
                "label": "画幅比例",
                "type": "single_select",
                "default": "21:9",
                "options": [
                    {"id": "21:9", "label": "21:9 宽画幅"},
                    {"id": "9:16", "label": "9:16 竖屏"},
                ],
            },
            {
                "id": "voice_mode",
                "label": "配音模式",
                "type": "single_select",
                "default": "voiceover",
                "options": [
                    {"id": "voiceover", "label": "旁白"},
                    {"id": "silent", "label": "无配音"},
                ],
            },
        ]
    }

    questions = runtime._parameter_questions(
        skill,
        [],
        config={"duration": "90", "aspect_ratio": "21:9", "voice_mode": "silent"},
        include_all=True,
    )

    assert [question["id"] for question in questions] == ["duration", "aspect_ratio", "voice_mode"]
    assert questions[0]["selectable"] is True
    assert questions[0]["current_value"] == "90"
    assert questions[0]["default"] == "30_60"
    assert questions[0]["options"][1]["label"] == "90 秒"


def test_freezone_skill_session_runtime_is_isolated_from_workflow_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAMACLAW_SKILL_SESSION_DIR", str(tmp_path))
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    listed = handlers["freezone_skill_list"]({"include_workflows": True})

    assert listed["ok"] is True
    assert any(item["id"] == "video-ad" for item in listed["skills"])

    started = handlers["freezone_skill_start_session"](
        {
            "skill_id": "video-ad",
            "user_goal": "创建一个水果电商广告视频",
            "execution_mode": "auto",
            "project_id": "project-a",
            "canvas_id": "canvas-a",
        }
    )

    assert started["ok"] is True
    session = started["session"]
    assert session["skill_id"] == "video-ad"
    assert session["execution_mode"] == "auto"
    assert session["project_id"] == "project-a"
    assert session["canvas_id"] == "canvas-a"
    assert session["status"] == "waiting_config_confirmation"

    confirmed = handlers["freezone_skill_confirm"]({"session_id": session["session_id"]})

    assert confirmed["ok"] is True
    assert confirmed["status"] == "confirmed"
    plan = confirmed["execution_plan"]
    assert plan["schema_version"] == "freezone_skill_execution_plan.v1"
    assert plan["source"] == "workflow_template"
    assert plan["workflow_type"].startswith("catalog.video-ad.")
    assert plan["approval_policy"]["before_start_confirmation"] is True
    assert plan["approval_policy"]["per_step_confirmation"] is False
    assert plan["node_count"] > 0

    saved = handlers["freezone_skill_status"]({"session_id": session["session_id"]})
    assert saved["ok"] is True
    assert saved["session"]["status"] == "confirmed"


def test_interactive_skills_do_not_pollute_legacy_workflow_list():
    plugin = _load_plugin_module()
    handlers = {name: handler for name, _schema, handler in plugin.TOOLS}

    workflows = handlers["freezone_list_workflows"]({})

    workflow_types = {item["workflow_type"] for item in workflows["workflows"]}
    assert "catalog.a24-cinematic-short" not in workflow_types
    assert "catalog.cyberpunk-apocalypse-short" not in workflow_types
    assert "catalog.fruit-ecommerce-ad-skill" not in workflow_types
    assert "catalog.video_ad" in workflow_types
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
    assert pending_events[2]["event"]["message"] == "已生成 Recipe 1 / 2"
    assert pending_events[3]["event"]["message"] == "已生成 Recipe 2 / 2"
    draft_event = pending_events[-1]["event"]
    assert draft_event["skill"]["id"] == "public-service-video"
    assert [recipe["id"] for recipe in draft_event["recipes"]] == ["story-outline", "video-render"]


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
    workflow_step_schema = skill_schema["properties"]["workflow_templates"]["items"]["properties"][
        "steps"
    ]["items"]

    assert "including Skill Studio setup questions" in clarification_description
    assert "decide the next step from the current context" in clarification_description
    assert "Ask only the questions needed for the next decision" in clarification_schema["properties"]["questions"]["description"]
    assert "exactly one question" not in clarification_schema["properties"]["questions"]["description"]
    assert "freezone_present_skill_studio_questions" not in schemas
    assert clarification_schema["required"] == ["clarification_id", "questions"]
    assert clarification_question_item["required"] == ["id", "title", "options"]
    assert clarification_option_item["required"] == ["id", "label"]
    assert "Do not include Recipe drafts inside skill" in skill_schema["description"]
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
        "description",
        "category",
        "triggers",
        "planning",
        "evaluation",
    ]
    assert skill_schema["properties"]["triggers"]["required"] == ["keywords", "node_scopes"]
    assert skill_schema["properties"]["triggers"]["properties"]["node_scopes"]["items"]["enum"] == [
        "textGeneration",
        "imageGeneration",
        "videoGeneration",
        "audioGeneration",
    ]
    assert workflow_step_schema["properties"]["node_type"]["enum"] == [
        "textGeneration",
        "imageGeneration",
        "videoGeneration",
        "audioGeneration",
    ]
    assert "textAnnotationNode" not in workflow_step_schema["properties"]["node_type"]["enum"]
    assert "imageGenNode" not in workflow_step_schema["properties"]["node_type"]["enum"]
    assert "Do not use internal canvas node types" in workflow_step_schema["properties"][
        "node_type"
    ]["description"]
    assert skill_schema["properties"]["planning"]["required"] == [
        "planning_notes",
        "prompt_guide",
        "conduct_rules",
        "default_aspect_ratios",
    ]
    assert "model_preferences" not in skill_schema["properties"]["planning"]["properties"]
    aspect_schema_description = skill_schema["properties"]["planning"]["properties"][
        "default_aspect_ratios"
    ]["description"]
    aspect_schema = skill_schema["properties"]["planning"]["properties"]["default_aspect_ratios"]
    assert "imageGeneration" in aspect_schema_description
    assert "videoGeneration" in aspect_schema_description
    assert "16:9" in aspect_schema_description
    assert "5:4" in aspect_schema_description
    assert "Do not use auto" in aspect_schema_description
    assert aspect_schema["additionalProperties"] is False
    assert set(aspect_schema["properties"]) == {"imageGeneration", "videoGeneration"}
    assert "textGeneration" not in aspect_schema["properties"]
    assert "auto" not in aspect_schema["properties"]["imageGeneration"]["enum"]
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
                    "system_prompt": "输出一条提示词/指令。",
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


def test_freezone_catalog_resolver_exact_alias_skips_ambiguous_scoring():
    catalog = _load_catalog_module()

    resolved = catalog.resolve_catalog_workflow({"workflow_type": "text_to_video"})

    assert resolved["matched"] is True
    assert resolved["ambiguous"] is False
    assert resolved["recommended"]["workflow_type"] == "catalog.text_to_video.text_to_video"
    assert resolved["recommended"]["score"] == 99.0
    assert resolved["next_step"]["tool"] == "freezone_build_workflow_plan"


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
    assert "创建一个电商产品广告视频工作流" not in data["prompt"]
    assert data["prompt"].startswith("待生成内容：生成广告创意大纲")
    assert "workflowCatalog.promptBuilder" in data["prompt"]
    assert catalog["recipeSettings"]["outputKind"] == "text"
    assert catalog["recipeSettings"]["requiresSourceMedia"] is True
    assert catalog["promptBuilder"]["recipeId"] == "video-ad-creative-outline"
    assert catalog["promptBuilder"]["isPromptRecipe"] is True
    assert (
        catalog["promptBuilder"]["recipeRef"]
        == "agent_catalog/builtins/recipes/video-ad-creative-outline.json"
    )
    assert set(catalog["promptBuilder"]) == {
        "mode",
        "userGoal",
        "goalTemplate",
        "inputStrategy",
        "recipeId",
        "recipeName",
        "recipeRef",
        "isPromptRecipe",
    }

    image_node = next(
        item
        for item in plan["nodes"]
        if item["data"].get("workflowCatalog", {}).get("operationType")
        == "video-storyboard-grid"
    )
    assert "创建一个电商产品广告视频工作流" not in image_node["data"]["prompt"]
    assert "待生成图片" not in image_node["data"]["prompt"]
    assert "workflowCatalog.promptBuilder" not in image_node["data"]["prompt"]
    assert "提示词页" in image_node["data"]["prompt"]
    assert "画面中不要出现任何文字" in image_node["data"]["prompt"]
    assert "将广告脚本中的所有 Shot 合成为多宫格分镜图" in image_node["data"]["prompt"]


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


def test_freezone_workflow_graph_normalizes_legacy_catalog_model_ids():
    plugin = _load_plugin_module()

    built = plugin.build_workflow_graph_commands({"workflow_type": "catalog.video_ad"})

    assert built["ok"] is True
    create_nodes = [
        command
        for command in built["commands"]
        if command.get("type") == "create_node" and isinstance(command.get("data"), dict)
    ]
    models = [command["data"].get("model") for command in create_nodes]
    assert "nano-banana-2" not in models
    assert "omni-flash" not in models
    assert "newapi_nanobanana2" in models
    assert "newapi_seedance-2.0-fast" in models


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
