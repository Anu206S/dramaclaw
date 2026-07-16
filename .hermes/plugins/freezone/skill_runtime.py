"""Interactive Freezone Skill session runtime.

This module is intentionally separate from the existing workflow graph tools.
It manages high-level Skill sessions and leaves canvas writes/execution to the
existing Freezone command tools or a future runner.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

try:
    from json_workflow_catalog import _catalog_label, _catalog_source, _load_skill, _load_skills
    from json_workflow_catalog import _templates, _text, build_catalog_workflow_plan
except Exception:  # pragma: no cover - surfaced by callers via import failure.
    _catalog_label = None
    _catalog_source = None
    _load_skill = None
    _load_skills = None
    _templates = None
    _text = None
    build_catalog_workflow_plan = None


SESSION_SCHEMA_VERSION = "freezone_skill_session.v1"
INTERACTIVE_SKILL_TYPE = "interactive_skill"
WORKFLOW_SKILL_TYPE = "workflow"


def list_skill_entries(args: dict[str, Any] | None = None) -> dict[str, Any]:
    args = args or {}
    if _load_skills is None:
        return _error("json workflow catalog is unavailable")
    include_workflows = _bool(args.get("include_workflows"), True)
    entries = [_skill_entry(skill) for skill in _load_skills() if not skill.get("_disabled")]
    if not include_workflows:
        entries = [entry for entry in entries if entry["type"] == INTERACTIVE_SKILL_TYPE]
    entries.sort(key=lambda item: (item["type"] != INTERACTIVE_SKILL_TYPE, item["source"], item["id"]))
    return {"ok": True, "count": len(entries), "skills": entries}


def start_skill_session(args: dict[str, Any]) -> dict[str, Any]:
    if _load_skills is None:
        return _error("json workflow catalog is unavailable")
    skill, selection = _resolve_skill(args)
    if selection is not None:
        return selection
    if skill is None:
        return _error("skill not found", status="skill_not_found")
    config = _default_config(skill)
    supplied_config = args.get("config")
    if isinstance(supplied_config, dict):
        config.update({str(key): value for key, value in supplied_config.items()})
    mode = _text_value(
        args.get("execution_mode")
        or args.get("executionMode")
        or config.get("execution_mode")
        or _default_execution_mode(skill)
    )
    if mode:
        config["execution_mode"] = mode
    session = {
        "schema_version": SESSION_SCHEMA_VERSION,
        "session_id": _new_session_id(),
        "skill_id": _text_value(skill.get("id")),
        "skill_name": _skill_name(skill),
        "skill_type": _skill_type(skill),
        "source": _skill_source(skill),
        "project_id": _text_value(args.get("project_id") or args.get("project")),
        "canvas_id": _text_value(args.get("canvas_id") or args.get("canvasId")),
        "user_goal": _text_value(args.get("user_goal") or args.get("message") or args.get("prompt")),
        "phase": "collecting_parameters",
        "status": "waiting_config_confirmation",
        "execution_mode": config.get("execution_mode") or mode or "manual",
        "config": config,
        "parameters": _parameters(skill),
        "missing_required_parameters": _missing_required_parameters(skill, config),
        "created_at": _now_ms(),
        "updated_at": _now_ms(),
        "confirmed_at": None,
        "cancelled_at": None,
    }
    session["summary"] = _session_summary(skill, session)
    if not session["missing_required_parameters"]:
        session["phase"] = "ready_to_confirm"
    _save_session(session)
    return {
        "ok": True,
        "status": session["status"],
        "session": _public_session(session),
        "questions": _parameter_questions(
            skill,
            session["missing_required_parameters"],
            config=session["config"],
            include_all=True,
        ),
        "message": "Skill Session 已创建，请确认参数后再开始执行。",
        "agent_instruction": (
            "Present all selectable parameters and their options to the user. Let the user pick "
            "options or accept defaults. Do not create canvas nodes or run workflow steps until "
            "the user confirms the Skill Session."
        ),
    }


def update_skill_session_config(args: dict[str, Any]) -> dict[str, Any]:
    session, error = _load_session_from_args(args)
    if error is not None:
        return error
    updates = args.get("config") or args.get("updates")
    if not isinstance(updates, dict):
        return _error("config is required", status="config_required")
    session["config"].update({str(key): value for key, value in updates.items()})
    if "execution_mode" in session["config"]:
        session["execution_mode"] = _text_value(session["config"].get("execution_mode")) or "manual"
    skill = _load_skill(session["skill_id"]) if _load_skill is not None else None
    session["missing_required_parameters"] = _missing_required_parameters(skill or {}, session["config"])
    session["phase"] = "ready_to_confirm" if not session["missing_required_parameters"] else "collecting_parameters"
    session["updated_at"] = _now_ms()
    session["summary"] = _session_summary(skill or {}, session)
    _save_session(session)
    return {
        "ok": True,
        "status": session["status"],
        "session": _public_session(session),
        "questions": _parameter_questions(
            skill or {},
            session["missing_required_parameters"],
            config=session["config"],
            include_all=True,
        ),
    }


def confirm_skill_session(args: dict[str, Any]) -> dict[str, Any]:
    session, error = _load_session_from_args(args)
    if error is not None:
        return error
    if session.get("cancelled_at"):
        return _error("session is cancelled", status="session_cancelled")
    if session.get("missing_required_parameters"):
        return {
            "ok": False,
            "status": "missing_required_parameters",
            "session": _public_session(session),
            "questions": _parameter_questions(
                _load_skill(session["skill_id"]) if _load_skill is not None else {},
                session["missing_required_parameters"],
                config=session["config"],
                include_all=False,
            ),
        }
    skill = _load_skill(session["skill_id"]) if _load_skill is not None else None
    plan = _build_execution_plan(skill or {}, session)
    session["phase"] = "confirmed"
    session["status"] = "confirmed"
    session["confirmed_at"] = _now_ms()
    session["updated_at"] = _now_ms()
    session["execution_plan"] = plan
    _save_session(session)
    return {
        "ok": True,
        "status": "confirmed",
        "session": _public_session(session),
        "execution_plan": plan,
        "message": "Skill Session 已确认。下一步可由 runner 创建画布节点并按策略执行。",
        "agent_instruction": (
            "Do not call legacy workflow tools unless the user asks to create nodes now. "
            "For this first runtime version, report the confirmed plan and wait for the next action."
        ),
    }


def get_skill_session_status(args: dict[str, Any]) -> dict[str, Any]:
    session, error = _load_session_from_args(args)
    if error is not None:
        return error
    return {"ok": True, "session": _public_session(session), "execution_plan": session.get("execution_plan")}


def cancel_skill_session(args: dict[str, Any]) -> dict[str, Any]:
    session, error = _load_session_from_args(args)
    if error is not None:
        return error
    session["status"] = "cancelled"
    session["phase"] = "cancelled"
    session["cancelled_at"] = _now_ms()
    session["updated_at"] = _now_ms()
    _save_session(session)
    return {"ok": True, "status": "cancelled", "session": _public_session(session)}


def _resolve_skill(args: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    requested = _text_value(args.get("skill_id") or args.get("skillId"))
    skills = [skill for skill in _load_skills() if not skill.get("_disabled")]
    if requested:
        normalized = _alias_key(requested)
        for skill in skills:
            aliases = [_text_value(skill.get("id")), _skill_name(skill), *_string_list(skill.get("aliases"))]
            if normalized in {_alias_key(item) for item in aliases if item}:
                return skill, None
        return None, None
    user_goal = _text_value(args.get("user_goal") or args.get("message") or args.get("prompt"))
    candidates = _match_skills(skills, user_goal, limit=_int(args.get("limit"), 5))
    positive = [candidate for candidate in candidates if candidate["score"] > 0]
    if not positive:
        return None, {
            "ok": False,
            "status": "skill_selection_required",
            "reason": "no_skill_matched",
            "candidates": candidates,
            "message": "没有明确命中 Skill，请让用户选择一个 Skill 或补充目标。",
        }
    top = positive[0]
    second_score = positive[1]["score"] if len(positive) > 1 else 0.0
    if len(positive) > 1 and top["score"] - second_score < 1.0:
        return None, {
            "ok": False,
            "status": "skill_selection_required",
            "reason": "multiple_skills_matched",
            "candidates": positive,
            "message": "命中多个 Skill，请让用户选择一个 skill_id 后再开始。",
        }
    for skill in skills:
        if _text_value(skill.get("id")) == top["skill_id"]:
            return skill, None
    return None, None


def _match_skills(skills: list[dict[str, Any]], user_goal: str, *, limit: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    goal = _alias_key(user_goal)
    for skill in skills:
        haystacks = [
            _text_value(skill.get("id")),
            _skill_name(skill),
            _text_value(skill.get("description")),
            *_string_list(skill.get("aliases")),
            *_string_list((skill.get("triggers") or {}).get("keywords") if isinstance(skill.get("triggers"), dict) else []),
        ]
        score = 0.0
        reasons: list[str] = []
        for text in haystacks:
            key = _alias_key(text)
            if not key:
                continue
            if goal and key in goal:
                score += 10.0
                reasons.append(f"matched:{text}")
            elif goal and any(token and token in key for token in _tokens(goal)):
                score += 1.0
        candidates.append(
            {
                "skill_id": _text_value(skill.get("id")),
                "name": _skill_name(skill),
                "type": _skill_type(skill),
                "source": _skill_source(skill),
                "score": round(score, 3),
                "description": _text_value(skill.get("description")),
                "reasons": reasons[:5],
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["type"] != INTERACTIVE_SKILL_TYPE, item["skill_id"]))
    return candidates[: max(1, limit)]


def _build_execution_plan(skill: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    steps = skill.get("steps") if isinstance(skill.get("steps"), list) else []
    if not steps and _templates is not None:
        templates = _templates(skill)
        if templates:
            workflow_type = f"catalog.{session['skill_id']}.{_text_value(templates[0].get('id'))}"
            if build_catalog_workflow_plan is not None:
                plan = build_catalog_workflow_plan(
                    {
                        "workflow_type": workflow_type,
                        "user_goal": session.get("user_goal") or session.get("summary") or "",
                    }
                )
                if isinstance(plan, dict) and plan.get("ok"):
                    return {
                        "schema_version": "freezone_skill_execution_plan.v1",
                        "source": "workflow_template",
                        "workflow_type": workflow_type,
                        "mode": session.get("execution_mode"),
                        "approval_policy": _approval_policy(skill, session.get("execution_mode")),
                        "node_count": len(plan.get("nodes") or []),
                        "edge_count": len(plan.get("edges") or []),
                        "workflow_plan": plan,
                    }
    normalized_steps = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        normalized_steps.append(
            {
                "id": _text_value(step.get("id") or f"step_{index + 1}"),
                "node_type": _text_value(step.get("node_type") or step.get("nodeType")),
                "recipe_id": _text_value(step.get("recipe_id") or step.get("recipeId")),
                "depends_on": [item for item in step.get("depends_on", []) if isinstance(item, str)],
                "execution": step.get("execution") or "node_action",
            }
        )
    return {
        "schema_version": "freezone_skill_execution_plan.v1",
        "source": "interactive_skill",
        "mode": session.get("execution_mode"),
        "approval_policy": _approval_policy(skill, session.get("execution_mode")),
        "steps": normalized_steps,
        "step_count": len(normalized_steps),
    }


def _approval_policy(skill: dict[str, Any], mode: str | None) -> dict[str, Any]:
    policy = skill.get("execution_policy") if isinstance(skill.get("execution_policy"), dict) else {}
    mode_policy = policy.get(mode or "") if isinstance(policy.get(mode or ""), dict) else {}
    if mode == "auto":
        defaults = {
            "before_start_confirmation": True,
            "per_step_confirmation": False,
            "dangerous_action_confirmation": True,
            "regenerate_completed_confirmation": True,
        }
    else:
        defaults = {
            "before_start_confirmation": True,
            "per_step_confirmation": True,
            "dangerous_action_confirmation": True,
            "regenerate_completed_confirmation": True,
        }
    defaults.update(mode_policy)
    return defaults


def _default_config(skill: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for parameter in _parameters(skill):
        parameter_id = _text_value(parameter.get("id"))
        if not parameter_id:
            continue
        if "default" in parameter:
            config[parameter_id] = parameter.get("default")
    return config


def _parameters(skill: dict[str, Any]) -> list[dict[str, Any]]:
    params = skill.get("parameters")
    if not isinstance(params, list):
        return []
    return [dict(item) for item in params if isinstance(item, dict)]


def _missing_required_parameters(skill: dict[str, Any], config: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for parameter in _parameters(skill):
        parameter_id = _text_value(parameter.get("id"))
        if parameter_id and parameter.get("required") is True and parameter_id not in config:
            missing.append(parameter_id)
    return missing


def _parameter_questions(
    skill: dict[str, Any],
    missing_ids: list[str],
    *,
    config: dict[str, Any] | None = None,
    include_all: bool = False,
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    missing = set(missing_ids)
    current_config = config or {}
    for parameter in _parameters(skill):
        parameter_id = _text_value(parameter.get("id"))
        if not include_all:
            if missing and parameter_id not in missing:
                continue
            if not missing and parameter.get("required") is not True:
                continue
        options = parameter.get("options") if isinstance(parameter.get("options"), list) else []
        questions.append(
            {
                "id": parameter_id,
                "label": _text_value(parameter.get("label") or parameter_id),
                "type": _text_value(parameter.get("type") or "text"),
                "default": parameter.get("default"),
                "current_value": current_config.get(parameter_id),
                "options": options,
                "required": bool(parameter.get("required")),
                "selectable": bool(options),
            }
        )
    return questions


def _session_summary(skill: dict[str, Any], session: dict[str, Any]) -> str:
    config = session.get("config") or {}
    lines = [f"Skill：{session.get('skill_name') or _skill_name(skill)}"]
    if session.get("user_goal"):
        lines.append(f"目标：{session['user_goal']}")
    if config:
        parts = [f"{key}={value}" for key, value in sorted(config.items())]
        lines.append("配置：" + "；".join(parts))
    lines.append(f"执行模式：{session.get('execution_mode') or 'manual'}")
    return "\n".join(lines)


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema_version",
        "session_id",
        "skill_id",
        "skill_name",
        "skill_type",
        "source",
        "project_id",
        "canvas_id",
        "user_goal",
        "phase",
        "status",
        "execution_mode",
        "config",
        "missing_required_parameters",
        "summary",
        "created_at",
        "updated_at",
        "confirmed_at",
        "cancelled_at",
    )
    return {key: session.get(key) for key in keys if key in session}


def _skill_entry(skill: dict[str, Any]) -> dict[str, Any]:
    templates = _templates(skill) if _templates is not None else []
    return {
        "id": _text_value(skill.get("id")),
        "name": _skill_name(skill),
        "type": _skill_type(skill),
        "source": _skill_source(skill),
        "description": _text_value(skill.get("description")),
        "category": _text_value(skill.get("category")),
        "aliases": _string_list(skill.get("aliases")),
        "parameter_count": len(_parameters(skill)),
        "template_count": len(templates),
    }


def _skill_type(skill: dict[str, Any]) -> str:
    value = _text_value(skill.get("type") or skill.get("skill_type"))
    if value:
        return value
    if _parameters(skill) or isinstance(skill.get("steps"), list):
        return INTERACTIVE_SKILL_TYPE
    return WORKFLOW_SKILL_TYPE


def _skill_name(skill: dict[str, Any]) -> str:
    if _catalog_label is not None:
        return _catalog_label(skill)
    return _text_value(skill.get("name") or skill.get("label") or skill.get("id"))


def _skill_source(skill: dict[str, Any]) -> str:
    if _catalog_source is not None:
        return _catalog_source(skill)
    return _text_value(skill.get("_catalog_source") or "builtin")


def _default_execution_mode(skill: dict[str, Any]) -> str:
    for parameter in _parameters(skill):
        if _text_value(parameter.get("id")) == "execution_mode":
            return _text_value(parameter.get("default")) or "manual"
    return _text_value(skill.get("default_execution_mode")) or "manual"


def _session_dir() -> Path:
    configured = _text_value(os.environ.get("DRAMACLAW_SKILL_SESSION_DIR"))
    if configured:
        path = Path(configured)
    else:
        bridge_dir = _text_value(os.environ.get("DRAMACLAW_CANVAS_COMMAND_BRIDGE_DIR"))
        if bridge_dir:
            path = Path(bridge_dir).parent / "skill_sessions"
        else:
            user = _text_value(os.environ.get("DRAMACLAW_USER") or os.environ.get("SUPERTALE_USER") or "local")
            path = Path.cwd() / "state" / user / ".hermes-freezone" / "tmp" / "skill_sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)
    return _session_dir() / f"{safe}.json"


def _save_session(session: dict[str, Any]) -> None:
    path = _session_path(_text_value(session["session_id"]))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _load_session(session_id: str) -> dict[str, Any] | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_session_from_args(args: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    session_id = _text_value(args.get("session_id") or args.get("sessionId"))
    if not session_id:
        return None, _error("session_id is required", status="session_id_required")
    session = _load_session(session_id)
    if session is None:
        return None, _error(f"session not found: {session_id}", status="session_not_found")
    return session, None


def _new_session_id() -> str:
    return f"skill_{uuid.uuid4().hex}"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _text_value(value: Any) -> str:
    if _text is not None:
        return _text(value)
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text_value(item) for item in value if _text_value(item)]


def _alias_key(value: Any) -> str:
    return re.sub(r"[\s_/\-\\：:（）()]+", "", _text_value(value).lower())


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", value) if token]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return _text_value(value).lower() in {"1", "true", "yes", "on"}


def _error(message: str, *, status: str = "error") -> dict[str, Any]:
    return {"ok": False, "status": status, "error": message}
