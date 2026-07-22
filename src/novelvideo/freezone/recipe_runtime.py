"""Runtime compilation of catalog Recipes into executable node prompts."""

from __future__ import annotations

import asyncio
import json
import os
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic_ai import Agent

from novelvideo.freezone.agent_config_store import list_user_agent_config_items
from novelvideo.config import OUTPUT_DIR
from novelvideo.official_defaults import DEFAULT_FREEZONE_STORY_SCRIPT_MODEL

RecipeNodeKind = Literal["image", "video", "audio", "text"]
RecipePromptStrategy = Literal["template", "user_message", "previous_output", "llm_refine"]

_PROMPT_CACHE_LIMIT = 128
_PERSISTENT_CACHE_LIMIT = 256
_MAX_GOAL_CHARS = 8_000
_MAX_NODE_PROMPT_CHARS = 12_000
_MAX_UPSTREAM_CHARS = 16_000
_prompt_cache: OrderedDict[str, str] = OrderedDict()
_prompt_inflight: dict[str, asyncio.Task[str]] = {}

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
The trusted Recipe is a production method. If it says to write a downstream prompt, apply that method
directly to produce the final requested text deliverable instead of returning another instruction.
"""


class RecipeRuntimeError(ValueError):
    """Raised when a workflow node cannot safely compile its Recipe."""


def _validate_recipe_kind(recipe: dict[str, Any], node_kind: RecipeNodeKind) -> None:
    expected_kind = str(recipe.get("output_kind") or "").strip()
    if expected_kind and expected_kind != node_kind:
        raise RecipeRuntimeError(
            f"recipe output kind {expected_kind} is incompatible with node kind {node_kind}"
        )


def _limit_model_context(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return f"{text[:half]}\n\n[context truncated]\n\n{text[-half:]}"


def compose_deterministic_prompt(
    *,
    prompt_strategy: RecipePromptStrategy,
    node_prompt: str,
    user_goal: str = "",
    upstream_text: str = "",
) -> str:
    """Resolve strategies that only select or combine already-produced text."""
    prompt = str(node_prompt or "").strip()
    goal = str(user_goal or "").strip()
    upstream = str(upstream_text or "").strip()
    if prompt_strategy == "previous_output":
        parts = [upstream, prompt or goal]
    elif prompt_strategy == "user_message":
        parts = [prompt or goal]
    else:
        parts = [upstream, prompt or goal]
    result = "\n\n".join(part for part in parts if part)
    if not result:
        raise RecipeRuntimeError("node prompt or workflow context is required")
    return result


def _cache_key(*, recipe: dict[str, Any], task: str, node_kind: RecipeNodeKind) -> str:
    material = json.dumps(
        {
            "recipe_id": recipe.get("id"),
            "recipe_version": recipe.get("version"),
            "recipe_prompt": recipe.get("system_prompt"),
            "node_kind": node_kind,
            "task": task,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _persistent_cache_path(username: str, key: str) -> Path:
    return (
        Path(OUTPUT_DIR)
        / username
        / "_account"
        / "freezone"
        / "cache"
        / "recipe_prompts"
        / f"{key}.json"
    )


def _read_persistent_prompt(username: str, key: str) -> str | None:
    path = _persistent_cache_path(username, key)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("cache_key") != key:
        return None
    prompt = str(payload.get("prompt") or "").strip()
    return prompt or None


def _write_persistent_prompt(username: str, key: str, prompt: str) -> None:
    path = _persistent_cache_path(username, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps({"cache_key": key, "prompt": prompt}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    cached_files = sorted(
        path.parent.glob("*.json"),
        key=lambda item: item.stat().st_mtime_ns,
        reverse=True,
    )
    for stale_path in cached_files[_PERSISTENT_CACHE_LIMIT:]:
        stale_path.unlink(missing_ok=True)


def _cache_prompt(key: str, prompt: str, *, username: str) -> None:
    _prompt_cache[key] = prompt
    _prompt_cache.move_to_end(key)
    while len(_prompt_cache) > _PROMPT_CACHE_LIMIT:
        _prompt_cache.popitem(last=False)
    try:
        _write_persistent_prompt(username, key, prompt)
    except OSError:
        pass


async def _run_recipe_compiler(task: str) -> str:
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
    prompt = _limit_model_context(node_prompt, _MAX_NODE_PROMPT_CHARS)
    upstream = _limit_model_context(upstream_text, _MAX_UPSTREAM_CHARS)
    goal = _limit_model_context(user_goal, _MAX_GOAL_CHARS)
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
    prompt_strategy: RecipePromptStrategy = "llm_refine",
) -> str:
    """Compile an effective user Recipe into a prompt for one node execution."""
    if prompt_strategy not in {"template", "user_message", "previous_output", "llm_refine"}:
        raise RecipeRuntimeError(f"unsupported prompt strategy: {prompt_strategy}")
    recipe = get_recipe_for_runtime(
        username=username,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
    )
    _validate_recipe_kind(recipe, node_kind)
    if prompt_strategy != "llm_refine":
        return compose_deterministic_prompt(
            prompt_strategy=prompt_strategy,
            node_prompt=node_prompt,
            user_goal=user_goal,
            upstream_text=upstream_text,
        )
    task = build_recipe_compiler_task(
        recipe=recipe,
        node_kind=node_kind,
        node_prompt=node_prompt,
        user_goal=user_goal,
        upstream_text=upstream_text,
        reference_media=reference_media,
    )
    cache_key = _cache_key(recipe=recipe, task=task, node_kind=node_kind)
    cached = _prompt_cache.get(cache_key)
    if cached is not None:
        _prompt_cache.move_to_end(cache_key)
        return cached
    persisted = _read_persistent_prompt(username, cache_key)
    if persisted is not None:
        _prompt_cache[cache_key] = persisted
        _prompt_cache.move_to_end(cache_key)
        return persisted

    compiler_task = _prompt_inflight.get(cache_key)
    if compiler_task is None:
        compiler_task = asyncio.create_task(_run_recipe_compiler(task))
        _prompt_inflight[cache_key] = compiler_task
    try:
        compiled = await asyncio.shield(compiler_task)
    finally:
        if compiler_task.done() and _prompt_inflight.get(cache_key) is compiler_task:
            _prompt_inflight.pop(cache_key, None)
    _cache_prompt(cache_key, compiled, username=username)
    return compiled


async def generate_recipe_text(**compile_args: Any) -> str:
    """Execute a text Recipe directly in one model call."""
    if compile_args.get("node_kind") != "text":
        raise RecipeRuntimeError("text generation requires node_kind=text")
    recipe = get_recipe_for_runtime(
        username=str(compile_args.get("username") or ""),
        recipe_id=str(compile_args.get("recipe_id") or ""),
        recipe_version=str(compile_args.get("recipe_version") or ""),
    )
    _validate_recipe_kind(recipe, "text")
    task = build_recipe_compiler_task(
        recipe=recipe,
        node_kind="text",
        node_prompt=str(compile_args.get("node_prompt") or ""),
        user_goal=str(compile_args.get("user_goal") or ""),
        upstream_text=str(compile_args.get("upstream_text") or ""),
        reference_media=compile_args.get("reference_media"),
    )
    task += "\n\nExecution requirement:\nProduce the final text deliverable now."

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
    response = await agent.run(task)
    content = str(response.output or "").strip()
    if not content:
        raise RuntimeError("Recipe text executor returned empty content")
    return content
