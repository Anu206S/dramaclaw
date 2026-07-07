from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelvideo.freezone import agent_config_store


def test_user_agent_config_items_are_account_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))

    saved = agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload={
            "id": "story-skill",
            "description": "故事类规则",
            "category": "general",
        },
    )

    assert saved["id"] == "story-skill"
    target = (
        tmp_path
        / "alice"
        / "_account"
        / "freezone"
        / "agent_config"
        / "skills"
        / "story-skill.json"
    )
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["description"] == "故事类规则"

    listed = agent_config_store.list_user_agent_config_items("alice", "skills")
    assert [item["id"] for item in listed] == ["story-skill"]
    assert agent_config_store.list_user_agent_config_items("bob", "skills") == []


def test_user_agent_config_item_rejects_unsafe_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="invalid agent config id"):
        agent_config_store.save_user_agent_config_item(
            username="alice",
            kind="recipes",
            payload={"id": "../escape", "name": "bad"},
        )


def test_user_agent_config_item_can_be_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="recipes",
        payload={"id": "ad-recipe", "name": "广告 Recipe"},
    )

    deleted = agent_config_store.delete_user_agent_config_item(
        username="alice",
        kind="recipes",
        item_id="ad-recipe",
    )

    assert deleted is True
    assert agent_config_store.list_user_agent_config_items("alice", "recipes") == []


def test_user_agent_config_delete_missing_item_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))

    deleted = agent_config_store.delete_user_agent_config_item(
        username="alice",
        kind="skills",
        item_id="missing-skill",
    )

    assert deleted is False
