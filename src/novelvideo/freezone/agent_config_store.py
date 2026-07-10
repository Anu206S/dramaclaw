"""User-scoped Freezone agent configuration storage."""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Literal

from novelvideo.config import OUTPUT_DIR

AgentConfigKind = Literal["skills", "recipes"]

_SAFE_ITEM_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
BUILTIN_AGENT_CATALOG_DIR = Path(__file__).with_name("agent_catalog") / "builtins"
_CATALOG_CACHE: dict[tuple[str, str, tuple, tuple], list[dict]] = {}


def builtin_agent_catalog_dir(kind: AgentConfigKind | str) -> Path:
    checked_kind = _validate_kind(kind)
    return BUILTIN_AGENT_CATALOG_DIR / checked_kind


def user_agent_config_dir(username: str, kind: AgentConfigKind | str) -> Path:
    checked_kind = _validate_kind(kind)
    return Path(OUTPUT_DIR) / username / "_account" / "freezone" / "agent_config" / checked_kind


def list_user_agent_config_items(username: str, kind: AgentConfigKind | str) -> list[dict]:
    checked_kind = _validate_kind(kind)
    builtin_root = builtin_agent_catalog_dir(checked_kind)
    user_root = user_agent_config_dir(username, checked_kind)
    cache_key = (
        username,
        checked_kind,
        _directory_signature(builtin_root),
        _directory_signature(user_root),
    )
    cached = _CATALOG_CACHE.get(cache_key)
    if cached is not None:
        return deepcopy(cached)

    builtin_items_by_id: dict[str, dict] = {}
    for payload in _read_agent_config_items(builtin_root):
        item_id = str(payload["id"])
        builtin_items_by_id[item_id] = payload

    user_items_by_id = {
        str(payload["id"]): payload
        for payload in _read_agent_config_items(user_root)
    }
    user_items: list[dict] = []
    for item_id in sorted(user_items_by_id):
        user_payload = user_items_by_id[item_id]
        if user_payload.get("hidden") is True:
            continue
        builtin_payload = builtin_items_by_id.get(item_id)
        if builtin_payload is not None:
            merged_payload = {**builtin_payload, **user_payload}
            merged_payload["_catalog_source"] = "user"
            merged_payload["_catalog_base_source"] = "builtin"
            user_items.append(merged_payload)
            continue
        user_payload.setdefault("_catalog_source", "user")
        user_items.append(user_payload)
    user_items.sort(key=_user_agent_config_sort_key)

    builtin_items = [
        {**builtin_items_by_id[item_id], "_catalog_source": "builtin"}
        for item_id in sorted(builtin_items_by_id)
        if item_id not in user_items_by_id
    ]
    items = [*user_items, *builtin_items]
    _CATALOG_CACHE.clear()
    _CATALOG_CACHE[cache_key] = deepcopy(items)
    return items


def save_user_agent_config_item(
    *,
    username: str,
    kind: AgentConfigKind | str,
    payload: dict,
) -> dict:
    item_id = _validate_item_id(str(payload.get("id") or ""))
    root = user_agent_config_dir(username, kind)
    root.mkdir(parents=True, exist_ok=True)
    stored_payload = _strip_response_metadata(payload)

    target = root / f"{item_id}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(stored_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, target)
    _CATALOG_CACHE.clear()
    return stored_payload


def delete_user_agent_config_item(
    *,
    username: str,
    kind: AgentConfigKind | str,
    item_id: str,
) -> bool:
    checked_id = _validate_item_id(item_id)
    checked_kind = _validate_kind(kind)
    user_root = user_agent_config_dir(username, checked_kind)
    target = user_root / f"{checked_id}.json"
    if _builtin_agent_config_exists(checked_kind, checked_id):
        user_root.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"id": checked_id, "hidden": True}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, target)
        _CATALOG_CACHE.clear()
        return True
    if not target.exists():
        return False
    target.unlink()
    _CATALOG_CACHE.clear()
    return True


def _validate_kind(kind: AgentConfigKind | str) -> AgentConfigKind:
    if kind in {"skills", "recipes"}:
        return kind  # type: ignore[return-value]
    raise ValueError("invalid agent config kind")


def _validate_item_id(item_id: str) -> str:
    if not _SAFE_ITEM_ID.fullmatch(item_id):
        raise ValueError("invalid agent config id")
    return item_id


def _read_agent_config_items(root: Path) -> list[dict]:
    if not root.exists():
        return []

    items: list[dict] = []
    for path in sorted(root.glob("*.json"), key=lambda item: item.name):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        item_id = payload.get("id")
        if not isinstance(item_id, str) or not _SAFE_ITEM_ID.fullmatch(item_id):
            continue
        try:
            payload["_catalog_updated_at"] = path.stat().st_mtime
        except OSError:
            payload["_catalog_updated_at"] = 0
        items.append(payload)
    return items


def _directory_signature(root: Path) -> tuple:
    if not root.exists():
        return (str(root), "missing")
    if not root.is_dir():
        return (str(root), "not-dir")
    files: list[tuple[str, int, int]] = []
    for path in sorted(root.glob("*.json"), key=lambda item: item.name):
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((path.name, stat.st_mtime_ns, stat.st_size))
    return (str(root), tuple(files))


def _builtin_agent_config_exists(kind: AgentConfigKind, item_id: str) -> bool:
    return (builtin_agent_catalog_dir(kind) / f"{item_id}.json").exists()


def _strip_response_metadata(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if not key.startswith("_catalog_")}


def _user_agent_config_sort_key(payload: dict) -> tuple[int, float, str]:
    priority = 1 if payload.get("_catalog_base_source") == "builtin" else 0
    updated_at = payload.get("_catalog_updated_at")
    if not isinstance(updated_at, int | float):
        updated_at = 0
    item_id = str(payload.get("id") or "")
    return (priority, -float(updated_at), item_id)
