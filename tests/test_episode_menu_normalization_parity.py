"""The legacy write and the column patch must normalize menus identically.

Legacy normalization lives on CogneeStore.update_episode, not on SQLiteStore's
— the plain store assigns menus straight through. So the pair that has to agree
is the Cognee facade's whole-row write and the patch, because those are the two
routes a real project takes. Anything less means routing an existing project
through the patch would silently rewrite its menus.
"""

from __future__ import annotations

import json

import pytest

from novelvideo.models import NovelProp, NovelScene


@pytest.fixture
async def stores(tmp_path):
    from novelvideo.cognee.pipeline import NovelEpisode
    from novelvideo.sqlite_store import SQLiteStore

    state = tmp_path / "user" / "project"
    state.mkdir(parents=True)
    s = SQLiteStore("user/project", output_dir=str(state), state_dir=str(state))
    await s.initialize()
    await s.load_graph_state()

    await s.add_scene(
        NovelScene(name="郑家别墅客厅", aliases=["郑家客厅", "客厅"])
    )
    await s.add_scene(NovelScene(name="主任办公室"))
    await s.add_prop(
        NovelProp(
            name="怀表",
            aliases=["金怀表"],
            prop_type="object",
            visual_prompt="一只旧金怀表",
            description="祖传怀表",
            owner="郑玉琴",
        )
    )
    await s.load_graph_state()
    await s.add_episodes([NovelEpisode(number=1, title="第一集")])

    from novelvideo.cognee.store import CogneeStore

    legacy = CogneeStore(
        "user/project", output_dir=str(state), state_dir=str(state), sqlite_store=s
    )
    await legacy.load_graph_state()
    try:
        yield legacy, s
    finally:
        await s.close()


async def _row(store, column: str):
    db = await store._ensure_db()
    async with db.execute(f"SELECT {column} FROM episodes WHERE number = 1") as cur:
        return json.loads((await cur.fetchone())[0] or "[]")


MENUS = [
    # An alias, resolved to the canonical scene name.
    {"scene_menu": [{"scene_id": "郑家客厅"}]},
    # Case and spacing variants of the same alias.
    {"scene_menu": [{"scene_id": " 客厅 "}]},
    # A derived scene keeps its base and variant.
    {
        "scene_menu": [
            {"scene_id": "郑家别墅客厅_暴雨版", "base_scene_id": "郑家别墅客厅",
             "variant_id": "暴雨版"}
        ]
    },
    # Duplicates collapse.
    {"scene_menu": [{"scene_id": "主任办公室"}, {"scene_id": "主任办公室"}]},
    # An unknown scene passes through untouched.
    {"scene_menu": [{"scene_id": "查无此地"}]},
    # A prop alias resolves and backfills type, prompt, description and owner.
    {"prop_menu": [{"prop_id": "金怀表"}]},
    # Duplicate props collapse.
    {"prop_menu": [{"prop_id": "怀表"}, {"prop_id": "怀表"}]},
    # An unknown prop keeps whatever the caller supplied.
    {"prop_menu": [{"prop_id": "长剑", "prop_type": "weapon"}]},
    # Emptying a menu is a real update, not a no-op.
    {"scene_menu": []},
    {"prop_menu": []},
]


@pytest.mark.parametrize("menu", MENUS, ids=range(len(MENUS)))
async def test_patch_and_legacy_write_produce_identical_menus(stores, menu):
    legacy, sqlite = stores
    column = "scene_menu_json" if "scene_menu" in menu else "prop_menu_json"

    await legacy.update_episode(1, **menu)
    from_legacy = await _row(sqlite, column)

    await sqlite.patch_episode(1, **menu)
    from_patch = await _row(sqlite, column)

    assert from_patch == from_legacy


async def test_the_patch_leaves_the_other_menu_alone(stores):
    """The whole point: writing one menu must not re-serialise the other."""
    _, sqlite = stores
    await sqlite.patch_episode(1, scene_menu=[{"scene_id": "主任办公室"}])
    await sqlite.patch_episode(1, prop_menu=[{"prop_id": "怀表"}])

    assert await _row(sqlite, "scene_menu_json")
    assert await _row(sqlite, "prop_menu_json")
