from __future__ import annotations

import importlib.util
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

    path = Path(__file__).resolve().parents[1] / ".hermes" / "plugins" / "dramaclaw" / "__init__.py"
    spec = importlib.util.spec_from_file_location("test_dramaclaw_plugin", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dramaclaw_plugin_adds_chat_error_without_replacing_task_error():
    plugin = _load_plugin_module()
    raw_error = "Content filter triggered. Finish reason: 'content_filter'"

    result = plugin._with_chat_error_hints(
        {
            "ok": True,
            "data": [
                {
                    "status": "failed",
                    "error": raw_error,
                    "metadata": {"provider_response_id": "resp_123"},
                }
            ],
        }
    )

    task = result["data"][0]
    assert task["error"] == raw_error
    assert task["chat_error"] == plugin.TEXT_CONTENT_FILTER_CHAT_ERROR
    assert "Do not quote the raw provider JSON" in task["agent_instruction"]


def test_dramaclaw_plugin_adds_voice_prereq_chat_error():
    plugin = _load_plugin_module()
    raw_error = "Beat 03 解说声线缺失：项目解说人声线缺失，请上传或录制解说人音频"

    result = plugin._with_chat_error_hints(
        {
            "status_code": 200,
            "ok": False,
            "code": "voice_prereq_required",
            "error": raw_error,
        }
    )

    assert result["error"] == raw_error
    assert "配音任务没有成功启动" in result["chat_error"]
    assert "虾塘" in result["chat_error"]
    assert raw_error in result["chat_error"]
    assert "Do not start another tool" in result["agent_instruction"]


def test_dramaclaw_plugin_adds_render_prereq_chat_error():
    plugin = _load_plugin_module()
    raw_error = (
        "Render 重生未生成可用图片（mode=1x1_2-3, beats=[1, 2, 3]）："
        "Render 模式需要草图但未找到覆盖 beat 1-1 的草图"
    )

    result = plugin._with_chat_error_hints(
        {
            "ok": True,
            "data": [
                {
                    "status": "failed",
                    "error": raw_error,
                }
            ],
        }
    )

    task = result["data"][0]
    assert task["error"] == raw_error
    assert "Render 任务没有生成可用图片" in task["chat_error"]
    assert "虾塘" in task["chat_error"]
    assert raw_error in task["chat_error"]
    assert "Do not start another tool" in task["agent_instruction"]


def test_dramaclaw_plugin_registers_freezone_canvas_tools():
    plugin = _load_plugin_module()

    names = {name for name, _schema, _handler in plugin.TOOLS}

    assert "dramaclaw_list_freezone_skills" in names
    assert "dramaclaw_run_freezone_skill" in names
    assert "dramaclaw_get_freezone_skill_result" in names
    assert "dramaclaw_list_freezone_canvases" in names
    assert "dramaclaw_get_freezone_canvas" in names
    assert "dramaclaw_save_freezone_canvas" in names
    assert "dramaclaw_delete_freezone_canvas" in names
    assert "dramaclaw_create_freezone_canvas_from_preset" in names


def test_dramaclaw_run_freezone_skill_uses_typed_endpoint(monkeypatch):
    plugin = _load_plugin_module()
    calls = []

    def fake_request(method, path, *, query=None, body=None):
        calls.append({"method": method, "path": path, "query": query, "body": body})
        return {"ok": True, "data": {"task_type": "freezone_gen"}}

    monkeypatch.setattr(plugin, "_request", fake_request)

    result = plugin._handle_run_freezone_skill(
        {
            "project_id": "demo",
            "skill_id": "freezone.sketch_from_context",
            "skill_node_id": "skill_1",
            "canvas_id": "canvas_a",
            "parameters": {"aspect_ratio": "2:3"},
            "resolved_inputs": [{"role": "beat_context", "node_id": "beat_1"}],
        }
    )

    assert result["ok"] is True
    assert calls == [
        {
            "method": "POST",
            "path": "/api/v1/projects/demo/freezone/skills/freezone.sketch_from_context/run",
            "query": None,
            "body": {
                "schema_version": "skill.v1",
                "skill_node_id": "skill_1",
                "canvas_id": "canvas_a",
                "idempotency_key": None,
                "parameters": {"aspect_ratio": "2:3"},
                "resolved_inputs": [{"role": "beat_context", "node_id": "beat_1"}],
            },
        }
    ]


def test_dramaclaw_save_freezone_canvas_puts_complete_payload(monkeypatch):
    plugin = _load_plugin_module()
    calls = []

    def fake_request(method, path, *, query=None, body=None):
        calls.append({"method": method, "path": path, "query": query, "body": body})
        return {"ok": True, "saved": True}

    monkeypatch.setattr(plugin, "_request", fake_request)

    result = plugin._handle_save_freezone_canvas(
        {
            "project_id": "demo",
            "canvas_id": "canvas_a",
            "payload": {
                "nodes": [],
                "edges": [],
                "base_revision": 3,
                "client_save_id": "save-1",
            },
        }
    )

    assert result["saved"] is True
    assert calls == [
        {
            "method": "PUT",
            "path": "/api/v1/projects/demo/freezone/canvases/canvas_a",
            "query": None,
            "body": {
                "nodes": [],
                "edges": [],
                "base_revision": 3,
                "client_save_id": "save-1",
                "canvas_id": "canvas_a",
                "project_id": "demo",
            },
        }
    ]


def test_dramaclaw_create_freezone_canvas_from_preset_uses_preset_endpoint(monkeypatch):
    plugin = _load_plugin_module()
    calls = []

    def fake_request(method, path, *, query=None, body=None):
        calls.append({"method": method, "path": path, "query": query, "body": body})
        return {"ok": True, "data": {"canvas_id": "beat-1"}}

    monkeypatch.setattr(plugin, "_request", fake_request)

    result = plugin._handle_create_freezone_canvas_from_preset(
        {
            "project_id": "demo",
            "scope": "beat",
            "episode": 1,
            "beat": 2,
            "primary_slot": "sketch",
        }
    )

    assert result["ok"] is True
    assert calls == [
        {
            "method": "POST",
            "path": "/api/v1/projects/demo/freezone/canvases:from-preset",
            "query": None,
            "body": {
                "scope": "beat",
                "episode": 1,
                "beat": 2,
                "primary_slot": "sketch",
            },
        }
    ]


def test_dramaclaw_freezone_mode_denies_mainline_writes(monkeypatch):
    plugin = _load_plugin_module()

    def fail_request(*_args, **_kwargs):
        raise AssertionError("_request should not be called")

    monkeypatch.setenv("DRAMACLAW_TOOL_MODE", "freezone_canvas")
    monkeypatch.setattr(plugin, "_request", fail_request)
    denied = plugin._guard_freezone_mainline_write(
        "dramaclaw_generate_sketches",
        plugin._handle_generate_sketches,
    )({"project_id": "demo", "episode": 1})

    assert denied["ok"] is False
    assert denied["code"] == "freezone_mainline_write_denied"
    assert "虾画画布" in denied["chat_error"]


def test_dramaclaw_freezone_mode_allows_canvas_writes(monkeypatch):
    plugin = _load_plugin_module()
    calls = []

    def fake_request(method, path, *, query=None, body=None):
        calls.append({"method": method, "path": path, "query": query, "body": body})
        return {"ok": True}

    monkeypatch.setenv("DRAMACLAW_TOOL_MODE", "freezone_canvas")
    monkeypatch.setattr(plugin, "_request", fake_request)

    result = plugin._guard_freezone_mainline_write(
        "dramaclaw_save_freezone_canvas",
        plugin._handle_save_freezone_canvas,
    )(
        {
            "project_id": "demo",
            "canvas_id": "canvas_a",
            "payload": {"nodes": [], "edges": []},
        }
    )

    assert result["ok"] is True
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == "/api/v1/projects/demo/freezone/canvases/canvas_a"
