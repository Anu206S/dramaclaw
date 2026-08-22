"""Project-level asset builds for structured_v2 projects.

Each build reads the imported source text and publishes to SQLite.  None of them
touch Cognee, an embedding model or the graph.

The three builds differ in how much they can usefully do up front:

* **Characters** are worth discovering across the whole work, for both formats.
* **Scenes** are worth discovering up front only for screenplays, where scene
  headings already name every location.  Narrated projects have no comparable
  marker, so their scenes accumulate per episode instead.
* **Props** are never worth a full-text sweep.  What matters is which objects
  carry story weight in a given episode, which is a per-episode judgement.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from novelvideo.novel_source import require_imported_novel
from novelvideo.project_config import load_project_config_file_from_state_dir
from novelvideo.story_analysis import SourceChunk, chunk_source_text

PROP_BUILD_DEFERRED_MESSAGE = "道具将在分集规划时按需生成"
SCENE_BUILD_DEFERRED_MESSAGE = "解说剧场景将在分集规划时按需生成"


def spine_template_for(store: Any) -> str:
    config = load_project_config_file_from_state_dir(store.state_dir)
    return str(config.get("spine_template") or "drama").strip()


async def build_characters_structured(
    store: Any,
    *,
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Discover characters from the source text and publish them atomically.

    Only missing characters are added.  An existing character may already carry
    user edits, a portrait, identities and voice bindings, so a rebuild must
    never overwrite one.
    """
    from novelvideo.cognee.pipeline import NovelCharacter
    from novelvideo.structured_extraction import (
        ChunkCharacterOutput,
        extract_characters_from_chunks,
    )

    def report(progress: float, task: str) -> None:
        if on_progress:
            on_progress(progress, task)

    def log(message: str) -> None:
        if on_log:
            on_log(message)

    novel_text = require_imported_novel(store.project_dir)
    template = spine_template_for(store)

    report(0.1, "切分原文...")
    chunks = chunk_source_text(novel_text, template)
    if not chunks:
        log("⚠️ 原文切分结果为空")
        report(1.0, "无可分析内容")
        return []
    log(f"确定性切分: {len(chunks)} 个片段（{chunks[0].section_type}）")

    run = await _current_run(store, novel_text, template)
    run_id = run["run_id"] if run else ""

    # Resume: a retried task or a second click on "build characters" must not
    # pay for every chunk again. Chunks already recorded as done are replayed
    # from their stored result instead of being sent to the model.
    cached: list[tuple[SourceChunk, ChunkCharacterOutput]] = []
    pending = chunks
    if run_id:
        done = {
            row["chunk_id"]: row
            for row in await store.list_analysis_chunks(run_id, status="done")
        }
        by_id = {chunk.chunk_id: chunk for chunk in chunks}
        for chunk_id, row in done.items():
            chunk = by_id.get(chunk_id)
            # A stored result only applies if the span it was produced from is
            # byte-identical; otherwise the text moved and it must be redone.
            if chunk is None or row["source_hash"] != chunk.source_hash:
                continue
            try:
                cached.append(
                    (chunk, ChunkCharacterOutput.model_validate_json(row["result_json"]))
                )
            except Exception:
                continue
        replayed = {chunk.chunk_id for chunk, _ in cached}
        pending = [chunk for chunk in chunks if chunk.chunk_id not in replayed]
        if cached:
            log(f"复用 {len(cached)} 个已完成片段，仅重算 {len(pending)} 个")

    async def persist_done(chunk: SourceChunk, output: ChunkCharacterOutput) -> None:
        if run_id:
            await store.mark_analysis_chunk_done(
                run_id, chunk.chunk_id, output.model_dump_json()
            )

    async def persist_failed(chunk: SourceChunk, exc: BaseException) -> None:
        if run_id:
            await store.mark_analysis_chunk_failed(run_id, chunk.chunk_id, str(exc))

    report(0.2, "逐片段抽取角色...")
    merged, failures = await extract_characters_from_chunks(
        pending,
        on_log=log,
        cached_outcomes=cached,
        on_chunk_done=persist_done,
        on_chunk_failed=persist_failed,
    )
    if run_id:
        # A run with failed chunks is "partial", not "completed": the next build
        # must know there is work left rather than treating this as finished.
        await store.finish_analysis_run(
            run_id,
            status="partial" if failures else "completed",
            error=f"{len(failures)} chunks failed" if failures else "",
        )
    if not merged:
        log("⚠️ 未抽取到有原文证据的角色，保留现有角色数据")
        report(1.0, "提取无结果")
        return []
    log(f"归一后得到 {len(merged)} 个角色候选")

    report(0.8, "发布角色...")
    candidates = [
        NovelCharacter(
            name=item.name,
            aliases=sorted(item.aliases),
            gender=item.gender,
            description=item.description,
        )
        for item in merged
    ]
    added = await store.add_characters_atomic(candidates, skip_existing=True)
    log(f"已新增 {len(added)} 个角色，跳过已有 {len(candidates) - len(added)} 个")

    report(0.95, "记录角色证据...")
    if run_id:
        by_name = {item.name: item for item in merged}
        for name in added:
            item = by_name.get(name)
            if item:
                await store.replace_entity_evidence(
                    run_id, "character", name, item.evidence
                )

    report(1.0, "角色提取完成")
    return added


async def build_scenes_structured(
    store: Any,
    *,
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> dict:
    """Build base scenes from screenplay headings; defer for narrated projects.

    A screenplay names every location in its scene headings, so a full-text pass
    produces a genuinely reusable catalogue.  Narrated source has no equivalent
    marker: a full-text sweep would guess at locations, so those scenes are
    discovered per episode from that episode's own text instead.
    """
    from novelvideo.cognee.pipeline import extract_scenes_from_script

    def report(progress: float, task: str) -> None:
        if on_progress:
            on_progress(progress, task)

    def log(message: str) -> None:
        if on_log:
            on_log(message)

    novel_text = require_imported_novel(store.project_dir)
    template = spine_template_for(store)

    if template != "drama":
        log(SCENE_BUILD_DEFERRED_MESSAGE)
        report(1.0, "无需提前构建场景")
        return {
            "scenes": 0,
            "added_scenes": 0,
            "mode": "episode_on_demand",
            "message": SCENE_BUILD_DEFERRED_MESSAGE,
        }

    report(0.1, "从场次头提取基础场景...")
    scenes = await extract_scenes_from_script(
        novel_text,
        on_progress=lambda progress, task: report(0.1 + progress * 0.7, task),
        on_log=on_log,
    )
    if not scenes:
        log("⚠️ 未从场次头提取到场景，保留现有场景数据")
        report(1.0, "提取无结果")
        return {"scenes": 0, "added_scenes": 0, "mode": "script"}

    report(0.85, "保存新增场景...")
    added = 0
    skipped = 0
    for scene in scenes:
        # Existing base scenes and their derived plates are asset facts; a
        # rebuild adds what is missing and leaves the rest alone.
        if await store.get_scene(scene.name):
            skipped += 1
            continue
        await store.add_scene(scene)
        added += 1
    log(f"已新增 {added} 个场景，跳过已有 {skipped} 个")

    report(1.0, "场景提取完成")
    return {"scenes": len(scenes), "added_scenes": added, "mode": "script"}


async def build_props_structured(
    store: Any,
    *,
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> dict:
    """Report that props are discovered per episode, not swept up front.

    A full-text prop sweep cannot tell a story-bearing object from background
    furniture, because that distinction depends on what an episode does with it.
    This returns an explicit deferral rather than a silent no-op, so callers do
    not read "0 props" as "the analysis found nothing".
    """
    if on_log:
        on_log(PROP_BUILD_DEFERRED_MESSAGE)
    if on_progress:
        on_progress(1.0, "道具按分集生成")
    return {
        "props": 0,
        "mode": "episode_on_demand",
        "message": PROP_BUILD_DEFERRED_MESSAGE,
    }


async def _current_run(store: Any, novel_text: str, spine_template: str) -> dict | None:
    """Find the analysis run recorded for the text now on disk.

    The spine template is part of the key: the same novel chunked as a
    screenplay and as narrated prose produces different chunk plans, so one
    must never inherit the other's results.
    """
    from novelvideo.story_analysis import source_sha256
    from novelvideo.structured_ingest import (
        STRUCTURED_PIPELINE_VERSION,
        STRUCTURED_SCHEMA_VERSION,
    )

    return await store.get_reusable_analysis_run(
        source_sha256=source_sha256(novel_text),
        schema_version=STRUCTURED_SCHEMA_VERSION,
        pipeline_version=STRUCTURED_PIPELINE_VERSION,
        spine_template=spine_template,
    )
