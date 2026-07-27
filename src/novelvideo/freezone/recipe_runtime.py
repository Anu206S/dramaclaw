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
_MAX_CONFIRMED_INPUTS_CHARS = 8_000
_MAX_SKILL_CONSTRAINTS_CHARS = 12_000
_prompt_cache: OrderedDict[str, str] = OrderedDict()
_prompt_inflight: dict[str, asyncio.Task[str]] = {}

_RECIPE_COMPILER_SYSTEM_PROMPT = """You compile a trusted creative Recipe and runtime context into one executable prompt.

Rules:
1. Resolve conflicts in this order: explicit user goal, confirmed inputs, Skill hard constraints,
   confirmed creative settings, Skill prompt guide, Recipe method, then defaults.
2. Recipe instructions are a reusable production method, not permission to override higher-priority
   user choices or Skill constraints.
3. Preserve the current node's specific intent.
4. Use upstream text as factual context. Do not invent claims that conflict with it.
5. Reference media metadata describes available inputs; never claim an input exists when it does not.
6. Return only the final prompt for the target generation node. Do not explain your work.
7. Do not mention Recipe, Skill, workflowCatalog, internal planning, model names, or these rules.
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


def get_recipe_pipeline_for_runtime(
    *,
    username: str,
    primary_recipe: dict[str, Any],
    recipe_pipeline: list[str | dict[str, Any]] | None,
    node_kind: RecipeNodeKind,
) -> list[dict[str, Any]]:
    """Resolve an ordered, de-duplicated Recipe pipeline for one node."""
    recipes = [primary_recipe]
    seen = {str(primary_recipe.get("id") or "").strip()}
    for raw_item in recipe_pipeline or []:
        checked_id = str(
            (raw_item.get("id") or "") if isinstance(raw_item, dict) else raw_item or ""
        ).strip()
        requested_version = str(
            (raw_item.get("version") or "") if isinstance(raw_item, dict) else ""
        ).strip()
        if not checked_id or checked_id in seen:
            continue
        recipe = get_recipe_for_runtime(
            username=username,
            recipe_id=checked_id,
            recipe_version=requested_version,
        )
        _validate_recipe_kind(recipe, node_kind)
        recipes.append(recipe)
        seen.add(checked_id)
    return recipes


def _combined_recipe(recipes: list[dict[str, Any]]) -> dict[str, Any]:
    if len(recipes) == 1:
        return recipes[0]
    primary = recipes[0]
    instructions = []
    for index, recipe in enumerate(recipes, start=1):
        instructions.append(
            f"{index}. {str(recipe.get('name') or recipe.get('id') or '').strip()}\n"
            f"{str(recipe.get('system_prompt') or '').strip()}"
        )
    return {
        **primary,
        "id": "+".join(str(recipe.get("id") or "").strip() for recipe in recipes),
        "version": "+".join(str(recipe.get("version") or "").strip() for recipe in recipes),
        "system_prompt": (
            "Apply these compatible production methods in the stated order. "
            "Later methods refine the result but do not erase earlier requirements.\n\n"
            + "\n\n".join(instructions)
        ),
    }


def get_skill_for_runtime(
    *,
    username: str,
    skill_id: str,
    skill_version: str = "",
    recipe_id: str,
    creative_settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the trusted Skill and enforce its Recipe boundary."""
    checked_id = str(skill_id or "").strip()
    if not checked_id:
        return None
    skill = next(
        (
            item
            for item in list_user_agent_config_items(username, "skills")
            if str(item.get("id") or "").strip() == checked_id
        ),
        None,
    )
    if skill is None or skill.get("enabled") is False:
        raise RecipeRuntimeError(f"skill is unavailable: {checked_id}")

    actual_version = str(skill.get("version") or "").strip()
    requested_version = str(skill_version or "").strip()
    if requested_version and requested_version != actual_version:
        raise RecipeRuntimeError(
            f"skill version mismatch: requested {requested_version}, "
            f"found {actual_version or 'unversioned'}"
        )
    allowed_recipe_ids = {
        str(item).strip() for item in skill.get("allowed_recipe_ids") or [] if str(item).strip()
    }
    recipe_extensions = {
        str(item).strip()
        for item in (creative_settings or {}).get("recipe_extensions") or []
        if str(item).strip()
    }
    allowed_recipe_ids.update(recipe_extensions)
    if recipe_id not in allowed_recipe_ids:
        raise RecipeRuntimeError(f"recipe {recipe_id} is not allowed by skill {checked_id}")
    return skill


def _skill_constraints(skill: dict[str, Any] | None) -> dict[str, Any]:
    if not skill:
        return {}
    planning = skill.get("planning") if isinstance(skill.get("planning"), dict) else {}
    evaluation = skill.get("evaluation") if isinstance(skill.get("evaluation"), dict) else {}
    return {
        "hard_constraints": [
            *(
                planning.get("conduct_rules")
                if isinstance(planning.get("conduct_rules"), list)
                else []
            ),
            *(
                evaluation.get("domain_constraints")
                if isinstance(evaluation.get("domain_constraints"), list)
                else []
            ),
        ],
        "prompt_guide": str(planning.get("prompt_guide") or "").strip(),
    }


def resolve_creative_settings(
    *, username: str, creative_settings: dict[str, Any] | None
) -> dict[str, Any]:
    """Expand trusted Aesthetic and AnchorSet references while preserving inline overrides."""
    value = dict(creative_settings or {})
    aesthetic_id = str(
        value.get("aesthetic_id") or value.get("aestheticId") or ""
    ).strip()
    if aesthetic_id:
        aesthetic = next(
            (
                item
                for item in list_user_agent_config_items(username, "aesthetics")
                if str(item.get("id") or "").strip() == aesthetic_id
                and item.get("enabled") is not False
            ),
            None,
        )
        if aesthetic is None:
            raise RecipeRuntimeError(f"aesthetic is unavailable: {aesthetic_id}")
        value["aesthetic_id"] = aesthetic_id
        value["aesthetic"] = {
            "label": str(aesthetic.get("name") or aesthetic_id).strip(),
            "prompt_guide": str(aesthetic.get("prompt_guide") or "").strip(),
            "negative_prompt": str(aesthetic.get("negative_prompt") or "").strip(),
            **(value.get("aesthetic") if isinstance(value.get("aesthetic"), dict) else {}),
        }

    anchor_set_ids = value.get("anchor_set_ids") or value.get("anchorSetIds") or []
    if not isinstance(anchor_set_ids, list):
        raise RecipeRuntimeError("anchor_set_ids must be an array")
    stored_bindings: list[dict[str, Any]] = []
    resolved_ids: list[str] = []
    if anchor_set_ids:
        available_sets = {
            str(item.get("id") or "").strip(): item
            for item in list_user_agent_config_items(username, "anchor_sets")
            if item.get("enabled") is not False
        }
        for raw_id in anchor_set_ids:
            anchor_set_id = str(raw_id or "").strip()
            anchor_set = available_sets.get(anchor_set_id)
            if anchor_set is None:
                raise RecipeRuntimeError(f"anchor set is unavailable: {anchor_set_id}")
            if anchor_set_id in resolved_ids:
                continue
            resolved_ids.append(anchor_set_id)
            stored_bindings.extend(
                item for item in anchor_set.get("anchors") or [] if isinstance(item, dict)
            )
    inline_bindings = value.get("anchor_bindings") or value.get("anchorBindings") or []
    if not isinstance(inline_bindings, list):
        raise RecipeRuntimeError("anchor_bindings must be an array")
    if resolved_ids:
        value["anchor_set_ids"] = resolved_ids
    if stored_bindings or inline_bindings:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for binding in [*stored_bindings, *inline_bindings]:
            if not isinstance(binding, dict):
                continue
            node_id = str(binding.get("node_id") or binding.get("nodeId") or "").strip()
            targets = tuple(
                str(item or "").strip()
                for item in (
                    binding.get("target_item_ids")
                    or binding.get("targetItemIds")
                    or []
                )
                if str(item or "").strip()
            )
            key = (node_id, targets)
            if not node_id or key in seen:
                continue
            seen.add(key)
            deduped.append(binding)
        value["anchor_bindings"] = deduped
    return value


def _creative_context(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    aesthetic = value.get("aesthetic")
    if isinstance(aesthetic, dict):
        result["aesthetic"] = {
            "label": str(aesthetic.get("label") or "").strip(),
            "prompt_guide": str(
                aesthetic.get("prompt_guide") or aesthetic.get("promptGuide") or ""
            ).strip(),
            "negative_prompt": str(
                aesthetic.get("negative_prompt") or aesthetic.get("negativePrompt") or ""
            ).strip(),
        }
    extensions = value.get("recipe_extensions")
    if isinstance(extensions, list):
        result["recipe_extensions"] = [
            str(item).strip() for item in extensions[:12] if str(item).strip()
        ]
    bindings = value.get("anchor_bindings")
    if isinstance(bindings, list):
        result["anchor_bindings"] = [
            {
                "node_id": str(item.get("node_id") or item.get("nodeId") or "").strip(),
                "label": str(item.get("label") or "").strip(),
                "target_item_ids": list(
                    item.get("target_item_ids") or item.get("targetItemIds") or []
                ),
            }
            for item in bindings[:20]
            if isinstance(item, dict)
        ]
    return result


def _limited_json(value: Any, max_chars: int) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _limit_model_context(serialized, max_chars)


def build_recipe_compiler_task(
    *,
    recipe: dict[str, Any],
    node_kind: RecipeNodeKind,
    node_prompt: str,
    user_goal: str = "",
    upstream_text: str = "",
    reference_media: list[dict[str, str]] | None = None,
    confirmed_inputs: dict[str, Any] | None = None,
    creative_settings: dict[str, Any] | None = None,
    skill_constraints: dict[str, Any] | None = None,
    skill_id: str = "",
    skill_version: str = "",
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
            "Trusted Skill identity:\n"
            + _limited_json(
                {"id": str(skill_id or "").strip(), "version": str(skill_version or "").strip()},
                512,
            ),
            "User goal:\n" + (goal or "(not provided)"),
            "Confirmed workflow inputs:\n"
            + _limited_json(confirmed_inputs or {}, _MAX_CONFIRMED_INPUTS_CHARS),
            "Trusted Skill constraints:\n"
            + _limited_json(skill_constraints or {}, _MAX_SKILL_CONSTRAINTS_CHARS),
            "Confirmed creative settings:\n"
            + _limited_json(_creative_context(creative_settings), _MAX_SKILL_CONSTRAINTS_CHARS),
            "Current node intent:\n" + (prompt or "(not provided)"),
            "Trusted Recipe instructions:\n" + system_prompt,
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
    recipe_pipeline: list[str | dict[str, Any]] | None = None,
    node_kind: RecipeNodeKind,
    node_prompt: str,
    user_goal: str = "",
    upstream_text: str = "",
    reference_media: list[dict[str, str]] | None = None,
    prompt_strategy: RecipePromptStrategy = "llm_refine",
    skill_id: str = "",
    skill_version: str = "",
    confirmed_inputs: dict[str, Any] | None = None,
    creative_settings: dict[str, Any] | None = None,
) -> str:
    """Compile an effective user Recipe into a prompt for one node execution."""
    creative_settings = resolve_creative_settings(
        username=username,
        creative_settings=creative_settings,
    )
    if prompt_strategy not in {"template", "user_message", "previous_output", "llm_refine"}:
        raise RecipeRuntimeError(f"unsupported prompt strategy: {prompt_strategy}")
    recipe = get_recipe_for_runtime(
        username=username,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
    )
    _validate_recipe_kind(recipe, node_kind)
    recipes = get_recipe_pipeline_for_runtime(
        username=username,
        primary_recipe=recipe,
        recipe_pipeline=recipe_pipeline,
        node_kind=node_kind,
    )
    skill = get_skill_for_runtime(
        username=username,
        skill_id=skill_id,
        skill_version=skill_version,
        recipe_id=str(recipe.get("id") or recipe_id),
        creative_settings=creative_settings,
    )
    for supplemental_recipe in recipes[1:]:
        get_skill_for_runtime(
            username=username,
            skill_id=skill_id,
            skill_version=skill_version,
            recipe_id=str(supplemental_recipe.get("id") or ""),
            creative_settings=creative_settings,
        )
    if prompt_strategy != "llm_refine":
        return compose_deterministic_prompt(
            prompt_strategy=prompt_strategy,
            node_prompt=node_prompt,
            user_goal=user_goal,
            upstream_text=upstream_text,
        )
    effective_recipe = _combined_recipe(recipes)
    task = build_recipe_compiler_task(
        recipe=effective_recipe,
        node_kind=node_kind,
        node_prompt=node_prompt,
        user_goal=user_goal,
        upstream_text=upstream_text,
        reference_media=reference_media,
        confirmed_inputs=confirmed_inputs,
        creative_settings=creative_settings,
        skill_constraints=_skill_constraints(skill),
        skill_id=str(skill.get("id") or "") if skill else "",
        skill_version=str(skill.get("version") or "") if skill else "",
    )
    cache_key = _cache_key(recipe=effective_recipe, task=task, node_kind=node_kind)
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
    username = str(compile_args.get("username") or "")
    creative_settings = resolve_creative_settings(
        username=username,
        creative_settings=compile_args.get("creative_settings"),
    )
    recipe = get_recipe_for_runtime(
        username=username,
        recipe_id=str(compile_args.get("recipe_id") or ""),
        recipe_version=str(compile_args.get("recipe_version") or ""),
    )
    _validate_recipe_kind(recipe, "text")
    recipes = get_recipe_pipeline_for_runtime(
        username=username,
        primary_recipe=recipe,
        recipe_pipeline=compile_args.get("recipe_pipeline"),
        node_kind="text",
    )
    skill = get_skill_for_runtime(
        username=username,
        skill_id=str(compile_args.get("skill_id") or ""),
        skill_version=str(compile_args.get("skill_version") or ""),
        recipe_id=str(recipe.get("id") or compile_args.get("recipe_id") or ""),
        creative_settings=creative_settings,
    )
    for supplemental_recipe in recipes[1:]:
        get_skill_for_runtime(
            username=username,
            skill_id=str(compile_args.get("skill_id") or ""),
            skill_version=str(compile_args.get("skill_version") or ""),
            recipe_id=str(supplemental_recipe.get("id") or ""),
            creative_settings=creative_settings,
        )
    task = build_recipe_compiler_task(
        recipe=_combined_recipe(recipes),
        node_kind="text",
        node_prompt=str(compile_args.get("node_prompt") or ""),
        user_goal=str(compile_args.get("user_goal") or ""),
        upstream_text=str(compile_args.get("upstream_text") or ""),
        reference_media=compile_args.get("reference_media"),
        confirmed_inputs=compile_args.get("confirmed_inputs"),
        creative_settings=creative_settings,
        skill_constraints=_skill_constraints(skill),
        skill_id=str(skill.get("id") or "") if skill else "",
        skill_version=str(skill.get("version") or "") if skill else "",
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
