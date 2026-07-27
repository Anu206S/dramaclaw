from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from novelvideo.freezone import recipe_runtime


def test_build_recipe_compiler_task_checks_output_kind():
    with pytest.raises(recipe_runtime.RecipeRuntimeError, match="incompatible"):
        recipe_runtime.build_recipe_compiler_task(
            recipe={"id": "image-only", "output_kind": "image", "system_prompt": "refine"},
            node_kind="video",
            node_prompt="rotate product",
        )


def test_build_recipe_compiler_task_contains_runtime_context():
    task = recipe_runtime.build_recipe_compiler_task(
        recipe={"id": "scene", "output_kind": "image", "system_prompt": "商业摄影"},
        node_kind="image",
        node_prompt="北欧厨房",
        user_goal="生成三张咖啡机商品图",
        upstream_text="银色金属机身",
        reference_media=[{"kind": "image", "label": "产品锚点"}],
        confirmed_inputs={"aspect_ratio": "9:16", "language": "zh"},
        creative_settings={
            "aesthetic": {
                "label": "王家卫电影感",
                "prompt_guide": "高饱和霓虹色，手持摄影与步印效果",
                "negative_prompt": "避免明亮商业棚拍",
            },
            "anchor_bindings": [
                {"node_id": "character-1", "label": "女主角", "target_item_ids": ["shot-1"]}
            ],
        },
        skill_constraints={
            "hard_constraints": ["不得虚构产品功能", "不要字幕"],
            "prompt_guide": "高端商业摄影",
        },
        skill_id="ecommerce",
        skill_version="2.1.0",
    )

    assert "商业摄影" in task
    assert "北欧厨房" in task
    assert "银色金属机身" in task
    assert "产品锚点" in task
    assert '"aspect_ratio": "9:16"' in task
    assert "不得虚构产品功能" in task
    assert "高端商业摄影" in task
    assert "王家卫电影感" in task
    assert "女主角" in task
    assert '"version": "2.1.0"' in task


def test_get_skill_for_runtime_enforces_version_and_recipe_whitelist(monkeypatch):
    monkeypatch.setattr(
        recipe_runtime,
        "list_user_agent_config_items",
        lambda _username, kind: [
            {
                "id": "ecommerce",
                "version": "2.1.0",
                "allowed_recipe_ids": ["product-image"],
            }
        ]
        if kind == "skills"
        else [],
    )

    skill = recipe_runtime.get_skill_for_runtime(
        username="local",
        skill_id="ecommerce",
        skill_version="2.1.0",
        recipe_id="product-image",
    )
    assert skill is not None

    with pytest.raises(recipe_runtime.RecipeRuntimeError, match="version mismatch"):
        recipe_runtime.get_skill_for_runtime(
            username="local",
            skill_id="ecommerce",
            skill_version="1.0.0",
            recipe_id="product-image",
        )
    with pytest.raises(recipe_runtime.RecipeRuntimeError, match="not allowed"):
        recipe_runtime.get_skill_for_runtime(
            username="local",
            skill_id="ecommerce",
            recipe_id="other-image",
        )
    extended = recipe_runtime.get_skill_for_runtime(
        username="local",
        skill_id="ecommerce",
        recipe_id="other-image",
        creative_settings={"recipe_extensions": ["other-image"]},
    )
    assert extended is not None


def test_resolve_creative_settings_expands_catalog_references(monkeypatch):
    def catalog(_username, kind):
        if kind == "aesthetics":
            return [
                {
                    "id": "neon-film",
                    "name": "霓虹电影感",
                    "prompt_guide": "高饱和霓虹色",
                    "negative_prompt": "避免棚拍",
                }
            ]
        if kind == "anchor_sets":
            return [
                {
                    "id": "hero-assets",
                    "anchors": [
                        {
                            "node_id": "hero-node",
                            "node_type": "imageGenNode",
                            "label": "主角",
                            "target_item_ids": ["shot-1"],
                        }
                    ],
                }
            ]
        return []

    monkeypatch.setattr(recipe_runtime, "list_user_agent_config_items", catalog)

    resolved = recipe_runtime.resolve_creative_settings(
        username="local",
        creative_settings={
            "aesthetic_id": "neon-film",
            "anchor_set_ids": ["hero-assets"],
        },
    )

    assert resolved["aesthetic"]["label"] == "霓虹电影感"
    assert resolved["anchor_bindings"][0]["node_id"] == "hero-node"


def test_combined_recipe_preserves_pipeline_order():
    combined = recipe_runtime._combined_recipe(
        [
            {
                "id": "shotlist",
                "name": "分镜方法",
                "version": 1,
                "output_kind": "image",
                "system_prompt": "先确定镜头信息。",
            },
            {
                "id": "lighting",
                "name": "布光方法",
                "version": 2,
                "output_kind": "image",
                "system_prompt": "再设计光线。",
            },
        ]
    )

    assert combined["id"] == "shotlist+lighting"
    assert combined["system_prompt"].index("先确定镜头信息") < combined[
        "system_prompt"
    ].index("再设计光线")


def test_recipe_compiler_priority_places_skill_before_recipe():
    assert "confirmed inputs, Skill hard constraints" in recipe_runtime._RECIPE_COMPILER_SYSTEM_PROMPT
    assert "confirmed creative settings" in recipe_runtime._RECIPE_COMPILER_SYSTEM_PROMPT
    assert "Recipe method, then defaults" in recipe_runtime._RECIPE_COMPILER_SYSTEM_PROMPT


def test_build_recipe_compiler_task_limits_large_upstream_context():
    upstream = "A" * 20_000 + "B" * 20_000
    task = recipe_runtime.build_recipe_compiler_task(
        recipe={"id": "scene", "output_kind": "image", "system_prompt": "商业摄影"},
        node_kind="image",
        node_prompt="厨房",
        upstream_text=upstream,
    )

    assert "[context truncated]" in task
    assert "A" * 100 in task
    assert "B" * 100 in task
    assert len(task) < 18_000


@pytest.mark.asyncio
async def test_compile_recipe_prompt_loads_server_recipe_and_returns_only_prompt(
    monkeypatch, tmp_path
):
    recipe_runtime._prompt_cache.clear()
    recipe_runtime._prompt_inflight.clear()
    monkeypatch.setattr(recipe_runtime, "OUTPUT_DIR", tmp_path)
    calls = 0
    monkeypatch.setattr(
        recipe_runtime,
        "get_recipe_for_runtime",
        lambda **_kwargs: {
            "id": "scene",
            "version": 1,
            "output_kind": "image",
            "system_prompt": "trusted internal method",
        },
    )

    class FakeAgent:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run(self, task):
            nonlocal calls
            calls += 1
            assert "trusted internal method" in task
            return SimpleNamespace(output="最终可执行提示词")

    monkeypatch.setattr(recipe_runtime, "Agent", FakeAgent)
    monkeypatch.setattr(
        "novelvideo.config.get_newapi_text_pydantic_model",
        lambda *_args, **_kwargs: object(),
    )

    result = await recipe_runtime.compile_recipe_prompt(
        username="local",
        recipe_id="scene",
        recipe_version="1",
        node_kind="image",
        node_prompt="厨房场景",
    )
    cached = await recipe_runtime.compile_recipe_prompt(
        username="local",
        recipe_id="scene",
        recipe_version="1",
        node_kind="image",
        node_prompt="厨房场景",
    )

    assert result == "最终可执行提示词"
    assert cached == result
    assert calls == 1

    recipe_runtime._prompt_cache.clear()
    persisted = await recipe_runtime.compile_recipe_prompt(
        username="local",
        recipe_id="scene",
        recipe_version="1",
        node_kind="image",
        node_prompt="厨房场景",
    )
    assert persisted == result
    assert calls == 1


@pytest.mark.asyncio
async def test_compile_recipe_prompt_deduplicates_concurrent_model_calls(monkeypatch, tmp_path):
    recipe_runtime._prompt_cache.clear()
    recipe_runtime._prompt_inflight.clear()
    monkeypatch.setattr(recipe_runtime, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        recipe_runtime,
        "get_recipe_for_runtime",
        lambda **_kwargs: {
            "id": "scene",
            "version": 1,
            "output_kind": "image",
            "system_prompt": "trusted internal method",
        },
    )
    calls = 0

    class FakeAgent:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run(self, _task):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return SimpleNamespace(output="共享提示词")

    monkeypatch.setattr(recipe_runtime, "Agent", FakeAgent)
    monkeypatch.setattr(
        "novelvideo.config.get_newapi_text_pydantic_model",
        lambda *_args, **_kwargs: object(),
    )
    kwargs = {
        "username": "local",
        "recipe_id": "scene",
        "recipe_version": "1",
        "node_kind": "image",
        "node_prompt": "厨房场景",
    }

    results = await asyncio.gather(
        recipe_runtime.compile_recipe_prompt(**kwargs),
        recipe_runtime.compile_recipe_prompt(**kwargs),
    )

    assert results == ["共享提示词", "共享提示词"]
    assert calls == 1


@pytest.mark.asyncio
async def test_compile_recipe_prompt_uses_fallback_on_timeout_and_caches_late_result(
    monkeypatch,
    tmp_path,
):
    recipe_runtime._prompt_cache.clear()
    recipe_runtime._prompt_inflight.clear()
    monkeypatch.setattr(recipe_runtime, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        recipe_runtime,
        "get_recipe_for_runtime",
        lambda **_kwargs: {
            "id": "scene",
            "version": 1,
            "output_kind": "image",
            "system_prompt": "可信的商品摄影方法",
        },
    )

    async def slow_compiler(_task: str) -> str:
        await asyncio.sleep(0.03)
        return "后台完成的精炼提示词"

    monkeypatch.setattr(recipe_runtime, "_run_recipe_compiler", slow_compiler)
    monkeypatch.setattr(recipe_runtime, "_recipe_compiler_timeout_seconds", lambda: 0.01)

    fallback = await recipe_runtime.compile_recipe_prompt(
        username="local",
        recipe_id="scene",
        recipe_version="1",
        node_kind="image",
        node_prompt="厨房场景",
        user_goal="生成咖啡机商品图",
    )

    assert "生成咖啡机商品图" in fallback
    assert "厨房场景" in fallback
    assert "可信的商品摄影方法" in fallback

    await asyncio.sleep(0.04)
    assert recipe_runtime._prompt_inflight == {}
    assert "后台完成的精炼提示词" in recipe_runtime._prompt_cache.values()

    cached = await recipe_runtime.compile_recipe_prompt(
        username="local",
        recipe_id="scene",
        recipe_version="1",
        node_kind="image",
        node_prompt="厨房场景",
        user_goal="生成咖啡机商品图",
    )
    assert cached == "后台完成的精炼提示词"


@pytest.mark.asyncio
async def test_compile_recipe_prompt_skips_model_for_deterministic_strategy(monkeypatch):
    monkeypatch.setattr(
        recipe_runtime,
        "get_recipe_for_runtime",
        lambda **_kwargs: {
            "id": "video",
            "output_kind": "video",
            "system_prompt": "refine video prompt",
        },
    )

    class UnexpectedAgent:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("deterministic strategy must not create an Agent")

    monkeypatch.setattr(recipe_runtime, "Agent", UnexpectedAgent)
    result = await recipe_runtime.compile_recipe_prompt(
        username="local",
        recipe_id="video",
        node_kind="video",
        node_prompt="镜头缓慢推进",
        upstream_text="商品分镜",
        prompt_strategy="previous_output",
    )

    assert result == "商品分镜\n\n镜头缓慢推进"


@pytest.mark.asyncio
async def test_generate_recipe_text_executes_compiled_instruction(monkeypatch):
    monkeypatch.setattr(
        recipe_runtime,
        "get_recipe_for_runtime",
        lambda **_kwargs: {
            "id": "ecommerce-text-plan",
            "output_kind": "text",
            "system_prompt": "生成三屏详情页方案",
        },
    )

    class FakeAgent:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run(self, task):
            assert "生成三屏详情页方案" in task
            assert "Produce the final text deliverable now" in task
            return SimpleNamespace(output="# 详情页方案")

    monkeypatch.setattr(recipe_runtime, "Agent", FakeAgent)
    monkeypatch.setattr(
        "novelvideo.config.get_newapi_text_pydantic_model",
        lambda *_args, **_kwargs: object(),
    )

    result = await recipe_runtime.generate_recipe_text(
        username="local",
        recipe_id="ecommerce-text-plan",
        node_kind="text",
        node_prompt="咖啡机",
    )

    assert result == "# 详情页方案"
