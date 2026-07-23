from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from novelvideo.freezone import agent_config_store


def _skill_payload(item_id: str, **overrides) -> dict:
    payload = {
        "id": item_id,
        "name": item_id,
        "description": "测试 Skill",
        "category": "general",
        "triggers": {"keywords": ["测试"], "node_scopes": ["imageGeneration"]},
        "input_parameters": [
            {
                "id": "aspect_ratio",
                "label": "画幅",
                "type": "single_select",
                "required": True,
                "default": "16:9",
                "options": ["16:9", "1:1"],
            }
        ],
        "allowed_recipe_ids": ["general-image"],
        "planning": {
            "planning_notes": "动态执行路径：根据开始前选项和画布素材选择图片生成阶段。",
            "prompt_guide": "输出中文提示词。",
            "conduct_rules": ["生成前确认画幅。"],
        },
        "evaluation": {
            "rating_bands": [{"score": 5, "description": "结果清晰"}],
            "quality_threshold": 4,
            "domain_constraints": ["画幅正确"],
        },
    }
    payload.update(overrides)
    return payload


def _recipe_payload(item_id: str, **overrides) -> dict:
    payload = {
        "id": item_id,
        "name": item_id,
        "output_kind": "image",
        "action_keys": [item_id],
        "system_prompt": "你将把用户输入转换成图片生成提示词。重要：只输出提示词。",
        "must_have_items": ["主体清晰"],
        "planning_prompt": "根据用户目标生成图片提示词。",
        "result_summary": "图片生成指令。",
        "requires_source_media": False,
    }
    payload.update(overrides)
    return payload


def test_user_agent_config_items_are_account_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")

    saved = agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload=_skill_payload("story-skill", description="故事类规则"),
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
                **_skill_payload("story-skill"),
                "description": "内置故事规则",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (skill_root / "image-skill.json").write_text(
        json.dumps(
            {
                **_skill_payload("image-skill"),
                "description": "内置图像规则",
                "category": "image",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload=_skill_payload("story-skill", description="用户故事规则", category="custom"),
    )

    listed = agent_config_store.list_user_agent_config_items("alice", "skills")

    assert [item["id"] for item in listed] == ["story-skill", "image-skill"]
    assert listed[0]["description"] == "用户故事规则"
    assert listed[0]["_catalog_source"] == "user"
    assert listed[0]["_catalog_base_source"] == "builtin"
    assert listed[1]["_catalog_source"] == "builtin"


def test_agent_config_cache_invalidates_when_catalog_file_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    builtin_root = tmp_path / "agent_catalog" / "builtins"
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", builtin_root)
    skill_root = builtin_root / "skills"
    skill_root.mkdir(parents=True)
    target = skill_root / "story-skill.json"
    target.write_text(
        json.dumps(_skill_payload("story-skill", description="第一版"), ensure_ascii=False),
        encoding="utf-8",
    )

    first = agent_config_store.list_user_agent_config_items("alice", "skills")
    assert first[0]["description"] == "第一版"
    first[0]["description"] = "调用方不应污染缓存"

    target.write_text(
        json.dumps(_skill_payload("story-skill", description="第二版更长"), ensure_ascii=False),
        encoding="utf-8",
    )

    second = agent_config_store.list_user_agent_config_items("alice", "skills")
    assert second[0]["description"] == "第二版更长"


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
        json.dumps(_skill_payload("story-skill", description="内置故事规则"), ensure_ascii=False),
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
                **_skill_payload("story-skill"),
                "description": "内置故事规则",
                "enabled": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload=_skill_payload("story-skill", enabled=False),
    )

    listed = agent_config_store.list_user_agent_config_items("alice", "skills")

    assert len(listed) == 1
    assert listed[0]["id"] == "story-skill"
    assert listed[0]["description"] == "测试 Skill"
    assert listed[0]["enabled"] is False
    assert listed[0]["_catalog_source"] == "user"
    assert listed[0]["_catalog_base_source"] == "builtin"
    assert listed[0]["schema_version"] == "dramaclaw.workflow-skill.v1"


def test_agent_config_items_sort_user_then_customized_then_builtin_by_mtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    builtin_root = tmp_path / "agent_catalog" / "builtins"
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", builtin_root)
    skill_root = builtin_root / "skills"
    skill_root.mkdir(parents=True)
    for item_id in ["builtin-a", "custom-a", "custom-b"]:
        (skill_root / f"{item_id}.json").write_text(
            json.dumps(_skill_payload(item_id, description=item_id), ensure_ascii=False),
            encoding="utf-8",
        )

    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload=_skill_payload("custom-a", description="定制旧"),
    )
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload=_skill_payload("user-old", description="用户旧"),
    )
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload=_skill_payload("custom-b", description="定制新"),
    )
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="skills",
        payload=_skill_payload("user-new", description="用户新"),
    )
    user_root = agent_config_store.user_agent_config_dir("alice", "skills")
    mtimes = {
        "custom-a": 10,
        "user-old": 20,
        "custom-b": 30,
        "user-new": 40,
    }
    for item_id, mtime in mtimes.items():
        os.utime(user_root / f"{item_id}.json", (mtime, mtime))

    listed = agent_config_store.list_user_agent_config_items("alice", "skills")

    assert [item["id"] for item in listed] == [
        "user-new",
        "user-old",
        "custom-b",
        "custom-a",
        "builtin-a",
    ]
    assert listed[0]["_catalog_source"] == "user"
    assert "_catalog_base_source" not in listed[0]
    assert listed[2]["_catalog_base_source"] == "builtin"
    assert listed[-1]["_catalog_source"] == "builtin"


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
        json.dumps(_recipe_payload("valid-recipe", name="内置 Recipe"), ensure_ascii=False),
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
            payload=_recipe_payload("../escape", name="bad"),
        )


def test_user_agent_config_item_rejects_structurally_invalid_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")

    with pytest.raises(ValueError, match="invalid agent config skills"):
        agent_config_store.save_user_agent_config_item(
            username="alice",
            kind="skills",
            payload={"id": "loose-skill", "description": "只有 id 和描述"},
        )


def test_user_agent_config_item_rejects_structurally_invalid_recipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")

    with pytest.raises(ValueError, match="invalid agent config recipes"):
        agent_config_store.save_user_agent_config_item(
            username="alice",
            kind="recipes",
            payload={"id": "loose-recipe", "name": "只有名字"},
        )


def test_invalid_builtin_catalog_files_missing_schema_fields_are_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    builtin_root = tmp_path / "agent_catalog" / "builtins"
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", builtin_root)
    skill_root = builtin_root / "skills"
    skill_root.mkdir(parents=True)
    (skill_root / "loose-skill.json").write_text(
        json.dumps({"id": "loose-skill", "description": "只有描述"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (skill_root / "valid-skill.json").write_text(
        json.dumps(_skill_payload("valid-skill"), ensure_ascii=False),
        encoding="utf-8",
    )

    listed = agent_config_store.list_user_agent_config_items("alice", "skills")

    assert [item["id"] for item in listed] == ["valid-skill"]


def test_user_agent_config_item_can_be_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_config_store, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(agent_config_store, "BUILTIN_AGENT_CATALOG_DIR", tmp_path / "builtins")
    agent_config_store.save_user_agent_config_item(
        username="alice",
        kind="recipes",
        payload=_recipe_payload("ad-recipe", name="广告 Recipe"),
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
