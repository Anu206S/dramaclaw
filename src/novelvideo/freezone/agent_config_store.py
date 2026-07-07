"""User-scoped Freezone agent configuration storage."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

from novelvideo.config import OUTPUT_DIR

AgentConfigKind = Literal["skills", "recipes"]

_SAFE_ITEM_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
BUILTIN_AGENT_CATALOG_DIR = Path(__file__).with_name("agent_catalog") / "builtins"


def builtin_agent_catalog_dir(kind: AgentConfigKind | str) -> Path:
    checked_kind = _validate_kind(kind)
    return BUILTIN_AGENT_CATALOG_DIR / checked_kind


def user_agent_config_dir(username: str, kind: AgentConfigKind | str) -> Path:
    checked_kind = _validate_kind(kind)
    return Path(OUTPUT_DIR) / username / "_account" / "freezone" / "agent_config" / checked_kind


def list_user_agent_config_items(username: str, kind: AgentConfigKind | str) -> list[dict]:
    checked_kind = _validate_kind(kind)
    builtin_items_by_id: dict[str, dict] = {}
    for payload in _read_agent_config_items(builtin_agent_catalog_dir(checked_kind)):
        item_id = str(payload["id"])
        payload.setdefault("_catalog_source", "builtin")
        builtin_items_by_id[item_id] = payload

    user_items_by_id = {
        str(payload["id"]): payload
        for payload in _read_agent_config_items(user_agent_config_dir(username, checked_kind))
    }
    user_items = [user_items_by_id[item_id] for item_id in sorted(user_items_by_id)]
    builtin_items = [
        builtin_items_by_id[item_id]
        for item_id in sorted(builtin_items_by_id)
        if item_id not in user_items_by_id
    ]
    return [*user_items, *builtin_items]


def save_user_agent_config_item(
    *,
    username: str,
    kind: AgentConfigKind | str,
    payload: dict,
) -> dict:
    item_id = _validate_item_id(str(payload.get("id") or ""))
    root = user_agent_config_dir(username, kind)
    root.mkdir(parents=True, exist_ok=True)

    target = root / f"{item_id}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, target)
    return payload


def delete_user_agent_config_item(
    *,
    username: str,
    kind: AgentConfigKind | str,
    item_id: str,
) -> bool:
    checked_id = _validate_item_id(item_id)
    target = user_agent_config_dir(username, kind) / f"{checked_id}.json"
    if not target.exists():
        return False
    target.unlink()
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
        items.append(payload)
    return items
