"""Persistent drafts for confirmed Freezone workflow intents."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any

import fcntl


SCHEMA_VERSION = "freezone_workflow_draft.v1"
DEFAULT_TTL_SECONDS = 24 * 60 * 60
PATCHABLE_FIELDS = {
    "assumptions",
    "include_audio",
    "include_compose",
    "inputs",
    "items",
    "planner",
    "summary",
    "title",
    "user_goal",
}
MERGED_OBJECT_FIELDS = {"inputs"}


def _draft_dir() -> Path:
    configured = os.environ.get("DRAMACLAW_WORKFLOW_DRAFT_DIR", "").strip()
    if configured:
        return Path(configured)
    bridge_root = os.environ.get("DRAMACLAW_CANVAS_COMMAND_BRIDGE_DIR", "").strip()
    if bridge_root:
        return Path(bridge_root) / "workflow_drafts"
    return Path(tempfile.gettempdir()) / "dramaclaw_workflow_drafts"


def _draft_path(draft_id: str) -> Path:
    if not draft_id.startswith("workflow_draft_") or not all(
        char.isalnum() or char in {"_", "-"} for char in draft_id
    ):
        raise ValueError("invalid workflow draft id")
    return _draft_dir() / f"{draft_id}.json"


@contextmanager
def _draft_lock(draft_id: str):
    path = _draft_path(draft_id)
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield path
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _ttl_seconds() -> int:
    try:
        return max(
            300,
            int(
                os.environ.get(
                    "DRAMACLAW_WORKFLOW_DRAFT_TTL_SECONDS",
                    str(DEFAULT_TTL_SECONDS),
                )
            ),
        )
    except ValueError:
        return DEFAULT_TTL_SECONDS


def _plan_preview(compiled: dict[str, Any]) -> dict[str, Any]:
    plan = compiled.get("plan") if isinstance(compiled.get("plan"), dict) else {}
    nodes = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
    phases = plan.get("phases") if isinstance(plan.get("phases"), list) else []
    preview_nodes: list[dict[str, Any]] = []
    recipe_pipelines: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        catalog = (
            data.get("workflowCatalog")
            if isinstance(data.get("workflowCatalog"), dict)
            else {}
        )
        primary_recipe_id = str(catalog.get("recipeId") or "").strip()
        primary_recipe_name = str(catalog.get("recipeName") or "").strip()
        raw_pipeline = (
            catalog.get("recipePipeline")
            if isinstance(catalog.get("recipePipeline"), list)
            else []
        )
        pipeline_steps = []
        if primary_recipe_id:
            pipeline_steps.append(
                {
                    "role": "primary",
                    "id": primary_recipe_id,
                    "name": primary_recipe_name or primary_recipe_id,
                    "version": catalog.get("recipeVersion"),
                }
            )
        for item in raw_pipeline:
            value = item if isinstance(item, dict) else {"id": item}
            recipe_id = str(value.get("id") or "").strip()
            if not recipe_id:
                continue
            pipeline_steps.append(
                {
                    "role": "supplemental",
                    "id": recipe_id,
                    "name": str(value.get("name") or recipe_id).strip(),
                    "version": value.get("version"),
                }
            )
        node_name = str(
            node.get("name")
            or data.get("displayName")
            or data.get("title")
            or node.get("id")
            or ""
        ).strip()
        preview_nodes.append(
            {
                "id": str(node.get("id") or "").strip(),
                "name": node_name,
                "stage": str(node.get("stage") or "").strip(),
                "node_type": str(node.get("node_type") or "").strip(),
                **(
                    {"recipe_pipeline": deepcopy(pipeline_steps)}
                    if pipeline_steps
                    else {}
                ),
            }
        )
        if pipeline_steps:
            recipe_pipelines.append(
                {
                    "node_id": str(node.get("id") or "").strip(),
                    "node_name": node_name,
                    "steps": pipeline_steps,
                }
            )
    return {
        "planner": deepcopy(compiled.get("planner") or plan.get("planner") or {}),
        "preflight": deepcopy(compiled.get("preflight") or {}),
        "title": str(plan.get("summary") or "").strip(),
        "skill_id": str(compiled.get("skill_id") or "").strip(),
        "inputs": deepcopy(plan.get("inputs") or {}),
        "phases": [str(item).strip() for item in phases if str(item).strip()],
        "nodes": preview_nodes,
        "recipe_pipelines": recipe_pipelines,
        "node_count": len(preview_nodes),
        "edge_count": int(compiled.get("edge_count") or 0),
    }


def create_workflow_draft(
    *,
    intent: dict[str, Any],
    compiled: dict[str, Any],
    project_id: str = "",
    canvas_id: str = "",
    run_after_create: bool = False,
) -> dict[str, Any]:
    now = time.time()
    draft_id = f"workflow_draft_{uuid.uuid4().hex}"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "draft_id": draft_id,
        "revision": 1,
        "status": "ready",
        "project_id": project_id or None,
        "canvas_id": canvas_id or None,
        "skill_id": str(compiled.get("skill_id") or "").strip(),
        "run_after_create": bool(run_after_create),
        "intent": deepcopy(intent),
        "compiled": deepcopy(compiled),
        "preview": _plan_preview(compiled),
        "plan_digest": _digest(compiled.get("plan")),
        "created_at": now,
        "updated_at": now,
        "expires_at": now + _ttl_seconds(),
        "confirmed_at": None,
    }
    _atomic_write(_draft_path(draft_id), payload)
    return deepcopy(payload)


def read_workflow_draft(draft_id: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = _read(_draft_path(draft_id))
    except ValueError as exc:
        return None, str(exc)
    if payload is None:
        return None, "workflow draft not found"
    if float(payload.get("expires_at") or 0) < time.time():
        return None, "workflow draft expired"
    return payload, None


def claim_workflow_draft_confirmation(
    draft_id: str,
    *,
    revision: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Atomically reserve one draft confirmation across workers and retries."""
    try:
        with _draft_lock(draft_id) as path:
            payload = _read(path)
            if payload is None:
                return None, {
                    "ok": False,
                    "status": "workflow_draft_unavailable",
                    "error": "workflow draft not found",
                }
            if float(payload.get("expires_at") or 0) < time.time():
                return None, {
                    "ok": False,
                    "status": "workflow_draft_unavailable",
                    "error": "workflow draft expired",
                }
            current_revision = int(payload.get("revision") or 0)
            if revision != current_revision:
                return None, {
                    "ok": False,
                    "status": "workflow_draft_revision_conflict",
                    "error": (
                        f"workflow draft revision changed: expected {revision}, "
                        f"current {current_revision}"
                    ),
                    "current_revision": current_revision,
                }
            status = str(payload.get("status") or "ready").strip()
            if status == "confirmed":
                result = public_workflow_draft(payload)
                result.update(
                    {
                        "status": "workflow_draft_already_confirmed",
                        "message": "该工作流方案已经创建，不会重复创建节点。",
                    }
                )
                return None, result
            if status == "confirming":
                result = public_workflow_draft(payload)
                result.update(
                    {
                        "status": "workflow_draft_confirmation_in_progress",
                        "message": "该工作流方案正在创建或已提交，不会重复创建节点。",
                    }
                )
                return None, result
            now = time.time()
            payload.update(
                {
                    "status": "confirming",
                    "confirmation_started_at": now,
                    "updated_at": now,
                }
            )
            _atomic_write(path, payload)
            return deepcopy(payload), None
    except ValueError as exc:
        return None, {
            "ok": False,
            "status": "workflow_draft_unavailable",
            "error": str(exc),
        }


def finish_workflow_draft_confirmation(
    draft_id: str,
    *,
    outcome: str,
) -> None:
    """Finish or release a confirmation claim without exposing an unlocked transition."""
    if outcome not in {"confirmed", "submitted", "ready"}:
        raise ValueError(f"unsupported workflow draft confirmation outcome: {outcome}")
    try:
        with _draft_lock(draft_id) as path:
            payload = _read(path)
            if payload is None:
                return
            now = time.time()
            payload["status"] = outcome
            payload["updated_at"] = now
            if outcome == "confirmed":
                payload["confirmed_at"] = now
            elif outcome == "ready":
                payload["confirmation_started_at"] = None
            _atomic_write(path, payload)
    except ValueError:
        return


def patch_workflow_draft(
    *,
    draft_id: str,
    changes: dict[str, Any],
    compile_intent: Any,
    expected_revision: int | None = None,
    run_after_create: bool | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    payload, error = read_workflow_draft(draft_id)
    if payload is None:
        return None, {"ok": False, "status": "workflow_draft_unavailable", "error": error}
    status = str(payload.get("status") or "ready").strip()
    if status != "ready":
        return None, {
            "ok": False,
            "status": "workflow_draft_not_editable",
            "error": f"workflow draft cannot be patched while status is {status}",
        }
    current_revision = int(payload.get("revision") or 0)
    if expected_revision is not None and expected_revision != current_revision:
        return None, {
            "ok": False,
            "status": "workflow_draft_revision_conflict",
            "error": (
                f"workflow draft revision changed: expected {expected_revision}, "
                f"current {current_revision}"
            ),
            "current_revision": current_revision,
        }
    unsupported = sorted(set(changes) - PATCHABLE_FIELDS)
    if unsupported:
        return None, {
            "ok": False,
            "status": "invalid_workflow_draft_patch",
            "error": f"unsupported workflow draft field: {unsupported[0]}",
            "unsupported_fields": unsupported,
        }
    intent = deepcopy(payload.get("intent") or {})
    before_intent = deepcopy(intent)
    for key, value in changes.items():
        if value is None:
            intent.pop(key, None)
        elif key in MERGED_OBJECT_FIELDS and isinstance(value, dict):
            current = intent.get(key) if isinstance(intent.get(key), dict) else {}
            merged = {**current, **value}
            intent[key] = {item_key: item for item_key, item in merged.items() if item is not None}
        else:
            intent[key] = deepcopy(value)
    compiled = compile_intent(intent)
    if not isinstance(compiled, dict) or not compiled.get("ok"):
        return None, compiled if isinstance(compiled, dict) else {
            "ok": False,
            "status": "workflow_draft_compile_failed",
            "error": "workflow draft compiler returned an invalid result",
        }
    now = time.time()
    payload.update(
        {
            "revision": current_revision + 1,
            "status": "ready",
            "intent": intent,
            "compiled": deepcopy(compiled),
            "preview": _plan_preview(compiled),
            "plan_digest": _digest(compiled.get("plan")),
            "updated_at": now,
            "expires_at": now + _ttl_seconds(),
            "confirmed_at": None,
            "last_changes": {
                key: deepcopy(intent.get(key))
                for key in changes
                if before_intent.get(key) != intent.get(key)
            },
        }
    )
    if run_after_create is not None:
        payload["run_after_create"] = bool(run_after_create)
    _atomic_write(_draft_path(draft_id), payload)
    return deepcopy(payload), None


def mark_workflow_draft_confirmed(draft_id: str) -> None:
    finish_workflow_draft_confirmation(draft_id, outcome="confirmed")


def public_workflow_draft(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "workflow_draft_ready",
        "schema_version": SCHEMA_VERSION,
        "draft_id": payload.get("draft_id"),
        "revision": payload.get("revision"),
        "draft_status": payload.get("status"),
        "skill_id": payload.get("skill_id"),
        "plan_digest": payload.get("plan_digest"),
        "run_after_create": bool(payload.get("run_after_create")),
        "preview": deepcopy(payload.get("preview") or {}),
        "last_changes": deepcopy(payload.get("last_changes") or {}),
        "expires_at": payload.get("expires_at"),
        "message": "工作流方案草稿已准备完成，可继续调整或确认创建。",
    }
