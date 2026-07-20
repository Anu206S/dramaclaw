from __future__ import annotations

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
    )

    assert "商业摄影" in task
    assert "北欧厨房" in task
    assert "银色金属机身" in task
    assert "产品锚点" in task


@pytest.mark.asyncio
async def test_compile_recipe_prompt_loads_server_recipe_and_returns_only_prompt(monkeypatch):
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

    assert result == "最终可执行提示词"


@pytest.mark.asyncio
async def test_generate_recipe_text_executes_compiled_instruction(monkeypatch):
    monkeypatch.setattr(
        recipe_runtime,
        "compile_recipe_prompt",
        lambda **_kwargs: _async_value("生成三屏详情页方案"),
    )

    class FakeAgent:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run(self, task):
            assert task == "生成三屏详情页方案"
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


async def _async_value(value):
    return value
