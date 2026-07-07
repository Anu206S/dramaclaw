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
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")

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


def test_agent_config_items_include_builtin_catalog_with_user_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    builtin_root = tmp_path / "agent_catalog" / "builtins"
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", builtin_root)
    skill_root = builtin_root / "skills"
    skill_root.mkdir(parents=True)
    (skill_root / "story-skill.json").write_text(
        json.dumps(
            {
                "id": "story-skill",
                "description": "内置故事规则",
                "category": "general",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (skill_root / "image-skill.json").write_text(
        json.dumps(
            {
                "id": "image-skill",
                "description": "内置图像规则",
                "category": "image",
                "enabled": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload={
            "id": "story-skill",
            "description": "用户故事规则",
            "category": "custom",
        },
    )

    listed = agent_config_store.list_user_agent_config_items("alice", "skills")

    assert [item["id"] for item in listed] == ["story-skill", "image-skill"]
    assert listed[0]["description"] == "用户故事规则"
    assert listed[0]["_catalog_source"] == "user"
    assert listed[0]["_catalog_base_source"] == "builtin"
    assert listed[1]["_catalog_source"] == "builtin"


def test_builtin_agent_config_item_can_be_hidden_by_user_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    builtin_root = tmp_path / "agent_catalog" / "builtins"
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", builtin_root)
    skill_root = builtin_root / "skills"
    skill_root.mkdir(parents=True)
    (skill_root / "story-skill.json").write_text(
        json.dumps({"id": "story-skill", "description": "内置故事规则"}, ensure_ascii=False),
        encoding="utf-8",
    )

    deleted = agent_config_store.delete_user_agent_config_item(
        username="alice",
        kind="skills",
        item_id="story-skill",
    )

    assert deleted is True
    assert agent_config_store.list_user_agent_config_items("alice", "skills") == []
    overlay_path = (
        tmp_path
        / "alice"
        / "_account"
        / "freezone"
        / "agent_config"
        / "skills"
        / "story-skill.json"
    )
    assert json.loads(overlay_path.read_text(encoding="utf-8")) == {
        "id": "story-skill",
        "hidden": True,
    }


def test_builtin_agent_config_item_merges_partial_user_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    builtin_root = tmp_path / "agent_catalog" / "builtins"
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", builtin_root)
    skill_root = builtin_root / "skills"
    skill_root.mkdir(parents=True)
    (skill_root / "story-skill.json").write_text(
        json.dumps(
            {
                "id": "story-skill",
                "description": "内置故事规则",
                "category": "general",
                "enabled": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload={"id": "story-skill", "enabled": False},
    )

    listed = agent_config_store.list_user_agent_config_items("alice", "skills")

    assert listed == [
        {
            "id": "story-skill",
            "description": "内置故事规则",
            "category": "general",
            "enabled": False,
            "_catalog_source": "user",
            "_catalog_base_source": "builtin",
        }
    ]


def test_invalid_builtin_catalog_files_are_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    builtin_root = tmp_path / "agent_catalog" / "builtins"
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", builtin_root)
    recipe_root = builtin_root / "recipes"
    recipe_root.mkdir(parents=True)
    (recipe_root / "bad.json").write_text('{"id": "../bad"}', encoding="utf-8")
    (recipe_root / "not-json.json").write_text("{", encoding="utf-8")
    (recipe_root / "valid-recipe.json").write_text(
        json.dumps({"id": "valid-recipe", "name": "内置 Recipe"}, ensure_ascii=False),
        encoding="utf-8",
    )

    listed = agent_config_store.list_user_agent_config_items("alice", "recipes")

    assert [item["id"] for item in listed] == ["valid-recipe"]
    assert listed[0]["_catalog_source"] == "builtin"


def test_user_agent_config_item_rejects_unsafe_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")

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
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")
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
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")

    deleted = agent_config_store.delete_user_agent_config_item(
        username="alice",
        kind="skills",
        item_id="missing-skill",
    )

    assert deleted is False
