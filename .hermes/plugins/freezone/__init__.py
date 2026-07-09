"""Hermes 的 Freezone 画布工具入口。

这些工具名是虾画和 Agent 的稳定集成点。Handler 保持轻量：
读上下文、预校验、写命令都尽量转交给前端画布桥接层处理。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tools.registry import tool_error, tool_result

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

_REPO_SRC = Path(__file__).resolve().parents[3] / "src"
if _REPO_SRC.exists() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

_WORKFLOW_GRAPH_IMPORT_ERROR: Exception | None = None
try:
    from workflow_graph import (
        REGISTERED_WORKFLOWS,
        build_workflow_graph_commands,
        build_workflow_plan,
    )
except Exception as exc:
    _WORKFLOW_GRAPH_IMPORT_ERROR = exc
    REGISTERED_WORKFLOWS = []
    build_workflow_graph_commands = None
    build_workflow_plan = None

_JSON_WORKFLOW_CATALOG_IMPORT_ERROR: Exception | None = None
try:
    from json_workflow_catalog import registered_catalog_workflows, resolve_catalog_workflow
except Exception as exc:
    _JSON_WORKFLOW_CATALOG_IMPORT_ERROR = exc
    registered_catalog_workflows = None
    resolve_catalog_workflow = None

_CANVAS_COMMAND_BRIDGE_IMPORT_ERROR: Exception | None = None
try:
    from novelvideo.freezone.canvas_command_bridge import (
        canvas_command_bridge_key,
        canvas_context_bridge_key,
        clarification_bridge_key,
        put_pending_clarification_event,
        put_pending_canvas_command,
        put_pending_canvas_context,
        put_pending_skill_studio_event,
        wait_clarification_result,
        skill_studio_bridge_key,
        wait_canvas_command_result,
        wait_canvas_context_result,
        wait_skill_studio_result,
    )
except Exception as exc:
    _CANVAS_COMMAND_BRIDGE_IMPORT_ERROR = exc
    canvas_command_bridge_key = None
    canvas_context_bridge_key = None
    clarification_bridge_key = None
    put_pending_clarification_event = None
    put_pending_canvas_command = None
    put_pending_canvas_context = None
    put_pending_skill_studio_event = None
    wait_clarification_result = None
    skill_studio_bridge_key = None
    wait_canvas_command_result = None
    wait_canvas_context_result = None
    wait_skill_studio_result = None

TOOLSET = "freezone"
FREEZONE_ACP_TOOLSET = "freezone-acp"
REGISTER_TOOLSETS = (FREEZONE_ACP_TOOLSET,)
API_PREFIX = "/api/v1/"
try:
    DEFAULT_TIMEOUT_SECONDS = max(30, int(os.environ.get("DRAMACLAW_API_TIMEOUT_SECONDS", "120")))
except ValueError:
    DEFAULT_TIMEOUT_SECONDS = 120


def _available() -> bool:
    return bool(os.environ.get("DRAMACLAW_API_URL") and os.environ.get("DRAMACLAW_AGENT_TOKEN"))


def _base_url() -> str:
    value = os.environ.get("DRAMACLAW_API_URL", "").strip()
    if not value:
        raise ValueError("Freezone API URL is not configured")
    return value.rstrip("/")


def _token() -> str:
    value = os.environ.get("DRAMACLAW_AGENT_TOKEN", "").strip()
    if not value:
        raise ValueError("Freezone agent token is not configured")
    return value


def _default_project_id() -> str:
    return os.environ.get("DRAMACLAW_PROJECT_ID", "").strip()


def _default_canvas_id() -> str:
    return os.environ.get("DRAMACLAW_CANVAS_ID", "").strip()


def _surface() -> str:
    return (
        os.environ.get("DRAMACLAW_CHAT_SURFACE") or os.environ.get("SUPERTALE_CHAT_SURFACE") or ""
    ).strip()


def _project_from_args(args: dict[str, Any]) -> str:
    project = str(args.get("project_id") or args.get("project") or _default_project_id()).strip()
    if not project:
        raise ValueError("project_id is required and no current project context is configured")
    return project


def _canvas_from_args(args: dict[str, Any]) -> str:
    canvas = str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip()
    if not canvas:
        raise ValueError("canvas_id is required and no current canvas context is configured")
    return canvas


def _normalize_api_path(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path is required")
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("//"):
        raise ValueError("absolute URLs are not allowed; pass a Freezone API path")
    if not raw.startswith("/"):
        raw = f"/{raw}"
    if raw.startswith("/projects/") or raw.startswith("/freezone/"):
        raw = f"/api/v1{raw}"
    if not raw.startswith(API_PREFIX):
        raise ValueError("path must start with /api/v1/, /projects/, or /freezone/")
    if any(part == ".." for part in raw.split("/")):
        raise ValueError("path traversal is not allowed")
    return raw


def _query_string(params: Any) -> str:
    if not isinstance(params, dict) or not params:
        return ""
    cleaned = {
        str(key): value for key, value in params.items() if value is not None and value != ""
    }
    return f"?{urlencode(cleaned, doseq=True)}" if cleaned else ""


def _request(method: str, path: str, *, query: Any = None, body: Any = None) -> dict[str, Any]:
    api_path = _normalize_api_path(path)
    url = f"{_base_url()}{api_path}{_query_string(query)}"
    payload = None
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
        "User-Agent": "freezone-plugin/0.1.0",
    }
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url, data=payload, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return _decode_response(resp.status, text)
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": exc.code,
            "error": _response_error_text(text) or exc.reason,
            "data": _maybe_json(text),
        }
    except URLError as exc:
        return {"ok": False, "error": f"network_error: {exc.reason}"}


def _decode_response(status_code: int, text: str) -> dict[str, Any]:
    data = _maybe_json(text)
    if isinstance(data, dict):
        return {"status_code": status_code, **data}
    return {"ok": 200 <= status_code < 300, "status_code": status_code, "data": data}


def _maybe_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _response_error_text(text: str) -> str:
    data = _maybe_json(text)
    if isinstance(data, dict):
        for key in ("error", "message", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(data, str):
        return data[:500]
    return ""


def _scope_meta(project: str, canvas: str | None = None) -> dict[str, Any]:
    return {
        "project_id": project,
        "surface": _surface() or "freezone",
        "canvas_id": canvas or _default_canvas_id() or None,
    }


def _handle_canvas_ontology(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "canvas_ontology"}],
    )


def _handle_canvas_action_catalog(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "canvas_action_catalog"}],
    )


def _handle_canvas_command_catalog(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "canvas_command_catalog"}],
    )


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _emit_skill_studio_event(
    project: str | None,
    canvas: str | None,
    event: dict[str, Any],
) -> str:
    if (
        skill_studio_bridge_key is None
        or put_pending_skill_studio_event is None
        or wait_skill_studio_result is None
    ):
        return tool_error(
            "Skill Studio bridge is unavailable; cannot present the Freezone UI event. "
            f"Import error: {_CANVAS_COMMAND_BRIDGE_IMPORT_ERROR}"
        )
    key = skill_studio_bridge_key(project_id=project, canvas_id=canvas, event=event)
    put_pending_skill_studio_event(
        key=key,
        project_id=project,
        canvas_id=canvas,
        event=event,
    )
    try:
        timeout_seconds = max(
            1,
            int(os.environ.get("DRAMACLAW_SKILL_STUDIO_RESULT_TIMEOUT_SECONDS", "600")),
        )
    except ValueError:
        timeout_seconds = 600
    resolved = wait_skill_studio_result(key, timeout_seconds=timeout_seconds)
    if resolved is not None:
        return tool_result(resolved)
    return tool_result(
        {
            "ok": False,
            "status": "skill_studio_frontend_timeout",
            "tool_call_status": "completed",
            "skill_studio_status": "pending_user_input",
            "bridge_key": key,
            "project_id": project,
            "canvas_id": canvas,
            "type": event.get("type"),
            "skill_studio_session_id": event.get("skill_studio_session_id"),
            "message": "Skill Studio UI is still waiting for the user's frontend response.",
            "agent_instruction": (
                "Do not continue the Skill Studio flow or summarize the options until the "
                "frontend returns a Skill Studio tool result."
            ),
        }
    )


def _emit_clarification_event(
    project: str | None,
    canvas: str | None,
    event: dict[str, Any],
) -> str:
    if (
        clarification_bridge_key is None
        or put_pending_clarification_event is None
        or wait_clarification_result is None
    ):
        return tool_error(
            "Clarification bridge is unavailable; cannot present the Freezone UI event. "
            f"Import error: {_CANVAS_COMMAND_BRIDGE_IMPORT_ERROR}"
        )
    key = clarification_bridge_key(project_id=project, canvas_id=canvas, event=event)
    put_pending_clarification_event(
        key=key,
        project_id=project,
        canvas_id=canvas,
        event=event,
    )
    try:
        timeout_seconds = max(
            1,
            int(os.environ.get("DRAMACLAW_CLARIFICATION_RESULT_TIMEOUT_SECONDS", "600")),
        )
    except ValueError:
        timeout_seconds = 600
    resolved = wait_clarification_result(key, timeout_seconds=timeout_seconds)
    if resolved is not None:
        return tool_result(resolved)
    return tool_result(
        {
            "ok": False,
            "status": "clarification_frontend_timeout",
            "tool_call_status": "completed",
            "clarification_status": "pending_user_input",
            "bridge_key": key,
            "project_id": project,
            "canvas_id": canvas,
            "type": event.get("type"),
            "clarification_id": event.get("clarification_id"),
            "message": "Clarification UI is still waiting for the user's frontend response.",
            "agent_instruction": (
                "Do not continue or summarize the user's choices until the frontend returns "
                "a clarification tool result."
            ),
        }
    )


def _handle_request_user_clarification(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    clarification_id = str(args.get("clarification_id") or args.get("request_id") or "").strip()
    if not clarification_id:
        return tool_result(
            {
                "ok": False,
                "type": "assistant.clarification.request",
                "status": "clarification_id_required",
                "error": "clarification_id is required",
            }
        )
    questions = _safe_list(args.get("questions"))
    if not questions:
        return tool_result(
            {
                "ok": False,
                "type": "assistant.clarification.request",
                "status": "questions_required",
                "error": "questions must contain at least one question",
                "clarification_id": clarification_id,
            }
        )
    return _emit_clarification_event(
        project,
        canvas,
        {
            "type": "assistant.clarification.request",
            "clarification_id": clarification_id,
            "title": str(args.get("title") or "").strip(),
            "description": str(args.get("description") or "").strip(),
            "questions": questions,
            "allow_recommended": bool(args.get("allow_recommended", False)),
            "allow_skip": bool(args.get("allow_skip", True)),
        },
    )


def _handle_present_agent_catalog_draft(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    session_id = str(args.get("skill_studio_session_id") or args.get("session_id") or "").strip()
    if not session_id:
        return tool_result(
            {
                "ok": False,
                "type": "skill_studio.draft",
                "status": "skill_studio_session_id_required",
                "error": "skill_studio_session_id is required",
            }
        )
    mode = str(args.get("mode") or "create").strip() or "create"
    if mode not in {"create", "edit"}:
        mode = "create"
    skill = args.get("skill") if isinstance(args.get("skill"), dict) else {}
    recipes = _safe_list(args.get("recipes"))
    return _emit_skill_studio_event(
        project,
        canvas,
        {
            "type": "skill_studio.draft",
            "skill_studio_session_id": session_id,
            "mode": mode,
            "skill": skill,
            "recipes": recipes,
            "summary": str(args.get("summary") or "").strip(),
            "warnings": _safe_list(args.get("warnings")),
        },
    )


def _handle_selection(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "selection_detail"}],
    )


def _handle_node_detail(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    node_id = str(args.get("node_id") or args.get("nodeId") or "").strip()
    if not node_id:
        return tool_result(
            {"ok": False, "status": "node_id_required", "error": "node_id is required"}
        )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "node_detail", "node_id": node_id}],
    )


def _handle_neighbor_graph(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    node_id = str(args.get("node_id") or args.get("nodeId") or "").strip()
    if not node_id:
        return tool_result(
            {"ok": False, "status": "node_id_required", "error": "node_id is required"}
        )
    request: dict[str, Any] = {"type": "neighbor_graph", "node_id": node_id}
    if isinstance(args.get("depth"), (int, float)) and args["depth"] > 0:
        request["depth"] = args["depth"]
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[request],
    )


def _handle_node_action_catalog(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    node_id = str(args.get("node_id") or args.get("nodeId") or "").strip()
    if not node_id:
        return tool_result(
            {"ok": False, "status": "node_id_required", "error": "node_id is required"}
        )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "node_action_catalog", "node_id": node_id}],
    )


def _handle_node_create_schema(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    node_type = str(args.get("node_type") or args.get("nodeType") or "").strip()
    if not node_type:
        return tool_result(
            {"ok": False, "status": "node_type_required", "error": "node_type is required"}
        )
    if node_type not in _AGENT_CREATABLE_NODE_TYPE_VALUES:
        return tool_result(
            {
                "ok": False,
                "status": "invalid_node_type",
                "error": (
                    "node_type must be a directly creatable Freezone node type. "
                    "Use freezone_group_nodes/group_nodes for grouping existing nodes; "
                    "do not directly create or request create schemas for node types outside the "
                    "creatable values exposed by the command catalog."
                ),
            }
        )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "node_create_schema", "node_type": node_type}],
    )


def _handle_audio_voice_options(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    node_id = str(args.get("node_id") or args.get("nodeId") or "").strip()
    if not node_id:
        return tool_result(
            {"ok": False, "status": "node_id_required", "error": "node_id is required"}
        )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "audio_voice_options", "node_id": node_id}],
    )


def _handle_slot_candidates(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    slot_kind = str(args.get("slot_kind") or args.get("slotKind") or "").strip()
    request: dict[str, Any] = {"type": "slot_candidates"}
    if slot_kind:
        request["slot_kind"] = slot_kind
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[request],
    )


def _handle_mainline_projection_assets(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    request: dict[str, Any] = {"type": "mainline_projection_assets"}

    def _normalize_projection_asset_kind(value: Any) -> str | None:
        text = str(value).strip()
        if not text:
            return None
        if text in {
            "identity",
            "portrait",
            "character_identity",
            "character_portrait",
            "identity_portrait",
        }:
            return "character"
        return text

    asset_kinds = args.get("asset_kinds") or args.get("assetKinds")
    if isinstance(asset_kinds, list):
        values = [
            normalized
            for item in asset_kinds
            if (normalized := _normalize_projection_asset_kind(item))
        ]
        if values:
            request["asset_kinds"] = list(dict.fromkeys(values))
    asset_kind = str(args.get("asset_kind") or args.get("assetKind") or "").strip()
    if asset_kind and "asset_kinds" not in request:
        normalized = _normalize_projection_asset_kind(asset_kind)
        if normalized:
            request["asset_kinds"] = [normalized]
    query = str(args.get("query") or args.get("q") or "").strip()
    if query:
        request["query"] = query
    limit = args.get("limit")
    if isinstance(limit, (int, float)):
        request["limit"] = int(limit)
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[request],
    )


def _validation_payload(args: dict[str, Any]) -> dict[str, Any]:
    if isinstance(args.get("body"), dict):
        return dict(args["body"])
    if isinstance(args.get("envelope"), dict):
        return dict(args["envelope"])
    if isinstance(args.get("commands"), list):
        return {
            "schema_version": "canvas_chat_commands.v1",
            "commands": args["commands"],
        }
    return {}


def _handle_validate_commands(args: dict[str, Any], **_: Any) -> str:
    try:
        project = (
            str(args.get("project_id") or args.get("project") or _default_project_id()).strip()
            or None
        )
        canvas = (
            str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip()
            or None
        )
        payload = _validation_payload(args)
        if not payload:
            return tool_result(
                {
                    "ok": False,
                    "status": "empty_validation_payload",
                    "error": "commands, envelope, or body is required",
                    **(_scope_meta(project, canvas) if project and canvas else {}),
                }
            )
        commands = payload.get("commands")
        if isinstance(commands, list):
            shape_error = _validate_write_commands_shape(project, canvas, commands)
            if shape_error:
                return shape_error
        return _request_canvas_context_from_frontend(
            project=project,
            canvas=canvas,
            requests=[{"type": "validate_canvas_commands", "payload": payload}],
        )
    except Exception as exc:
        return tool_error(str(exc))


def _handle_summarize_canvas(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "canvas_summary"}],
    )


_FORBIDDEN_EDGE_FIELDS = (
    "role",
    "link_kind",
    "semantic_kind",
    "semantic_reason",
    "semantic_description",
)

_COMMAND_TYPES = {
    "create_node",
    "add_next_node",
    "update_node_data",
    "delete_nodes",
    "delete_edges",
    "create_edge",
    "layout_nodes",
    "group_nodes",
    "move_nodes",
    "select_nodes",
    "run_node_action",
    "open_mainline_projection",
}

_COMMAND_REQUIRED_FIELDS = {
    "create_node": ("node_type",),
    "add_next_node": ("source_node_id",),
    "update_node_data": ("node_id", "data"),
    "delete_nodes": ("node_ids",),
    "layout_nodes": ("mode",),
    "group_nodes": ("node_ids",),
    "select_nodes": ("node_ids",),
    "run_node_action": ("node_id", "action"),
    "open_mainline_projection": ("request",),
}


_WORKFLOW_LIKE_NODE_TYPES = {
    "imageGenNode",
    "videoNode",
    "audioNode",
    "videoComposeNode",
    "scriptNode",
    "storyboardGenNode",
}

_REGISTERED_WORKFLOW_HINTS = (
    "工作流",
    "workflow",
    "广告",
    "投放",
    "产品",
    "商品",
    "短剧",
    "小说",
    "故事",
    "mv",
    "音乐视频",
    "文生",
    "图生",
    "视频",
    "音频",
)


def _emit_command_error(project: str | None, canvas: str | None, status: str, error: str) -> str:
    return tool_result(
        {
            "ok": False,
            "status": status,
            "error": error,
            **_scope_meta(project or "", canvas),
        }
    )


def _command_text(command: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("client_id", "node_type", "label", "title", "displayName", "display_name"):
        value = command.get(key)
        if value is not None:
            values.append(str(value))
    data = command.get("data")
    if isinstance(data, dict):
        for key in ("displayName", "display_name", "title", "label", "prompt", "text", "content"):
            value = data.get(key)
            if value is not None:
                values.append(str(value))
    return "\n".join(values).lower()


def _looks_like_manual_registered_workflow_batch(commands: list[Any]) -> bool:
    object_commands = [command for command in commands if isinstance(command, dict)]
    create_commands = [
        command
        for command in object_commands
        if command.get("type") in {"create_node", "add_next_node"}
    ]
    if len(create_commands) < 3:
        return False
    workflow_like_count = sum(
        1 for command in create_commands if command.get("node_type") in _WORKFLOW_LIKE_NODE_TYPES
    )
    if workflow_like_count < 2:
        return False
    has_dependency_shape = any(
        command.get("type") in {"create_edge", "group_nodes", "layout_nodes", "select_nodes"}
        for command in object_commands
    )
    haystack = "\n".join(_command_text(command) for command in object_commands)
    has_registered_hint = any(hint in haystack for hint in _REGISTERED_WORKFLOW_HINTS)
    return (not has_dependency_shape) or has_registered_hint


def _validate_write_commands_shape(
    project: str | None,
    canvas: str | None,
    commands: list[Any],
) -> str | None:
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            return _emit_command_error(
                project,
                canvas,
                "invalid_command",
                f"commands[{index}] must be an object",
            )
        if command.get("schema_version") == "canvas_context_request.v1":
            return _emit_command_error(
                project,
                canvas,
                "wrong_tool",
                (
                    "canvas_context_request.v1 is read-only context retrieval. "
                    "Use a specific Freezone get_* context tool or freezone_validate_canvas_commands, "
                    "not a write tool."
                ),
            )
        if "command" in command and "type" not in command:
            return _emit_command_error(
                project,
                canvas,
                "invalid_command_schema",
                (
                    f"commands[{index}] uses legacy field 'command'. Use 'type' instead, "
                    "for example {'type': 'create_node', 'node_type': 'textAnnotationNode', 'data': {...}}."
                ),
            )
        command_type = command.get("type")
        if not isinstance(command_type, str) or not command_type.strip():
            return _emit_command_error(
                project,
                canvas,
                "invalid_command_schema",
                f"commands[{index}] missing required field 'type'.",
            )
        if command_type not in _COMMAND_TYPES:
            return _emit_command_error(
                project,
                canvas,
                "invalid_command_type",
                (
                    f"commands[{index}].type must be one of: {', '.join(sorted(_COMMAND_TYPES))}; "
                    f"got {command_type!r}."
                ),
            )
        if "nodeType" in command:
            return _emit_command_error(
                project,
                canvas,
                "invalid_command_schema",
                f"commands[{index}] uses legacy field 'nodeType'. Use snake_case 'node_type'.",
            )
        data = command.get("data")
        if isinstance(data, dict) and "nodeType" in data:
            return _emit_command_error(
                project,
                canvas,
                "invalid_command_schema",
                (
                    f"commands[{index}].data.nodeType is invalid. Put the canvas node type at "
                    "commands[index].node_type."
                ),
            )
        if "imageGenerationParams" in command or (
            isinstance(data, dict) and "imageGenerationParams" in data
        ):
            return _emit_command_error(
                project,
                canvas,
                "invalid_command_schema",
                (
                    f"commands[{index}] uses legacy imageGenerationParams. Flatten supported image node "
                    "fields into data, e.g. data.prompt, data.model, data.quality, data.aspectRatio."
                ),
            )
        missing_required = [
            field
            for field in _COMMAND_REQUIRED_FIELDS.get(command_type, ())
            if command.get(field) in (None, "", [])
        ]
        if missing_required:
            return _emit_command_error(
                project,
                canvas,
                "invalid_command_schema",
                f"commands[{index}] {command_type} missing required field(s): {', '.join(missing_required)}",
            )
        if command_type == "create_node" or (
            command_type == "add_next_node" and command.get("node_type") not in (None, "")
        ):
            node_type = str(command.get("node_type") or "").strip()
            if node_type not in _AGENT_CREATABLE_NODE_TYPE_VALUES:
                return _emit_command_error(
                    project,
                    canvas,
                    "invalid_node_type",
                    (
                        f"commands[{index}].node_type must be a directly creatable node type; "
                        f"got {node_type!r}. Use group_nodes/freezone_group_nodes to group existing "
                        "nodes, and only use creatable node types exposed by the command catalog."
                    ),
                )
        if command.get("type") == "create_edge":
            missing = [
                field for field in ("source", "target", "link_type") if not command.get(field)
            ]
            if missing:
                return _emit_command_error(
                    project,
                    canvas,
                    "invalid_create_edge",
                    f"commands[{index}] create_edge missing required field(s): {', '.join(missing)}",
                )
            forbidden = [field for field in _FORBIDDEN_EDGE_FIELDS if field in command]
            if forbidden:
                return _emit_command_error(
                    project,
                    canvas,
                    "invalid_create_edge",
                    (
                        f"commands[{index}] create_edge must use link_type only; "
                        f"remove legacy field(s): {', '.join(forbidden)}"
                    ),
                )
    return None


def _emit_canvas_commands(
    project: str | None,
    canvas: str | None,
    commands: list[Any],
    *,
    allow_registered_workflow_batch: bool = False,
    slim_result: bool = False,
) -> str:
    if not isinstance(commands, list) or not commands:
        return _emit_command_error(
            project, canvas, "empty_commands", "commands must be a non-empty array"
        )
    shape_error = _validate_write_commands_shape(project, canvas, commands)
    if shape_error:
        return shape_error
    if (
        not allow_registered_workflow_batch
        and _looks_like_manual_registered_workflow_batch(commands)
    ):
        return _emit_command_error(
            project,
            canvas,
            "wrong_tool_registered_workflow",
            (
                "This looks like a registered workflow being hand-written as canvas commands. "
                "Do not infer workflow nodes, edges, groups, or layout yourself. First call "
                "freezone_list_workflows to identify the workflow_type; if the user's request "
                "matches exactly one registered workflow, call freezone_create_workflow_graph "
                "with workflow_type/workflow_types. If it is ambiguous, ask the user to choose."
            ),
        )
    envelope = {
        "schema_version": "canvas_chat_commands.v1",
        **({"project_id": project} if project else {}),
        **({"canvas_id": canvas} if canvas else {}),
        "commands": commands,
    }
    if (
        canvas_command_bridge_key is not None
        and put_pending_canvas_command is not None
        and wait_canvas_command_result is not None
    ):
        key = canvas_command_bridge_key(project_id=project, canvas_id=canvas, commands=commands)
        put_pending_canvas_command(
            key=key,
            project_id=project,
            canvas_id=canvas,
            commands=commands,
            envelope=envelope,
        )
        try:
            timeout_seconds = max(
                1,
                int(os.environ.get("DRAMACLAW_CANVAS_COMMAND_RESULT_TIMEOUT_SECONDS", "600")),
            )
        except ValueError:
            timeout_seconds = 600
        resolved = wait_canvas_command_result(key, timeout_seconds=timeout_seconds)
        if resolved is not None:
            return tool_result(
                _summarize_canvas_command_result(
                    resolved,
                    bridge_key=key,
                    commands=commands,
                )
                if slim_result
                else resolved
            )
        return tool_result(
            {
                "ok": False,
                "tool_call_status": "completed",
                "canvas_apply_status": "pending_user_confirmation",
                "applied": False,
                "cancelled": False,
                "errors": ["Timed out waiting for frontend canvas command result."],
                "bridge_key": key,
                "message": "Canvas command is still waiting for frontend confirmation or apply result.",
                "agent_instruction": (
                    "Do not claim success yet. Wait for the frontend result or ask the user to "
                    "confirm whether the command should be retried."
                ),
            }
        )
    return tool_error(
        "Canvas command bridge is unavailable; cannot wait for frontend apply result. "
        f"Import error: {_CANVAS_COMMAND_BRIDGE_IMPORT_ERROR}"
    )


def _summarize_canvas_command_result(
    resolved: dict[str, Any],
    *,
    bridge_key: str,
    commands: list[Any],
) -> dict[str, Any]:
    command_counts: dict[str, int] = {}
    for command in commands:
        if not isinstance(command, dict):
            continue
        command_type = str(command.get("type") or "unknown").strip() or "unknown"
        command_counts[command_type] = command_counts.get(command_type, 0) + 1
    errors = resolved.get("errors") if isinstance(resolved.get("errors"), list) else []
    return {
        "ok": bool(resolved.get("ok")),
        "tool_call_status": resolved.get("tool_call_status") or "completed",
        "canvas_apply_status": resolved.get("canvas_apply_status"),
        "applied": bool(resolved.get("applied")),
        "cancelled": bool(resolved.get("cancelled")),
        "bridge_key": bridge_key,
        "project_id": resolved.get("project_id"),
        "canvas_id": resolved.get("canvas_id"),
        "applied_count": resolved.get("applied_count"),
        "opened_ui_actions": resolved.get("opened_ui_actions"),
        "created_node_count": len(resolved.get("created_node_ids") or []),
        "command_count": len(commands),
        "command_counts": command_counts,
        "error_count": len(errors),
        "errors": [str(item)[:240] for item in errors[:3]],
        "message": resolved.get("message") or "Canvas command finished.",
        "agent_instruction": resolved.get("agent_instruction") or (
            "Canvas command result has been summarized. Do not ask for or print the full commands."
        ),
    }


def _handle_emit_canvas_command(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    commands = args.get("commands")
    if commands is None and isinstance(args.get("body"), dict):
        commands = args["body"].get("commands")
    return _emit_canvas_commands(project, canvas, commands, slim_result=True)


def _handle_build_workflow_plan(args: dict[str, Any], **_: Any) -> str:
    if build_workflow_plan is None:
        return tool_error(
            "Freezone workflow plan builder is unavailable. "
            f"Import error: {_WORKFLOW_GRAPH_IMPORT_ERROR}"
        )
    return tool_result(build_workflow_plan(args))


def _handle_list_workflows(args: dict[str, Any], **_: Any) -> str:
    workflow_by_type: dict[str, dict[str, Any]] = {}
    for item in REGISTERED_WORKFLOWS:
        workflow_type = str(item.get("workflow_type") or "")
        if workflow_type:
            workflow_by_type[workflow_type] = item
    if registered_catalog_workflows is not None:
        try:
            for item in registered_catalog_workflows():
                workflow_type = str(item.get("workflow_type") or "")
                if workflow_type:
                    workflow_by_type[workflow_type] = item
        except Exception:
            pass
    workflows = [
        {
            "workflow_type": str(item.get("workflow_type") or ""),
            "label": str(item.get("label") or item.get("workflow_type") or ""),
            "aliases": item.get("aliases") if isinstance(item.get("aliases"), list) else [],
            "template_kind": item.get("template_kind") or item.get("builder") or "",
            "source": item.get("source") or "",
            "catalog_source": item.get("catalog_source") or "",
            "type": item.get("catalog_source_label") or (
                "内置" if item.get("source") == "workflow_json" else ""
            ),
        }
        for item in workflow_by_type.values()
        if item.get("workflow_type")
    ]
    workflows.sort(key=lambda item: item["workflow_type"])
    return tool_result({"ok": True, "count": len(workflows), "workflows": workflows})


def _handle_resolve_catalog_workflow(args: dict[str, Any], **_: Any) -> str:
    if resolve_catalog_workflow is None:
        return tool_error(
            "Freezone JSON workflow resolver is unavailable. "
            f"Import error: {_JSON_WORKFLOW_CATALOG_IMPORT_ERROR}"
        )
    return tool_result(resolve_catalog_workflow(args))


def _handle_create_workflow_graph(args: dict[str, Any], **_: Any) -> str:
    if build_workflow_graph_commands is None:
        return tool_error(
            "Freezone workflow graph builder is unavailable. "
            f"Import error: {_WORKFLOW_GRAPH_IMPORT_ERROR}"
        )
    built = build_workflow_graph_commands(args)
    if not built.get("ok"):
        return tool_result(built)
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    commands = built.get("commands")
    return _emit_canvas_commands(
        project,
        canvas,
        commands,
        allow_registered_workflow_batch=True,
        slim_result=True,
    )


def _position_from_args(args: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(args.get("position"), dict):
        return dict(args["position"])
    x = args.get("x")
    y = args.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return {"x": x, "y": y}
    return None


def _single_write_command(args: dict[str, Any], command: dict[str, Any]) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    return _emit_canvas_commands(project, canvas, [command], slim_result=True)


def _handle_create_node(args: dict[str, Any], **_: Any) -> str:
    node_type = str(args.get("node_type") or args.get("nodeType") or "").strip()
    if not node_type:
        return tool_result(
            {"ok": False, "status": "node_type_required", "error": "node_type is required"}
        )
    command: dict[str, Any] = {"type": "create_node", "node_type": node_type}
    if isinstance(args.get("data"), dict):
        command["data"] = args["data"]
    client_id = str(args.get("client_id") or args.get("clientId") or "").strip()
    if client_id:
        command["client_id"] = client_id
    position = _position_from_args(args)
    if position:
        command["position"] = position
    return _single_write_command(args, command)


def _handle_add_next_node(args: dict[str, Any], **_: Any) -> str:
    source_node_id = str(args.get("source_node_id") or args.get("sourceNodeId") or "").strip()
    node_type = str(args.get("node_type") or args.get("nodeType") or "").strip()
    if not source_node_id:
        return tool_result(
            {
                "ok": False,
                "status": "source_node_id_required",
                "error": "source_node_id is required",
            }
        )
    if not node_type:
        return tool_result(
            {"ok": False, "status": "node_type_required", "error": "node_type is required"}
        )
    command: dict[str, Any] = {
        "type": "add_next_node",
        "source_node_id": source_node_id,
        "node_type": node_type,
        "connect": bool(args.get("connect", True)),
    }
    if isinstance(args.get("data"), dict):
        command["data"] = args["data"]
    client_id = str(args.get("client_id") or args.get("clientId") or "").strip()
    if client_id:
        command["client_id"] = client_id
    return _single_write_command(args, command)


def _handle_update_node_data(args: dict[str, Any], **_: Any) -> str:
    node_id = str(args.get("node_id") or args.get("nodeId") or "").strip()
    if not node_id:
        return tool_result(
            {"ok": False, "status": "node_id_required", "error": "node_id is required"}
        )
    data = args.get("data")
    if not isinstance(data, dict):
        return tool_result(
            {"ok": False, "status": "data_required", "error": "data must be an object"}
        )
    return _single_write_command(
        args, {"type": "update_node_data", "node_id": node_id, "data": data}
    )


def _handle_create_edge(args: dict[str, Any], **_: Any) -> str:
    source = str(
        args.get("source") or args.get("source_node_id") or args.get("sourceNodeId") or ""
    ).strip()
    target = str(
        args.get("target") or args.get("target_node_id") or args.get("targetNodeId") or ""
    ).strip()
    link_type = str(args.get("link_type") or args.get("linkType") or "").strip()
    if not source:
        return tool_result(
            {"ok": False, "status": "source_required", "error": "source is required"}
        )
    if not target:
        return tool_result(
            {"ok": False, "status": "target_required", "error": "target is required"}
        )
    if not link_type:
        return tool_result(
            {"ok": False, "status": "link_type_required", "error": "link_type is required"}
        )
    return _single_write_command(
        args,
        {
            "type": "create_edge",
            "source": source,
            "target": target,
            "link_type": link_type,
        },
    )


def _handle_delete_nodes(args: dict[str, Any], **_: Any) -> str:
    node_ids = args.get("node_ids") or args.get("nodeIds")
    if not isinstance(node_ids, list) or not node_ids:
        return tool_result(
            {
                "ok": False,
                "status": "node_ids_required",
                "error": "node_ids must be a non-empty array",
            }
        )
    return _single_write_command(args, {"type": "delete_nodes", "node_ids": node_ids})


def _handle_delete_edges(args: dict[str, Any], **_: Any) -> str:
    command: dict[str, Any] = {"type": "delete_edges"}
    edge_ids = args.get("edge_ids") or args.get("edgeIds")
    pairs = args.get("pairs")
    if isinstance(edge_ids, list) and edge_ids:
        command["edge_ids"] = edge_ids
    if isinstance(pairs, list) and pairs:
        command["pairs"] = pairs
    if "edge_ids" not in command and "pairs" not in command:
        return tool_result(
            {"ok": False, "status": "edge_refs_required", "error": "edge_ids or pairs is required"}
        )
    return _single_write_command(args, command)


def _handle_move_nodes(args: dict[str, Any], **_: Any) -> str:
    command: dict[str, Any] = {"type": "move_nodes"}
    positions = args.get("positions")
    node_ids = args.get("node_ids") or args.get("nodeIds")
    if isinstance(positions, dict) and positions:
        command["positions"] = positions
    else:
        if not isinstance(node_ids, list) or not node_ids:
            return tool_result(
                {
                    "ok": False,
                    "status": "node_ids_required",
                    "error": "node_ids is required for relative moves",
                }
            )
        command["node_ids"] = node_ids
        if isinstance(args.get("dx"), (int, float)):
            command["dx"] = args["dx"]
        if isinstance(args.get("dy"), (int, float)):
            command["dy"] = args["dy"]
        if "dx" not in command and "dy" not in command:
            return tool_result(
                {
                    "ok": False,
                    "status": "delta_required",
                    "error": "dx or dy is required for relative moves",
                }
            )
    return _single_write_command(args, command)


def _handle_layout_nodes(args: dict[str, Any], **_: Any) -> str:
    mode = str(args.get("mode") or "").strip()
    if mode not in {"horizontal", "vertical", "grid"}:
        return tool_result(
            {
                "ok": False,
                "status": "mode_required",
                "error": "mode must be horizontal, vertical, or grid",
            }
        )
    command: dict[str, Any] = {"type": "layout_nodes", "mode": mode}
    node_ids = args.get("node_ids") or args.get("nodeIds")
    if isinstance(node_ids, list):
        command["node_ids"] = node_ids
    return _single_write_command(args, command)


def _handle_group_nodes(args: dict[str, Any], **_: Any) -> str:
    node_ids = args.get("node_ids") or args.get("nodeIds")
    if not isinstance(node_ids, list) or len(node_ids) < 2:
        return tool_result(
            {
                "ok": False,
                "status": "node_ids_required",
                "error": "node_ids must contain at least two nodes",
            }
        )
    command: dict[str, Any] = {"type": "group_nodes", "node_ids": node_ids}
    label = str(args.get("label") or "").strip()
    if label:
        command["label"] = label
    return _single_write_command(args, command)


def _handle_select_nodes(args: dict[str, Any], **_: Any) -> str:
    node_ids = args.get("node_ids") or args.get("nodeIds")
    if not isinstance(node_ids, list) or not node_ids:
        return tool_result(
            {
                "ok": False,
                "status": "node_ids_required",
                "error": "node_ids must be a non-empty array",
            }
        )
    command: dict[str, Any] = {"type": "select_nodes", "node_ids": node_ids}
    if "focus" in args:
        command["focus"] = bool(args.get("focus"))
    return _single_write_command(args, command)


def _handle_run_node_action(args: dict[str, Any], **_: Any) -> str:
    node_id = str(args.get("node_id") or args.get("nodeId") or "").strip()
    action = str(args.get("action") or "").strip()
    if not node_id:
        return tool_result(
            {"ok": False, "status": "node_id_required", "error": "node_id is required"}
        )
    if not action:
        return tool_result(
            {"ok": False, "status": "action_required", "error": "action is required"}
        )
    command: dict[str, Any] = {"type": "run_node_action", "node_id": node_id, "action": action}
    parameters = args.get("parameters") or args.get("params")
    if isinstance(parameters, dict):
        command["parameters"] = parameters
    return _single_write_command(args, command)


def _handle_open_mainline_projection(args: dict[str, Any], **_: Any) -> str:
    project = str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    canvas = str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    if not project:
        return tool_result({"ok": False, "status": "project_id_required", "error": "project_id is required"})

    raw_request = args.get("request") if isinstance(args.get("request"), dict) else args
    scope = str(raw_request.get("scope") or "").strip()
    if scope not in {"episode", "beat", "asset"}:
        return tool_result({"ok": False, "status": "scope_required", "error": "scope must be episode, beat, or asset"})

    request: dict[str, Any] = {"scope": scope}
    if isinstance(raw_request.get("episode"), int):
        request["episode"] = raw_request["episode"]
    if isinstance(raw_request.get("beat"), int):
        request["beat"] = raw_request["beat"]
    primary_slot = str(raw_request.get("primary_slot") or raw_request.get("primarySlot") or "").strip()
    if primary_slot:
        request["primary_slot"] = primary_slot
    asset_kind = str(raw_request.get("asset_kind") or raw_request.get("assetKind") or "").strip()
    if asset_kind:
        request["asset_kind"] = asset_kind
    for snake, camel in (
        ("character", "character"),
        ("identity_id", "identityId"),
        ("asset_id", "assetId"),
    ):
        value = str(raw_request.get(snake) or raw_request.get(camel) or "").strip()
        if value:
            request[snake] = value

    if scope == "episode" and "episode" not in request:
        return tool_result({"ok": False, "status": "episode_required", "error": "episode is required for episode scope"})
    if scope == "beat" and ("episode" not in request or "beat" not in request):
        return tool_result({"ok": False, "status": "beat_required", "error": "episode and beat are required for beat scope"})
    if scope == "asset":
        if "asset_kind" not in request:
            return tool_result({"ok": False, "status": "asset_kind_required", "error": "asset_kind is required for asset scope"})
        if not any(key in request for key in ("character", "identity_id", "asset_id")):
            return tool_result(
                {
                    "ok": False,
                    "status": "asset_ref_required",
                    "error": "character, identity_id, or asset_id is required for asset scope",
                }
            )

    return _emit_canvas_commands(
        project,
        canvas,
        [{"type": "open_mainline_projection", "project_id": project, "request": request}],
    )


def _request_canvas_context_from_frontend(
    *,
    project: str | None,
    canvas: str | None,
    requests: list[Any],
) -> str:
    envelope = {
        "schema_version": "canvas_context_request.v1",
        **({"canvas_id": canvas} if canvas else {}),
        "requests": requests,
    }
    if (
        canvas_context_bridge_key is not None
        and put_pending_canvas_context is not None
        and wait_canvas_context_result is not None
    ):
        key = canvas_context_bridge_key(project_id=project, canvas_id=canvas, requests=requests)
        put_pending_canvas_context(
            key=key,
            project_id=project,
            canvas_id=canvas,
            requests=requests,
            envelope=envelope,
        )
        try:
            timeout_seconds = max(
                1,
                int(os.environ.get("DRAMACLAW_CANVAS_CONTEXT_RESULT_TIMEOUT_SECONDS", "60")),
            )
        except ValueError:
            timeout_seconds = 60
        resolved = wait_canvas_context_result(key, timeout_seconds=timeout_seconds)
        if resolved is not None:
            return tool_result(resolved)
        return tool_result(
            {
                "ok": False,
                "tool_call_status": "failed",
                "canvas_context_status": "timeout",
                "errors": ["Timed out waiting for frontend canvas context response."],
                "bridge_key": key,
                **({"project_id": project} if project else {}),
                **({"canvas_id": canvas} if canvas else {}),
            }
        )
    return tool_error(
        "Canvas context bridge is unavailable; cannot wait for frontend context result. "
        f"Import error: {_CANVAS_COMMAND_BRIDGE_IMPORT_ERROR}"
    )


def _handle_link_type_catalog(args: dict[str, Any], **_: Any) -> str:
    project = (
        str(args.get("project_id") or args.get("project") or _default_project_id()).strip() or None
    )
    canvas = (
        str(args.get("canvas_id") or args.get("canvasId") or _default_canvas_id()).strip() or None
    )
    return _request_canvas_context_from_frontend(
        project=project,
        canvas=canvas,
        requests=[{"type": "link_type_catalog"}],
    )


def _schema(
    name: str, description: str, properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


_SCOPE_PROPS = {
    "project_id": {"type": "string", "description": "Defaults to the current project context."},
    "canvas_id": {"type": "string", "description": "Defaults to the current canvas context."},
    "canvasId": {"type": "string", "description": "Alias of canvas_id."},
}

_SKILL_STUDIO_OPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Stable lowercase option id.",
        },
        "label": {
            "type": "string",
            "description": "Short user-facing option label.",
        },
        "description": {
            "type": "string",
            "description": "One-sentence user-facing explanation of this option.",
        },
    },
    "required": ["id", "label"],
}

_SKILL_STUDIO_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Stable lowercase question id.",
        },
        "title": {
            "type": "string",
            "description": "User-facing question title.",
        },
        "description": {
            "type": "string",
            "description": "Optional short explanation for the question.",
        },
        "options": {
            "type": "array",
            "description": "2-4 selectable options.",
            "items": _SKILL_STUDIO_OPTION_SCHEMA,
        },
        "mode": {
            "type": "string",
            "enum": ["single", "multiple"],
            "description": "Selection mode. Use multiple when the user may choose several options.",
        },
        "selection_mode": {
            "type": "string",
            "enum": ["single", "multiple"],
            "description": "Alias of mode. Prefer mode for generic clarification.",
        },
        "allow_custom": {
            "type": "boolean",
            "description": "Whether the frontend should allow a free-form custom answer for this question.",
        },
    },
    "required": ["id", "title", "options"],
}

_SKILL_STUDIO_ASPECT_RATIO_SCHEMA = {
    "type": "object",
    "description": "Default aspect ratio by output task kind.",
    "additionalProperties": {"type": "string"},
}

_SKILL_STUDIO_MODEL_PREFERENCE_SCHEMA = {
    "type": "object",
    "description": "Preferred model by output task kind.",
    "additionalProperties": {"type": "string"},
}

_SKILL_STUDIO_RATING_BAND_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "description": "Score anchor from 0 to 10."},
        "description": {"type": "string", "description": "Rubric text for this score anchor."},
    },
    "required": ["score", "description"],
}

_SKILL_STUDIO_REVIEW_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Review dimension name."},
        "weight": {"type": "number", "description": "Dimension weight from 0 to 1."},
        "description": {"type": "string", "description": "Review dimension description."},
    },
    "required": ["name", "weight", "description"],
}

_SKILL_STUDIO_SKILL_SCHEMA = {
    "type": "object",
    "description": "Complete Xi画 Skill catalog draft.",
    "properties": {
        "id": {
            "type": "string",
            "description": "Lowercase id using letters, numbers, underscores, or hyphens.",
        },
        "description": {
            "type": "string",
            "description": "User-facing skill description.",
        },
        "category": {
            "type": "string",
            "description": "Skill category.",
        },
        "triggers": {
            "type": "object",
            "description": "Trigger rules such as keywords and nodeTypes. Use an empty array when no node type trigger applies.",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "nodeTypes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["keywords", "nodeTypes"],
        },
        "planning": {
            "type": "object",
            "description": "Planner behavior hints and rules.",
            "properties": {
                "planning_notes": {
                    "type": "string",
                    "description": "Planner-facing context hints for this skill.",
                },
                "prompt_guide": {
                    "type": "string",
                    "description": "Prompt style and structure guidance.",
                },
                "conduct_rules": {
                    "type": "array",
                    "description": "Behavior rules the agent should follow in this domain.",
                    "items": {"type": "string"},
                },
                "default_aspect_ratios": _SKILL_STUDIO_ASPECT_RATIO_SCHEMA,
                "model_preferences": _SKILL_STUDIO_MODEL_PREFERENCE_SCHEMA,
            },
            "required": [
                "planning_notes",
                "prompt_guide",
                "conduct_rules",
                "default_aspect_ratios",
                "model_preferences",
            ],
        },
        "evaluation": {
            "type": "object",
            "description": "Evaluation rubric.",
            "properties": {
                "rating_bands": {
                    "type": "array",
                    "description": "Score anchors for evaluating output quality.",
                    "items": _SKILL_STUDIO_RATING_BAND_SCHEMA,
                },
                "quality_threshold": {
                    "type": "number",
                    "description": "Passing score threshold.",
                },
                "domain_constraints": {
                    "type": "array",
                    "description": "Domain-specific constraints.",
                    "items": {"type": "string"},
                },
                "visual_review_items": {
                    "type": "array",
                    "description": "Visual review dimensions.",
                    "items": _SKILL_STUDIO_REVIEW_ITEM_SCHEMA,
                },
                "text_review_items": {
                    "type": "array",
                    "description": "Text review dimensions.",
                    "items": _SKILL_STUDIO_REVIEW_ITEM_SCHEMA,
                },
            },
            "required": [
                "rating_bands",
                "quality_threshold",
                "domain_constraints",
                "visual_review_items",
                "text_review_items",
            ],
        },
    },
    "required": ["id", "description", "category", "triggers", "planning", "evaluation"],
}

_SKILL_STUDIO_RECIPE_SCHEMA = {
    "type": "object",
    "description": "Complete Xi画 Recipe catalog draft.",
    "properties": {
        "id": {
            "type": "string",
            "description": "Lowercase id using letters, numbers, underscores, or hyphens.",
        },
        "name": {"type": "string", "description": "User-facing recipe name."},
        "output_kind": {
            "type": "string",
            "enum": ["text", "image", "video", "audio"],
            "description": "Generated output kind.",
        },
        "action_keys": {
            "type": "array",
            "description": "Operation/action keys this recipe matches.",
            "items": {"type": "string"},
        },
        "systemPrompt": {
            "type": "string",
            "description": "System prompt used by this recipe.",
        },
        "required_elements": {
            "type": "array",
            "description": "Must-have elements in the generated result.",
            "items": {"type": "string"},
        },
        "planner_cue": {
            "type": "string",
            "description": "Short cue for the planner.",
        },
        "output_summary": {
            "type": "string",
            "description": "Short output summary.",
        },
        "needs_multimodal_input": {
            "type": "boolean",
            "description": "Whether the recipe needs image/video/audio input.",
        },
    },
    "required": [
        "id",
        "name",
        "output_kind",
        "action_keys",
        "systemPrompt",
        "required_elements",
        "planner_cue",
        "output_summary",
        "needs_multimodal_input",
    ],
}


_LINK_TYPE_VALUES = [
    "context_for",
    "prompt_for",
    "media_input_for",
    "derived_from",
    "composition_input_for",
]

_NODE_TYPE_VALUES = [
    "uploadNode",
    "imageNode",
    "imageGenNode",
    "exportImageNode",
    "beatContextNode",
    "textAnnotationNode",
    "groupNode",
    "storyboardNode",
    "storyboardGenNode",
    "videoNode",
    "audioNode",
    "videoStoryNode",
    "videoComposeNode",
    "scriptNode",
    "pano360ViewerNode",
    "threeDWorldNode",
    "skillNode",
]

_AGENT_CREATABLE_NODE_TYPE_VALUES = [
    "uploadNode",
    "imageGenNode",
    "beatContextNode",
    "textAnnotationNode",
    "videoNode",
    "audioNode",
    "videoComposeNode",
    "scriptNode",
    "pano360ViewerNode",
    "threeDWorldNode",
    "skillNode",
]

_NODE_TYPE_DESCRIPTION = (
    "Directly creatable Freezone canvas node type. Use only these values for "
    "create_node/add_next_node. If the user asks to add a picture/image node, use "
    "imageGenNode unless they explicitly ask to upload or import an existing file. "
    "Use freezone_group_nodes/group_nodes for grouping existing nodes. "
    "Use textAnnotationNode for ordinary briefs, copy, notes, "
    "prompts, and free-form text. Use scriptNode only for explicit structured script "
    "tables or script-generation workflows. Use threeDWorldNode for 导演世界; "
    "directorWorldNode is not a valid node type."
)

_NODE_TYPE_SCHEMA = {
    "type": "string",
    "enum": _AGENT_CREATABLE_NODE_TYPE_VALUES,
    "description": _NODE_TYPE_DESCRIPTION,
}

_NODE_TYPE_ALIAS_SCHEMA = {
    "type": "string",
    "enum": _AGENT_CREATABLE_NODE_TYPE_VALUES,
    "description": "Alias of node_type. Prefer snake_case node_type.",
}

_MAINLINE_PROJECTION_SCOPE_VALUES = ["episode", "beat", "asset"]
_MAINLINE_PRIMARY_SLOT_VALUES = ["sketch", "frame", "render"]
_MAINLINE_ASSET_KIND_VALUES = [
    "character",
    "identity",
    "portrait",
    "scene",
    "scene_master",
    "scene_reverse_master",
    "scene_spatial_layout",
    "scene_360",
    "prop",
    "prop_ref",
]
_MAINLINE_PROJECTION_ASSET_KIND_VALUES = [
    "character",
    "scene",
    "scene_master",
    "scene_reverse_master",
    "scene_spatial_layout",
    "scene_360",
    "prop",
    "prop_ref",
]

_CANVAS_COMMAND_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": sorted(_COMMAND_TYPES),
            "description": "Required command discriminator. Use 'type', never legacy 'command'.",
        },
        "node_type": {
            "type": "string",
            "enum": _AGENT_CREATABLE_NODE_TYPE_VALUES,
            "description": "Required for create_node. Batch commands use snake_case node_type, never nodeType.",
        },
        "data": {
            "type": "object",
            "description": "Node data. Do not put nodeType or imageGenerationParams here.",
        },
        "client_id": {"type": "string", "description": "Same-batch alias for newly created nodes."},
        "source": {"type": "string"},
        "target": {"type": "string"},
        "link_type": {
            "type": "string",
            "enum": _LINK_TYPE_VALUES,
            "description": "Required for create_edge.",
        },
        "request": {
            "type": "object",
            "description": "Required for open_mainline_projection. Mainline projection request with scope, episode/beat, primary_slot, or asset fields.",
        },
    },
    "required": ["type"],
}


TOOLS = (
    # 读全局画布上下文。
    (
        "freezone_get_canvas_ontology",
        _schema(
            "freezone_get_canvas_ontology",
            "Request the current detailed Freezone canvas ontology context from the frontend.",
            _SCOPE_PROPS,
        ),
        _handle_canvas_ontology,
    ),
    (
        "freezone_summarize_canvas",
        _schema(
            "freezone_summarize_canvas",
            "Request the simple Freezone canvas ontology summary from the frontend.",
            _SCOPE_PROPS,
        ),
        _handle_summarize_canvas,
    ),
    (
        "freezone_get_canvas_action_catalog",
        _schema(
            "freezone_get_canvas_action_catalog",
            "Request the current canvas-level Freezone action catalog from the frontend.",
            _SCOPE_PROPS,
        ),
        _handle_canvas_action_catalog,
    ),
    (
        "freezone_get_canvas_command_catalog",
        _schema(
            "freezone_get_canvas_command_catalog",
            "Request the frontend Freezone canvas_chat_commands.v1 command catalog. Use this before freezone_emit_canvas_command when batch command fields are unclear.",
            _SCOPE_PROPS,
        ),
        _handle_canvas_command_catalog,
    ),
    (
        "freezone_request_user_clarification",
        _schema(
            "freezone_request_user_clarification",
            "Ask the user structured clarification questions in the Freezone frontend and wait for their submitted answers. Use for user choices before continuing the current chat or workflow, including Skill Studio setup questions. The submitted answers only mean the user completed the choices; decide the next step from the current context. This tool does not write canvas nodes or save catalog files.",
            {
                "clarification_id": {
                    "type": "string",
                    "description": "Stable id for this clarification request.",
                },
                "title": {
                    "type": "string",
                    "description": "Short title shown above the question card.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional one-sentence explanation shown to the user.",
                },
                "questions": {
                    "type": "array",
                    "description": "High-level user-facing questions. Use 1-5 questions, each with 2-5 options.",
                    "items": _SKILL_STUDIO_QUESTION_SCHEMA,
                },
                "allow_recommended": {
                    "type": "boolean",
                    "description": "Whether the frontend should show a use-recommended option.",
                },
                "allow_skip": {
                    "type": "boolean",
                    "description": "Whether the frontend should allow skipping this clarification.",
                },
                **_SCOPE_PROPS,
            },
            ["clarification_id", "questions"],
        ),
        _handle_request_user_clarification,
    ),
    (
        "freezone_present_agent_catalog_draft",
        _schema(
            "freezone_present_agent_catalog_draft",
            "Present a complete editable Skill/Recipe catalog draft for Xi画 Skill Studio. Use after questions or when enough context exists. Do not paste final JSON in prose and do not claim it is saved.",
            {
                "skill_studio_session_id": {
                    "type": "string",
                    "description": "Stable id shared by questions, draft, and later edits in this Skill Studio flow.",
                },
                "mode": {"type": "string", "enum": ["create", "edit"], "description": "Draft mode."},
                "skill": _SKILL_STUDIO_SKILL_SCHEMA,
                "recipes": {
                    "type": "array",
                    "description": "Complete Recipe drafts.",
                    "items": _SKILL_STUDIO_RECIPE_SCHEMA,
                },
                "summary": {"type": "string", "description": "Short user-facing summary."},
                "warnings": {
                    "type": "array",
                    "description": "User-facing draft warnings.",
                    "items": {"type": "string"},
                },
            },
            ["skill_studio_session_id", "mode"],
        ),
        _handle_present_agent_catalog_draft,
    ),
    (
        "freezone_get_link_type_catalog",
        _schema(
            "freezone_get_link_type_catalog",
            "Request the Freezone ordinary node link_type catalog for create_edge source/target compatibility.",
            _SCOPE_PROPS,
        ),
        _handle_link_type_catalog,
    ),
    (
        "freezone_get_selection",
        _schema(
            "freezone_get_selection",
            "Request the current Freezone canvas selection from the frontend.",
            _SCOPE_PROPS,
        ),
        _handle_selection,
    ),
    # 读节点级上下文。
    (
        "freezone_get_node_detail",
        _schema(
            "freezone_get_node_detail",
            "Request detailed context for one Freezone canvas node from the frontend.",
            {
                **_SCOPE_PROPS,
                "node_id": {"type": "string", "description": "Canvas node id."},
                "nodeId": {"type": "string", "description": "Alias of node_id."},
            },
            ["node_id"],
        ),
        _handle_node_detail,
    ),
    (
        "freezone_get_neighbor_graph",
        _schema(
            "freezone_get_neighbor_graph",
            "Request upstream/downstream neighbor graph context around one Freezone canvas node.",
            {
                **_SCOPE_PROPS,
                "node_id": {"type": "string", "description": "Canvas node id."},
                "nodeId": {"type": "string", "description": "Alias of node_id."},
                "depth": {
                    "type": "number",
                    "description": "Neighbor traversal depth. Defaults to 1.",
                },
            },
            ["node_id"],
        ),
        _handle_neighbor_graph,
    ),
    (
        "freezone_get_node_action_catalog",
        _schema(
            "freezone_get_node_action_catalog",
            "Request the action catalog for one Freezone canvas node from the frontend.",
            {
                **_SCOPE_PROPS,
                "node_id": {"type": "string", "description": "Canvas node id."},
                "nodeId": {"type": "string", "description": "Alias of node_id."},
            },
            ["node_id"],
        ),
        _handle_node_action_catalog,
    ),
    (
        "freezone_get_node_create_schema",
        _schema(
            "freezone_get_node_create_schema",
            "Request allowed create_node data schema for one Freezone node type from the frontend. "
            "For ordinary text, briefs, copywriting, prompts, notes, or free-form scripts, "
            "request textAnnotationNode schema. Request scriptNode only when the user "
            "explicitly asks for structured script tables or a script-generation workflow.",
            {
                **_SCOPE_PROPS,
                "node_type": _NODE_TYPE_SCHEMA,
                "nodeType": _NODE_TYPE_ALIAS_SCHEMA,
            },
            ["node_type"],
        ),
        _handle_node_create_schema,
    ),
    (
        "freezone_get_audio_voice_options",
        _schema(
            "freezone_get_audio_voice_options",
            "Request dynamic voice options for one Freezone audio node from the frontend.",
            {
                **_SCOPE_PROPS,
                "node_id": {"type": "string", "description": "Audio canvas node id."},
                "nodeId": {"type": "string", "description": "Alias of node_id."},
            },
            ["node_id"],
        ),
        _handle_audio_voice_options,
    ),
    (
        "freezone_get_slot_candidates",
        _schema(
            "freezone_get_slot_candidates",
            "Canvas -> mainline only. Request Freezone canvas nodes that can be submitted/pushed back to a mainline slot. Use this only when the user wants to submit, sync, or set a canvas node as a mainline result; do not use it to open/map/project mainline content into Freezone.",
            {
                **_SCOPE_PROPS,
                "slot_kind": {
                    "type": "string",
                    "description": "Optional mainline slot kind filter for canvas-to-mainline submission, e.g. image, video, audio, or text.",
                },
                "slotKind": {"type": "string", "description": "Alias of slot_kind."},
            },
        ),
        _handle_slot_candidates,
    ),
    (
        "freezone_get_mainline_projection_assets",
        _schema(
            "freezone_get_mainline_projection_assets",
            "Mainline -> canvas only. Request compact mainline asset candidates that can be opened/mapped/projected into Freezone with freezone_open_mainline_projection. Use only after the user explicitly asks to map/open/project mainline characters, scenes, or props into Freezone; do not use for ordinary canvas creation/editing/linking/layout/generation, and do not use for canvas-to-mainline submission. For people/characters/identities/portraits, always request asset kind character.",
            {
                **_SCOPE_PROPS,
                "asset_kinds": {
                    "type": "array",
                    "items": {"type": "string", "enum": _MAINLINE_PROJECTION_ASSET_KIND_VALUES},
                    "description": "Optional filters for mainline asset kinds to map into Freezone. Use character for all people/identity/portrait requests. Other narrow categories include prop, scene_master, scene_reverse_master, scene_360, or prop_ref.",
                },
                "assetKinds": {"type": "array", "items": {"type": "string"}, "description": "Alias of asset_kinds."},
                "asset_kind": {
                    "type": "string",
                    "enum": _MAINLINE_PROJECTION_ASSET_KIND_VALUES,
                    "description": "Single asset kind filter alias. Prefer asset_kinds for multiple values.",
                },
                "assetKind": {"type": "string", "description": "Alias of asset_kind."},
                "query": {"type": "string", "description": "Optional user-facing keyword to match asset label/name."},
                "q": {"type": "string", "description": "Alias of query."},
                "limit": {"type": "integer", "description": "Maximum candidates to return. Default 20, maximum 50."},
            },
        ),
        _handle_mainline_projection_assets,
    ),
    (
        "freezone_list_workflows",
        _schema(
            "freezone_list_workflows",
            "List registered Freezone workflow templates. Use this before choosing a workflow_type when the user asks what workflows are available or asks to create an ambiguous workflow.",
            {},
        ),
        _handle_list_workflows,
    ),
    (
        "freezone_build_workflow_plan",
        _schema(
            "freezone_build_workflow_plan",
            "Build a deterministic freezone_workflow_plan.v1 for one or more registered workflow_type values. This is read-only and does not change the canvas.",
            {
                "workflow_type": {
                    "type": "string",
                    "description": "Registered workflow type, e.g. text_to_image, image_to_video, text_to_video, image_to_text, text_to_audio, short_drama, ad_video, product_video, mv.",
                },
                "workflow_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple registered workflow types to plan together.",
                },
                "title": {"type": "string", "description": "Optional workflow title."},
                "user_goal": {
                    "type": "string",
                    "description": "Optional user goal or brief to seed text nodes.",
                },
                "beat_count": {
                    "type": "integer",
                    "description": "Optional beat count for short drama style workflows.",
                },
            },
        ),
        _handle_build_workflow_plan,
    ),
    (
        "freezone_resolve_catalog_workflow",
        _schema(
            "freezone_resolve_catalog_workflow",
            "Read-only first step for JSON-backed workflows. Resolve a user goal to Freezone built-in plus current-user agent_config skills and recipes catalog skill/template candidates without changing the canvas. Use this when the user asks to follow the skills/recipes JSON flow step by step.",
            {
                "user_goal": {
                    "type": "string",
                    "description": "User's natural-language request, brief, or chat message to match against agent_catalog skills triggers and template conditions.",
                },
                "message": {
                    "type": "string",
                    "description": "Alias of user_goal.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum candidate count to return. Default 5.",
                },
            },
        ),
        _handle_resolve_catalog_workflow,
    ),
    (
        "freezone_create_workflow_graph",
        _schema(
            "freezone_create_workflow_graph",
            "Create registered Freezone workflow nodes, edges, layout, and group in one frontend approval. Use this instead of hand-writing create_node/create_edge commands for registered workflows.",
            {
                **_SCOPE_PROPS,
                "workflow_type": {
                    "type": "string",
                    "description": "Registered workflow type to create.",
                },
                "workflow_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple registered workflow types to create in one approval.",
                },
                "plan": {
                    "type": "object",
                    "description": "Optional prebuilt freezone_workflow_plan.v1.",
                },
                "title": {"type": "string", "description": "Optional workflow title."},
                "user_goal": {
                    "type": "string",
                    "description": "Optional user goal or brief to seed text nodes.",
                },
                "beat_count": {
                    "type": "integer",
                    "description": "Optional beat count for short drama style workflows.",
                },
            },
        ),
        _handle_create_workflow_graph,
    ),
    # 写入前预校验。
    (
        "freezone_validate_canvas_commands",
        _schema(
            "freezone_validate_canvas_commands",
            "Preflight validate canvas_chat_commands.v1 against the current frontend canvas before emitting commands.",
            {
                **_SCOPE_PROPS,
                "commands": {
                    "type": "array",
                    "description": "Commands array from a canvas_chat_commands.v1 envelope. Batch commands require snake_case fields such as type and node_type; do not use legacy command/nodeType/imageGenerationParams.",
                    "items": _CANVAS_COMMAND_ITEM_SCHEMA,
                },
                "envelope": {
                    "type": "object",
                    "description": "Full canvas_chat_commands.v1 envelope to validate.",
                },
                "body": {
                    "type": "object",
                    "description": "Raw canvas_chat_commands.v1 envelope or object containing commands.",
                },
            },
        ),
        _handle_validate_commands,
    ),
    # 写入画布命令：默认用批量入口一次提交；只有用户明确要求单个操作时才用后面的单步工具。
    (
        "freezone_emit_canvas_command",
        _schema(
            "freezone_emit_canvas_command",
            "Default Freezone write tool for ordinary non-workflow canvas edits. Submit one complete canvas_chat_commands.v1 commands array for the user's requested canvas changes. Do not use this tool to create registered workflows returned by freezone_list_workflows; use freezone_create_workflow_graph instead. If commands[] fields are unclear, call freezone_get_canvas_command_catalog first.",
            {
                **_SCOPE_PROPS,
                "commands": {
                    "type": "array",
                    "description": "Complete canvas_chat_commands.v1 commands array for ordinary non-workflow edits. For registered workflows, do not build this array manually; call freezone_create_workflow_graph with workflow_type/workflow_types. Batch command objects require snake_case fields from freezone_get_canvas_command_catalog: type, node_type, source_node_id, node_id, node_ids, source, target, link_type, etc.",
                    "items": _CANVAS_COMMAND_ITEM_SCHEMA,
                },
                "body": {
                    "type": "object",
                    "description": "Optional raw body containing a commands array.",
                },
            },
            ["commands"],
        ),
        _handle_emit_canvas_command,
    ),
    # 单步写入工具：只用于用户明确要求 exactly one 的节点、连线、编辑或动作。
    (
        "freezone_create_node",
        _schema(
            "freezone_create_node",
            "Single-operation tool only: create exactly one standalone Freezone canvas node when the user explicitly asks for one node. If the user asks to create these nodes, several nodes, a workflow, storyboard, prototype, framework, page, short-video plan, or any request with more than one canvas change, do not use this repeatedly; use one freezone_emit_canvas_command batch instead. For dynamic fields, inspect freezone_get_node_create_schema first.",
            {
                **_SCOPE_PROPS,
                "node_type": _NODE_TYPE_SCHEMA,
                "nodeType": _NODE_TYPE_ALIAS_SCHEMA,
                "data": {
                    "type": "object",
                    "description": "Node data. Prefer stable fields such as prompt, title, content, text, displayName.",
                },
                "position": {
                    "type": "object",
                    "description": 'Optional canvas position, e.g. {"x": 300, "y": 120}.',
                },
                "x": {"type": "number", "description": "Optional canvas x position."},
                "y": {"type": "number", "description": "Optional canvas y position."},
            },
            ["node_type"],
        ),
        _handle_create_node,
    ),
    (
        "freezone_add_next_node",
        _schema(
            "freezone_add_next_node",
            "Single-operation tool only: create exactly one downstream node behind one existing source node. Use only when the user explicitly asks for one downstream node and the source node is a valid input source. For several downstream nodes, workflows, prototypes, storyboards, or create+link/layout requests, use one freezone_emit_canvas_command batch instead.",
            {
                **_SCOPE_PROPS,
                "source_node_id": {
                    "type": "string",
                    "description": "Existing source canvas node id.",
                },
                "sourceNodeId": {"type": "string", "description": "Alias of source_node_id."},
                "node_type": _NODE_TYPE_SCHEMA,
                "nodeType": _NODE_TYPE_ALIAS_SCHEMA,
                "data": {"type": "object", "description": "New node data."},
                "connect": {
                    "type": "boolean",
                    "description": "Whether to auto-connect source to the new node. Defaults to true.",
                },
            },
            ["source_node_id", "node_type"],
        ),
        _handle_add_next_node,
    ),
    (
        "freezone_update_node_data",
        _schema(
            "freezone_update_node_data",
            "Single-operation tool only: update editable data fields on exactly one existing Freezone node when the user explicitly asks for one node edit. For multi-node edits or mixed edit+layout/link workflows, use one freezone_emit_canvas_command batch. Inspect freezone_get_node_action_catalog first when editable fields or enum options are unclear.",
            {
                **_SCOPE_PROPS,
                "node_id": {"type": "string", "description": "Existing canvas node id."},
                "nodeId": {"type": "string", "description": "Alias of node_id."},
                "data": {
                    "type": "object",
                    "description": "Only fields to change. Do not include reserved or non-editable fields.",
                },
            },
            ["node_id", "data"],
        ),
        _handle_update_node_data,
    ),
    (
        "freezone_create_edge",
        _schema(
            "freezone_create_edge",
            "Single-operation tool only: create exactly one semantic edge between two existing Freezone nodes when the user explicitly asks for one edge. For multiple edges, create+edge workflows, or newly created nodes that need same-batch client_id references, use one freezone_emit_canvas_command batch. Call freezone_get_link_type_catalog first unless the valid link_type for this source/target pair is already known. If validation says no link_type is valid, do not retry other link_type values; group related nodes instead.",
            {
                **_SCOPE_PROPS,
                "source": {"type": "string", "description": "Source node id."},
                "target": {"type": "string", "description": "Target node id."},
                "link_type": {
                    "type": "string",
                    "enum": _LINK_TYPE_VALUES,
                    "description": "Semantic relation. Required; do not use role, link_kind, semantic_kind, semantic_reason, or semantic_description.",
                },
                "linkType": {"type": "string", "description": "Alias of link_type."},
            },
            ["source", "target", "link_type"],
        ),
        _handle_create_edge,
    ),
    (
        "freezone_delete_nodes",
        _schema(
            "freezone_delete_nodes",
            "Single-operation tool only: delete nodes as one pure delete operation when the user explicitly asks only to delete nodes. For mixed delete/update/layout/link workflows, use one freezone_emit_canvas_command batch. Use this for node deletion, not for disconnecting edges.",
            {
                **_SCOPE_PROPS,
                "node_ids": {
                    "type": "array",
                    "description": "Existing node ids to delete.",
                    "items": {"type": "string"},
                },
                "nodeIds": {
                    "type": "array",
                    "description": "Alias of node_ids.",
                    "items": {"type": "string"},
                },
            },
            ["node_ids"],
        ),
        _handle_delete_nodes,
    ),
    (
        "freezone_delete_edges",
        _schema(
            "freezone_delete_edges",
            "Single-operation tool only: disconnect edges as one pure edge-delete operation. For mixed workflows, use one freezone_emit_canvas_command batch. Use edge_ids when known, or pairs when only source/target nodes are known.",
            {
                **_SCOPE_PROPS,
                "edge_ids": {
                    "type": "array",
                    "description": "Existing edge ids to delete.",
                    "items": {"type": "string"},
                },
                "edgeIds": {
                    "type": "array",
                    "description": "Alias of edge_ids.",
                    "items": {"type": "string"},
                },
                "pairs": {
                    "type": "array",
                    "description": 'Source/target pairs, e.g. [{"source":"node_a","target":"node_b"}].',
                    "items": {"type": "object"},
                },
            },
        ),
        _handle_delete_edges,
    ),
    (
        "freezone_move_nodes",
        _schema(
            "freezone_move_nodes",
            "Single-operation tool only: move Freezone canvas nodes as one pure move operation. For mixed create/link/layout/move workflows, use one freezone_emit_canvas_command batch. Use positions for absolute placement, or node_ids plus dx/dy for relative movement.",
            {
                **_SCOPE_PROPS,
                "positions": {
                    "type": "object",
                    "description": 'Absolute positions keyed by node id/client_id, e.g. {"node_a":{"x":300,"y":120}}.',
                },
                "node_ids": {
                    "type": "array",
                    "description": "Node ids for relative movement.",
                    "items": {"type": "string"},
                },
                "nodeIds": {
                    "type": "array",
                    "description": "Alias of node_ids.",
                    "items": {"type": "string"},
                },
                "dx": {"type": "number", "description": "Relative x delta."},
                "dy": {"type": "number", "description": "Relative y delta."},
            },
        ),
        _handle_move_nodes,
    ),
    (
        "freezone_layout_nodes",
        _schema(
            "freezone_layout_nodes",
            "Single-operation tool only: auto-layout selected Freezone nodes, or the whole canvas when node_ids is omitted or empty. For create/link/layout workflows, use one freezone_emit_canvas_command batch.",
            {
                **_SCOPE_PROPS,
                "mode": {
                    "type": "string",
                    "enum": ["horizontal", "vertical", "grid"],
                    "description": "Layout mode.",
                },
                "node_ids": {
                    "type": "array",
                    "description": "Optional node ids to layout.",
                    "items": {"type": "string"},
                },
                "nodeIds": {
                    "type": "array",
                    "description": "Alias of node_ids.",
                    "items": {"type": "string"},
                },
            },
            ["mode"],
        ),
        _handle_layout_nodes,
    ),
    (
        "freezone_group_nodes",
        _schema(
            "freezone_group_nodes",
            "Single-operation tool only: create a plain visual group around related nodes as one pure grouping operation. This does not replace valid semantic edges, but it is the preferred fallback when no valid link_type exists. For mixed workflows, use one freezone_emit_canvas_command batch.",
            {
                **_SCOPE_PROPS,
                "node_ids": {
                    "type": "array",
                    "description": "At least two node ids/client_ids to group.",
                    "items": {"type": "string"},
                },
                "nodeIds": {
                    "type": "array",
                    "description": "Alias of node_ids.",
                    "items": {"type": "string"},
                },
                "label": {"type": "string", "description": "Optional group label."},
            },
            ["node_ids"],
        ),
        _handle_group_nodes,
    ),
    (
        "freezone_select_nodes",
        _schema(
            "freezone_select_nodes",
            "Single-operation tool only: select or focus nodes as one pure selection operation. For mixed workflows, use one freezone_emit_canvas_command batch.",
            {
                **_SCOPE_PROPS,
                "node_ids": {
                    "type": "array",
                    "description": "Node ids/client_ids to select.",
                    "items": {"type": "string"},
                },
                "nodeIds": {
                    "type": "array",
                    "description": "Alias of node_ids.",
                    "items": {"type": "string"},
                },
                "focus": {
                    "type": "boolean",
                    "description": "Whether to focus the selected node(s).",
                },
            },
            ["node_ids"],
        ),
        _handle_select_nodes,
    ),
    (
        "freezone_open_mainline_projection",
        _schema(
            "freezone_open_mainline_projection",
            "Mainline -> canvas only. Open/map/project a mainline episode, beat, or asset into the user's personal Freezone canvas. This mirrors the frontend 虾画/虾画编辑 toolbar button: the frontend asks the user to confirm, then opens the projected canvas. Use this when the user asks to open/map mainline content into 虾画/Freezone; do not use slot-candidate tools for this direction, and do not use this tool to submit canvas nodes back to the mainline. If the user asks to map a category such as 人物/身份/肖像/场景/道具 but does not provide an exact asset name/id, first call freezone_get_mainline_projection_assets for that category, using asset_kind=character for all people/identity/portrait requests, then pass the selected candidate's projection_request to this tool.",
            {
                **_SCOPE_PROPS,
                "scope": {
                    "type": "string",
                    "enum": _MAINLINE_PROJECTION_SCOPE_VALUES,
                    "description": "Mainline projection scope: episode, beat, or asset.",
                },
                "episode": {"type": "integer", "description": "Episode number. Required for episode and beat scopes."},
                "beat": {"type": "integer", "description": "Beat number. Required for beat scope."},
                "primary_slot": {
                    "type": "string",
                    "enum": _MAINLINE_PRIMARY_SLOT_VALUES,
                    "description": "For beat scope: sketch for 草图, frame for 分镜, render for default/render.",
                },
                "primarySlot": {"type": "string", "description": "Alias of primary_slot."},
                "asset_kind": {
                    "type": "string",
                    "enum": _MAINLINE_ASSET_KIND_VALUES,
                    "description": "Asset kind for asset scope.",
                },
                "assetKind": {"type": "string", "description": "Alias of asset_kind."},
                "character": {"type": "string", "description": "Character name for character assets."},
                "identity_id": {"type": "string", "description": "Legacy alias accepted by older character projection requests; prefer character-only asset projections."},
                "identityId": {"type": "string", "description": "Alias of identity_id."},
                "asset_id": {"type": "string", "description": "Scene or prop id for scene/prop assets."},
                "assetId": {"type": "string", "description": "Alias of asset_id."},
                "request": {
                    "type": "object",
                    "description": "Optional raw projection request object. Top-level fields are preferred.",
                },
            },
            ["scope"],
        ),
        _handle_open_mainline_projection,
    ),
    (
        "freezone_run_node_action",
        _schema(
            "freezone_run_node_action",
            "Single-operation tool only: run or open exactly one frontend node action listed by freezone_get_node_action_catalog. For multiple actions or mixed workflows, use one freezone_emit_canvas_command batch.",
            {
                **_SCOPE_PROPS,
                "node_id": {"type": "string", "description": "Existing canvas node id."},
                "nodeId": {"type": "string", "description": "Alias of node_id."},
                "action": {
                    "type": "string",
                    "description": "Exact action id from the node action catalog.",
                },
                "parameters": {
                    "type": "object",
                    "description": "Optional parameters for actions whose action_catalog exposes parameter_schema.",
                },
                "params": {"type": "object", "description": "Alias of parameters."},
            },
            ["node_id", "action"],
        ),
        _handle_run_node_action,
    ),
)


def register(ctx) -> None:
    for name, schema, handler in TOOLS:
        for toolset in REGISTER_TOOLSETS:
            ctx.register_tool(
                name=name,
                toolset=toolset,
                schema=schema,
                handler=handler,
                check_fn=_available,
                requires_env=["DRAMACLAW_API_URL", "DRAMACLAW_AGENT_TOKEN"],
                description=schema["description"],
                emoji="",
            )
