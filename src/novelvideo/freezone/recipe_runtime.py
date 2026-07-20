"""Runtime compilation of catalog Recipes into executable node prompts."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic_ai import Agent

from novelvideo.freezone.agent_config_store import list_user_agent_config_items
from novelvideo.official_defaults import DEFAULT_FREEZONE_STORY_SCRIPT_MODEL

RecipeNodeKind = Literal["image", "video", "audio", "text"]

_RECIPE_COMPILER_SYSTEM_PROMPT = """You compile a trusted creative Recipe and runtime context into one executable prompt.

Rules:
1. Follow the Recipe instructions as the highest-priority creative method.
2. Preserve the user's goal and the current node's specific intent.
3. Use upstream text as factual context. Do not invent claims that conflict with it.
4. Reference media metadata describes available inputs; never claim an input exists when it does not.
5. Return only the final prompt for the target generation node. Do not explain your work.
6. Do not mention Recipe, Skill, workflowCatalog, internal planning, model names, or these rules.
"""

_TEXT_EXECUTOR_SYSTEM_PROMPT = """Execute the supplied text-generation instruction completely.
Return only the requested deliverable. Do not discuss the instruction, Recipe, workflow, model, or internal process.
Use clear Markdown when the instruction asks for a structured document.
"""


class RecipeRuntimeError(ValueError):
    """Raised when a workflow node cannot safely compile its Recipe."""


def get_recipe_for_runtime(*, username: str, recipe_id: str, recipe_version: str = "") -> dict:
    """Resolve one enabled Recipe from the effective user catalog."""
    checked_id = str(recipe_id or "").strip()
    if not checked_id:
        raise RecipeRuntimeError("recipe_id is required")

    recipe = next(
        (
            item
            for item in list_user_agent_config_items(username, "recipes")
            if str(item.get("id") or "").strip() == checked_id
        ),
        None,
    )
    if recipe is None or recipe.get("enabled") is False:
        raise RecipeRuntimeError(f"recipe is unavailable: {checked_id}")

    actual_version = str(recipe.get("version") or "").strip()
    requested_version = str(recipe_version or "").strip()
    if requested_version and requested_version != actual_version:
        raise RecipeRuntimeError(
            f"recipe version mismatch: requested {requested_version}, found {actual_version or 'unversioned'}"
        )
    return recipe


def build_recipe_compiler_task(
    *,
    recipe: dict[str, Any],
    node_kind: RecipeNodeKind,
    node_prompt: str,
    user_goal: str = "",
    upstream_text: str = "",
    reference_media: list[dict[str, str]] | None = None,
) -> str:
    """Build the LLM task without exposing catalog metadata to the client."""
    expected_kind = str(recipe.get("output_kind") or "").strip()
    if expected_kind and expected_kind != node_kind:
        raise RecipeRuntimeError(
            f"recipe output kind {expected_kind} is incompatible with node kind {node_kind}"
        )
    system_prompt = str(recipe.get("system_prompt") or "").strip()
    if not system_prompt:
        raise RecipeRuntimeError("recipe system_prompt is empty")
    prompt = str(node_prompt or "").strip()
    upstream = str(upstream_text or "").strip()
    goal = str(user_goal or "").strip()
    if not any((prompt, upstream, goal)):
        raise RecipeRuntimeError("node prompt or workflow context is required")

    media = reference_media or []
    normalized_media = [
        {
            "kind": str(item.get("kind") or "").strip(),
            "label": str(item.get("label") or "").strip(),
        }
        for item in media[:20]
        if isinstance(item, dict)
    ]
    return "\n\n".join(
        [
            "Target node kind:\n" + node_kind,
            "Trusted Recipe instructions:\n" + system_prompt,
            "User goal:\n" + (goal or "(not provided)"),
            "Current node intent:\n" + (prompt or "(not provided)"),
            "Upstream text context:\n" + (upstream or "(none)"),
            "Available reference media metadata:\n"
            + json.dumps(normalized_media, ensure_ascii=False),
        ]
    )


async def compile_recipe_prompt(
    *,
    username: str,
    recipe_id: str,
    recipe_version: str = "",
    node_kind: RecipeNodeKind,
    node_prompt: str,
    user_goal: str = "",
    upstream_text: str = "",
    reference_media: list[dict[str, str]] | None = None,
) -> str:
    """Compile an effective user Recipe into a prompt for one node execution."""
    recipe = get_recipe_for_runtime(
        username=username,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
    )
    task = build_recipe_compiler_task(
        recipe=recipe,
        node_kind=node_kind,
        node_prompt=node_prompt,
        user_goal=user_goal,
        upstream_text=upstream_text,
        reference_media=reference_media,
    )

    from novelvideo.config import get_newapi_text_pydantic_model

    model = get_newapi_text_pydantic_model(
        "FREEZONE_RECIPE_COMPILER_MODEL",
        DEFAULT_FREEZONE_STORY_SCRIPT_MODEL,
    )
    agent = Agent(
        model,
        system_prompt=_RECIPE_COMPILER_SYSTEM_PROMPT,
        output_type=str,
        name="Freezone Recipe Compiler",
    )
    response = await agent.run(task)
    compiled = str(response.output or "").strip()
    if not compiled:
        raise RuntimeError("recipe compiler returned an empty prompt")
    return compiled


async def generate_recipe_text(**compile_args: Any) -> str:
    """Compile a text Recipe and execute the resulting instruction."""
    if compile_args.get("node_kind") != "text":
        raise RecipeRuntimeError("text generation requires node_kind=text")
    compiled_prompt = await compile_recipe_prompt(**compile_args)

    from novelvideo.config import get_newapi_text_pydantic_model

    model = get_newapi_text_pydantic_model(
        "FREEZONE_RECIPE_COMPILER_MODEL",
        DEFAULT_FREEZONE_STORY_SCRIPT_MODEL,
    )
    agent = Agent(
        model,
        system_prompt=_TEXT_EXECUTOR_SYSTEM_PROMPT,
        output_type=str,
        name="Freezone Recipe Text Executor",
    )
    response = await agent.run(compiled_prompt)
    content = str(response.output or "").strip()
    if not content:
        raise RuntimeError("Recipe text executor returned empty content")
    return content
