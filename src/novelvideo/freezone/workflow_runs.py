"""Persistent execution records for Freezone canvas workflows."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from novelvideo.freezone.canvas_lock import canvas_write_lock
from novelvideo.freezone.paths import CANVAS_ID_RE, freezone_root

RUN_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
RUN_STATUSES = {"running", "completed", "failed", "cancelled", "interrupted"}
NODE_STATUSES = {"pending", "running", "completed", "failed", "blocked", "skipped"}
RESUMABLE_RUN_STATUSES = {"running", "failed", "interrupted"}
RESUMABLE_ACTION_STATUSES = {"pending", "running", "failed", "blocked"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def workflow_runs_dir(project_dir: Path, canvas_id: str) -> Path:
    if not CANVAS_ID_RE.match(canvas_id):
        raise ValueError(f"invalid canvas_id: {canvas_id!r}")
    return freezone_root(project_dir) / "_workflow_runs" / canvas_id


def workflow_run_path(project_dir: Path, canvas_id: str, run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")
    return workflow_runs_dir(project_dir, canvas_id) / f"{run_id}.json"


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


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


def _normalize_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in actions:
        if not isinstance(item, dict):
            raise ValueError("each workflow action must be an object")
        node_id = str(item.get("node_id") or "").strip()
        action = str(item.get("action") or "").strip()
        if not node_id or not action:
            raise ValueError("each workflow action requires node_id and action")
        key = (node_id, action)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "node_id": node_id,
                "action": action,
                "status": "pending",
                "updated_at": None,
                "error": None,
            }
        )
    if not normalized:
        raise ValueError("workflow run requires at least one action")
    return normalized


def create_workflow_run(
    *,
    project_dir: Path,
    project_id: str,
    canvas_id: str,
    actions: list[dict[str, Any]],
    actor_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = f"run_{uuid.uuid4().hex}"
    now = _now()
    normalized_actions = _normalize_actions(actions)
    payload: dict[str, Any] = {
        "schema_version": "freezone_workflow_run.v1",
        "run_id": run_id,
        "project_id": project_id,
        "canvas_id": canvas_id,
        "status": "running",
        "resumable": True,
        "created_at": now,
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
        "actor_id": actor_id or None,
        "actions": normalized_actions,
        "metadata": metadata or {},
    }
    with canvas_write_lock(project_dir, canvas_id):
        directory = workflow_runs_dir(project_dir, canvas_id)
        existing_paths = directory.glob("*.json") if directory.is_dir() else []
        for path in existing_paths:
            existing = _read(path)
            if existing is None:
                continue
            if existing.get("status") not in RESUMABLE_RUN_STATUSES:
                continue
            existing["status"] = "cancelled"
            existing["resumable"] = False
            existing["updated_at"] = now
            existing["completed_at"] = now
            existing_metadata = existing.get("metadata")
            existing_metadata = existing_metadata if isinstance(existing_metadata, dict) else {}
            existing_metadata["superseded_by_run_id"] = run_id
            existing["metadata"] = existing_metadata
            _atomic_write(path, existing)
        _atomic_write(workflow_run_path(project_dir, canvas_id, run_id), payload)
    return payload


def reconcile_workflow_runs_with_canvas_nodes(
    *,
    project_dir: Path,
    canvas_id: str,
    existing_node_ids: set[str],
) -> list[str]:
    """Cancel resumable runs after all of their unfinished nodes are deleted."""
    now = _now()
    cancelled: list[str] = []
    with canvas_write_lock(project_dir, canvas_id):
        directory = workflow_runs_dir(project_dir, canvas_id)
        paths = directory.glob("*.json") if directory.is_dir() else []
        for path in paths:
            payload = _read(path)
            if payload is None or payload.get("status") not in RESUMABLE_RUN_STATUSES:
                continue
            actions = payload.get("actions")
            actions = actions if isinstance(actions, list) else []
            unfinished_node_ids = {
                str(item.get("node_id") or "")
                for item in actions
                if isinstance(item, dict)
                and item.get("status") in RESUMABLE_ACTION_STATUSES
                and str(item.get("node_id") or "")
            }
            if not unfinished_node_ids or unfinished_node_ids & existing_node_ids:
                continue
            payload["status"] = "cancelled"
            payload["resumable"] = False
            payload["updated_at"] = now
            payload["completed_at"] = now
            metadata = payload.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            metadata["cancel_reason"] = "workflow_nodes_deleted"
            payload["metadata"] = metadata
            _atomic_write(path, payload)
            cancelled.append(str(payload.get("run_id") or ""))
    return cancelled


def interrupt_stale_workflow_runs(
    *,
    project_dir: Path,
    canvas_id: str,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> list[str]:
    """Mark running records without a recent runner heartbeat as interrupted."""
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(seconds=max(stale_after_seconds, 1))
    interrupted: list[str] = []
    with canvas_write_lock(project_dir, canvas_id):
        directory = workflow_runs_dir(project_dir, canvas_id)
        paths = directory.glob("*.json") if directory.is_dir() else []
        for path in paths:
            payload = _read(path)
            if payload is None or payload.get("status") != "running":
                continue
            try:
                updated_at = datetime.fromisoformat(
                    str(payload.get("updated_at") or "").replace("Z", "+00:00")
                )
            except ValueError:
                updated_at = datetime.min.replace(tzinfo=timezone.utc)
            if updated_at > cutoff:
                continue
            timestamp = current.isoformat().replace("+00:00", "Z")
            payload["status"] = "interrupted"
            payload["resumable"] = True
            payload["updated_at"] = timestamp
            payload["completed_at"] = timestamp
            metadata = payload.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            metadata["interrupt_reason"] = "runner_heartbeat_expired"
            payload["metadata"] = metadata
            _atomic_write(path, payload)
            interrupted.append(str(payload.get("run_id") or ""))
    return interrupted


def read_workflow_run(
    *, project_dir: Path, canvas_id: str, run_id: str
) -> dict[str, Any] | None:
    return _read(workflow_run_path(project_dir, canvas_id, run_id))


def list_workflow_runs(
    *, project_dir: Path, canvas_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    directory = workflow_runs_dir(project_dir, canvas_id)
    if not directory.is_dir():
        return []
    runs = [value for path in directory.glob("*.json") if (value := _read(path)) is not None]
    runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return runs[:limit] if limit > 0 else runs


def update_workflow_run(
    *,
    project_dir: Path,
    canvas_id: str,
    run_id: str,
    status: str | None = None,
    action_updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if status is not None and status not in RUN_STATUSES:
        raise ValueError(f"invalid workflow run status: {status!r}")
    path = workflow_run_path(project_dir, canvas_id, run_id)
    with canvas_write_lock(project_dir, canvas_id):
        payload = _read(path)
        if payload is None:
            return None
        if payload.get("status") == "cancelled":
            return payload
        now = _now()
        actions = payload.get("actions")
        actions = actions if isinstance(actions, list) else []
        by_key = {
            (str(item.get("node_id") or ""), str(item.get("action") or "")): item
            for item in actions
            if isinstance(item, dict)
        }
        for update in action_updates or []:
            if not isinstance(update, dict):
                raise ValueError("each workflow action update must be an object")
            node_id = str(update.get("node_id") or "").strip()
            action = str(update.get("action") or "").strip()
            node_status = str(update.get("status") or "").strip()
            if node_status not in NODE_STATUSES:
                raise ValueError(f"invalid workflow node status: {node_status!r}")
            item = by_key.get((node_id, action))
            if item is None:
                raise ValueError(f"workflow action not found: {node_id}:{action}")
            item["status"] = node_status
            item["updated_at"] = now
            item["error"] = str(update.get("error") or "").strip() or None
        if status is not None:
            payload["status"] = status
            if status in {"completed", "failed", "cancelled", "interrupted"}:
                payload["completed_at"] = now
                payload["resumable"] = status in {"failed", "interrupted"}
        payload["updated_at"] = now
        _atomic_write(path, payload)
        return payload
