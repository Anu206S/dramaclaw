"""structured_v1 project-level builds: characters, scenes, props.

The rules under test are the conservative ones. A character name is at once a
SQLite primary key, a REST identifier and an asset directory name, so the
merging rules must refuse to guess, and evidence must be verifiable against the
source or the candidate never reaches the table.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from novelvideo.knowledge_pipeline import KNOWLEDGE_PIPELINE_KEY, KNOWLEDGE_PIPELINE_STRUCTURED
from novelvideo.story_analysis import SourceChunk, chunk_source_text
from novelvideo.structured_extraction import (
    CharacterCandidate,
    CharacterEvidence,
    ChunkCharacterOutput,
    extract_characters_from_chunks,
    find_explicit_aliases,
    is_generic_address,
    merge_character_candidates,
    normalize_character_name,
    verify_evidence,
)

NARRATED_TEXT = """第一章 归来

林默回到阔别十年的故乡。街道还是老样子。
他的母亲在门口等他。

第二章 旧友

林默又名小默，村里人都这么叫他。
他在巷口遇见了苏晴。

第三章 真相

苏晴告诉林默一个秘密。
他的母亲听完沉默了很久。
"""


def _padded(body: str) -> str:
    """Pad a chapter past the packing target so it stays its own chunk."""
    return body + "\n" + "闲笔叙述。" * 640 + "\n"


NARRATED_MULTI = (
    "第一章 归来\n\n" + _padded("林默回到阔别十年的故乡。他的母亲在门口等他。")
    + "\n第二章 旧友\n\n" + _padded("林默又名小默，村里人都这么叫他。他在巷口遇见了苏晴。")
    + "\n第三章 真相\n\n" + _padded("苏晴告诉林默一个秘密。他的母亲听完沉默了很久。")
)


def _chunk(text: str, *, chunk_id="c0", start=0) -> SourceChunk:
    return SourceChunk(
        chunk_id=chunk_id,
        chunk_index=0,
        section_type="chapter",
        section_label="第一章",
        source_start=start,
        source_end=start + len(text),
        text=text,
    )


def _candidate(name, *, quotes=(), aliases=(), gender="", description=""):
    return CharacterCandidate(
        name=name,
        aliases=list(aliases),
        gender=gender,
        description=description,
        evidence=[CharacterEvidence(quote=quote) for quote in quotes],
    )


# ── name normalization ──────────────────────────────────────────────────────


def test_normalize_strips_punctuation_noise_without_altering_the_name():
    assert normalize_character_name("　林默：") == "林默"
    assert normalize_character_name("「苏晴」") == "苏晴"
    assert normalize_character_name("林 默") == "林 默"


def test_titles_and_kinship_terms_are_generic():
    for term in ("母亲", "陛下", "医生", "他", "少年"):
        assert is_generic_address(term)
    assert not is_generic_address("林默")


# ── evidence verification ───────────────────────────────────────────────────


def test_evidence_resolves_to_absolute_source_offsets():
    chunk = _chunk("林默回到故乡。", start=100)
    span = verify_evidence("林默回到故乡。", chunk)
    assert span == (100, 100 + len("林默回到故乡。"))


def test_evidence_not_present_in_the_chunk_is_rejected():
    """This check is what stops an invented character reaching the table."""
    chunk = _chunk("林默回到故乡。")
    assert verify_evidence("林默其实是皇帝的私生子。", chunk) is None


def test_evidence_tolerates_whitespace_the_model_normalized():
    chunk = _chunk("林默  回到   故乡。")
    assert verify_evidence("林默 回到 故乡。", chunk) is not None


def test_empty_quote_is_rejected():
    assert verify_evidence("   ", _chunk("林默回到故乡。")) is None


# ── explicit alias detection ────────────────────────────────────────────────


def test_explicit_alias_statements_are_detected():
    assert ("林默", "小默") in find_explicit_aliases("林默又名小默，村里人都这么叫他。")
    assert ("萧玦", "陛下") in find_explicit_aliases("萧玦人称陛下。")


def test_two_names_merely_appearing_together_is_not_an_alias():
    """Co-occurrence is not identity — that is how wrong merges happen."""
    assert find_explicit_aliases("林默看着苏晴，两人都没说话。") == set()


# ── merging ─────────────────────────────────────────────────────────────────


def test_identical_names_across_chunks_merge():
    text_a = "林默回到故乡。"
    text_b = "林默走进屋子。"
    outcomes = [
        (
            _chunk(text_a, chunk_id="c0"),
            ChunkCharacterOutput(characters=[_candidate("林默", quotes=[text_a])]),
        ),
        (
            _chunk(text_b, chunk_id="c1", start=50),
            ChunkCharacterOutput(characters=[_candidate("林默", quotes=[text_b])]),
        ),
    ]
    merged = merge_character_candidates(outcomes)
    assert [item.name for item in merged] == ["林默"]
    assert len(merged[0].evidence) == 2
    assert merged[0].chunk_ids == {"c0", "c1"}


def test_candidates_without_verifiable_evidence_are_dropped():
    text = "林默回到故乡。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(
                characters=[
                    _candidate("林默", quotes=[text]),
                    _candidate("皇帝", quotes=["林默是皇帝的儿子。"]),
                ]
            ),
        )
    ]
    merged = merge_character_candidates(outcomes)
    assert [item.name for item in merged] == ["林默"]


def test_generic_address_terms_never_become_characters():
    text = "他的母亲在门口等他。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(characters=[_candidate("母亲", quotes=[text])]),
        )
    ]
    assert merge_character_candidates(outcomes) == []


def test_explicitly_stated_alias_merges_into_one_character():
    text = "林默又名小默，村里人都这么叫他。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(
                characters=[
                    _candidate("林默", quotes=[text]),
                    _candidate("小默", quotes=[text]),
                ]
            ),
        )
    ]
    merged = merge_character_candidates(outcomes)
    assert len(merged) == 1
    assert merged[0].name == "林默"
    assert "小默" in merged[0].aliases


def test_model_proposed_alias_without_textual_support_stays_a_suggestion():
    """A wrong merge destroys data silently; a wrong split is a visible duplicate."""
    text = "林默看着苏晴。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=[text], aliases=["苏晴"])]
            ),
        )
    ]
    merged = merge_character_candidates(outcomes)
    assert merged[0].aliases == set()
    assert "苏晴" in merged[0].ambiguous_with


def test_same_generic_term_in_two_chunks_does_not_merge_into_one_person():
    """"母亲" in chapter one and chapter three need not be the same woman."""
    outcomes = [
        (
            _chunk("他的母亲在门口等他。", chunk_id="c0"),
            ChunkCharacterOutput(
                characters=[_candidate("母亲", quotes=["他的母亲在门口等他。"])]
            ),
        ),
        (
            _chunk("他的母亲听完沉默了。", chunk_id="c1", start=80),
            ChunkCharacterOutput(
                characters=[_candidate("母亲", quotes=["他的母亲听完沉默了。"])]
            ),
        ),
    ]
    assert merge_character_candidates(outcomes) == []


def test_alias_merge_keeps_the_better_evidenced_name_as_primary():
    alias_text = "林默又名小默。"
    outcomes = [
        (
            _chunk(alias_text, chunk_id="c0"),
            ChunkCharacterOutput(
                characters=[
                    _candidate("小默", quotes=[alias_text]),
                    _candidate("林默", quotes=[alias_text]),
                ]
            ),
        ),
        (
            _chunk("林默走进屋子。", chunk_id="c1", start=60),
            ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默走进屋子。"])]
            ),
        ),
    ]
    merged = merge_character_candidates(outcomes)
    assert len(merged) == 1
    assert merged[0].name == "林默"
    assert merged[0].aliases == {"小默"}


# ── extraction over chunks ──────────────────────────────────────────────────


class FakeAgent:
    """Returns a scripted output per chunk label, or raises for one of them."""

    def __init__(self, by_label, fail_labels=()):
        self.by_label = by_label
        self.fail_labels = set(fail_labels)
        self.seen = []

    async def run(self, prompt: str):
        label = next(
            (key for key in list(self.by_label) + list(self.fail_labels) if key in prompt),
            "",
        )
        self.seen.append(label)
        if label in self.fail_labels:
            raise RuntimeError("boom")
        return SimpleNamespace(
            output=self.by_label.get(label, ChunkCharacterOutput())
        )


async def test_extraction_runs_over_every_chunk():
    chunks = chunk_source_text(NARRATED_MULTI, "narrated")
    agent = FakeAgent(
        {
            "第一章": ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
            ),
            "第二章": ChunkCharacterOutput(
                characters=[_candidate("苏晴", quotes=["他在巷口遇见了苏晴。"])]
            ),
        }
    )
    merged, _ = await extract_characters_from_chunks(chunks, agent=agent, adjudicate=False)
    assert {item.name for item in merged} == {"林默", "苏晴"}


async def test_one_failing_chunk_does_not_discard_the_others():
    """A single unparseable scene must not take the whole build down with it."""
    chunks = chunk_source_text(NARRATED_MULTI, "narrated")
    agent = FakeAgent(
        {
            "第一章": ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
            )
        },
        fail_labels=["第二章"],
    )
    logs: list[str] = []
    merged, failures = await extract_characters_from_chunks(
        chunks, agent=agent, on_log=logs.append, adjudicate=False
    )
    assert [item.name for item in merged] == ["林默"]
    assert any("失败" in line for line in logs)
    # The failure is reported back so the caller can persist it against the run.
    assert [chunk.section_label for chunk, _ in failures]


async def test_extraction_is_bounded_but_not_serial():
    """Chunks are independent, so they must not run one at a time."""
    import asyncio

    in_flight = 0
    peak = 0

    class SlowAgent:
        async def run(self, prompt: str):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return SimpleNamespace(output=ChunkCharacterOutput())

    chunks = [
        _chunk(f"片段{index}", chunk_id=f"c{index}", start=index * 10)
        for index in range(12)
    ]
    await extract_characters_from_chunks(
        chunks, agent=SlowAgent(), concurrency=4, adjudicate=False
    )
    assert peak > 1
    assert peak <= 4


# ── builders ────────────────────────────────────────────────────────────────


@pytest.fixture
async def structured_store(tmp_path):
    from novelvideo.sqlite_store import SQLiteStore

    state_dir = tmp_path / "user" / "structured"
    state_dir.mkdir(parents=True)
    (state_dir / "project_config.json").write_text(
        json.dumps({KNOWLEDGE_PIPELINE_KEY: KNOWLEDGE_PIPELINE_STRUCTURED, "spine_template": "narrated"}),
        encoding="utf-8",
    )
    (state_dir / "novel.txt").write_text(NARRATED_MULTI, encoding="utf-8")
    store = SQLiteStore(
        "user/structured", output_dir=str(state_dir), state_dir=str(state_dir)
    )
    await store.initialize()
    await store.load_graph_state()
    try:
        yield store, state_dir
    finally:
        await store.close()


async def test_atomic_publish_leaves_nothing_behind_on_failure(structured_store):
    """add_character commits per row; a build must publish all or nothing."""
    from novelvideo.cognee.pipeline import NovelCharacter

    store, _ = structured_store
    db = await store._ensure_db()
    original_execute = db.execute
    calls = {"n": 0}

    async def fail_on_second_insert(sql, *args, **kwargs):
        if sql.strip().startswith("INSERT INTO characters"):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
        return await original_execute(sql, *args, **kwargs)

    db.execute = fail_on_second_insert
    try:
        with pytest.raises(RuntimeError):
            await store.add_characters_atomic(
                [NovelCharacter(name="林默"), NovelCharacter(name="苏晴")]
            )
    finally:
        db.execute = original_execute

    # The first insert must not survive the second one's failure.
    assert await store.list_characters() == []


async def test_atomic_publish_never_overwrites_an_existing_character(structured_store):
    """An existing character may already carry portraits, identities and voice."""
    from novelvideo.cognee.pipeline import NovelCharacter

    store, _ = structured_store
    await store.add_character(
        NovelCharacter(name="林默", description="用户编辑过的描述", face_prompt="portrait")
    )

    added = await store.add_characters_atomic(
        [NovelCharacter(name="林默", description="重扫生成的描述"), NovelCharacter(name="苏晴")]
    )

    assert added == ["苏晴"]
    assert store.get_character("林默").description == "用户编辑过的描述"
    assert store.get_character("林默").face_prompt == "portrait"


async def test_narrated_scene_build_defers_instead_of_guessing(structured_store):
    """Narrated source has no scene headings; a full sweep would invent places."""
    from novelvideo.structured_builders import build_scenes_structured

    store, _ = structured_store
    result = await build_scenes_structured(store)
    assert result["mode"] == "episode_on_demand"
    assert result["added_scenes"] == 0
    assert await store.list_scenes() == []


async def test_prop_build_reports_deferral_rather_than_a_silent_zero(structured_store):
    """"0 props" must not read as "the analysis found nothing"."""
    from novelvideo.structured_builders import build_props_structured

    store, _ = structured_store
    result = await build_props_structured(store)
    assert result["props"] == 0
    assert result["mode"] == "episode_on_demand"
    assert result["message"]


async def test_character_build_publishes_and_records_evidence(
    structured_store, monkeypatch
):
    from novelvideo import structured_builders
    from novelvideo.structured_ingest import ingest_source_text_structured

    store, state_dir = structured_store
    source = state_dir / "source.txt"
    source.write_text(NARRATED_MULTI, encoding="utf-8")
    run = await ingest_source_text_structured(
        store, str(source), spine_template="narrated"
    )

    agent = FakeAgent(
        {
            "第一章": ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
            )
        }
    )

    real_extract = extract_characters_from_chunks

    async def fake_extract(chunks, **kwargs):
        kwargs.pop("agent", None)
        kwargs.setdefault("adjudicate", False)
        return await real_extract(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks",
        fake_extract,
    )

    added = await structured_builders.build_characters_structured(store)
    assert added == ["林默"]

    evidence = await store.list_entity_evidence("character", "林默")
    assert evidence
    assert evidence[0]["run_id"] == run["run_id"]
    quoted = NARRATED_MULTI[
        evidence[0]["source_start"] : evidence[0]["source_end"]
    ]
    assert quoted == "林默回到阔别十年的故乡。"


async def test_character_build_never_touches_cognee(structured_store, monkeypatch):
    import cognee

    from novelvideo import structured_builders

    def _boom(*args, **kwargs):
        raise AssertionError("structured character build must not touch Cognee")

    for name in ("add", "cognify", "memify", "search"):
        monkeypatch.setattr(cognee, name, _boom, raising=False)

    store, _ = structured_store
    agent = FakeAgent({})

    real_extract = extract_characters_from_chunks

    async def fake_extract(chunks, **kwargs):
        kwargs.pop("agent", None)
        kwargs.setdefault("adjudicate", False)
        return await real_extract(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks",
        fake_extract,
    )
    await structured_builders.build_characters_structured(store)


# ── resume, chunk bounds and concurrency defaults ───────────────────────────


async def test_completed_chunks_are_replayed_instead_of_re_billed(
    structured_store, monkeypatch
):
    """A retry or a second click must not pay for every chunk again."""
    from novelvideo import structured_builders
    from novelvideo.structured_extraction import extract_characters_from_chunks
    from novelvideo.structured_ingest import ingest_source_text_structured

    store, state_dir = structured_store
    source = state_dir / "source.txt"
    source.write_text(NARRATED_MULTI, encoding="utf-8")
    await ingest_source_text_structured(store, str(source), spine_template="narrated")

    outputs = {
        "第一章": ChunkCharacterOutput(
            characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
        ),
        "第二章": ChunkCharacterOutput(
            characters=[_candidate("苏晴", quotes=["他在巷口遇见了苏晴。"])]
        ),
    }
    agent = FakeAgent(outputs)
    real_extract = extract_characters_from_chunks

    async def fake_extract(chunks, **kwargs):
        kwargs.pop("agent", None)
        kwargs.setdefault("adjudicate", False)
        return await real_extract(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks", fake_extract
    )

    first = await structured_builders.build_characters_structured(store)
    assert set(first) == {"林默", "苏晴"}
    first_calls = len(agent.seen)
    assert first_calls > 0

    agent.seen.clear()
    second = await structured_builders.build_characters_structured(store)

    # Everything was replayed from stored results, so no chunk went to the model.
    assert agent.seen == []
    # And the characters are unchanged: they already exist, so nothing is added.
    assert second == []


async def test_a_failed_chunk_leaves_the_run_partial(structured_store, monkeypatch):
    """A partial run must not look finished to the next build."""
    from novelvideo import structured_builders
    from novelvideo.structured_extraction import extract_characters_from_chunks
    from novelvideo.structured_ingest import ingest_source_text_structured

    store, state_dir = structured_store
    source = state_dir / "source.txt"
    source.write_text(NARRATED_MULTI, encoding="utf-8")
    run = await ingest_source_text_structured(
        store, str(source), spine_template="narrated"
    )

    agent = FakeAgent(
        {
            "第一章": ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
            )
        },
        fail_labels=["第二章"],
    )
    real_extract = extract_characters_from_chunks

    async def fake_extract(chunks, **kwargs):
        kwargs.pop("agent", None)
        kwargs.setdefault("adjudicate", False)
        return await real_extract(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks", fake_extract
    )
    await structured_builders.build_characters_structured(store)

    failed = await store.list_analysis_chunks(run["run_id"], status="failed")
    assert failed, "the failing chunk was not recorded"
    from novelvideo.story_analysis import source_sha256
    from novelvideo.structured_ingest import (
        STRUCTURED_PIPELINE_VERSION,
        STRUCTURED_SCHEMA_VERSION,
    )

    stored = await store.get_reusable_analysis_run(
        source_sha256=source_sha256(NARRATED_MULTI),
        schema_version=STRUCTURED_SCHEMA_VERSION,
        pipeline_version=STRUCTURED_PIPELINE_VERSION,
        spine_template="narrated",
    )
    assert stored["status"] == "partial"


def test_an_oversized_chapter_is_split_further():
    """A chapter boundary says where to cut, not how big the piece may be."""
    text = "第一章 归来\n\n" + "林默回到故乡。" * 3000 + "\n\n第二章 旧友\n\n短章节。\n"
    chunks = chunk_source_text(text, "narrated")

    assert len(chunks) > 2
    assert max(len(chunk.text) for chunk in chunks) <= 6000
    for chunk in chunks:
        assert text[chunk.source_start : chunk.source_end] == chunk.text
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_oversized_parts_keep_a_recognisable_section_label():
    text = "第一章 归来\n\n" + "林默回到故乡。" * 3000
    chunks = chunk_source_text(text, "narrated")
    assert all(chunk.chunk_id.startswith("chapter-0000-p") for chunk in chunks)
    assert all("第1章" in chunk.section_label for chunk in chunks)


def test_short_chapters_are_packed_into_one_call():
    """A call costs the same round trip whether it carries 300 or 3000 chars."""
    chunks = chunk_source_text(NARRATED_TEXT, "narrated")
    assert len(chunks) == 1
    assert chunks[0].source_start == 0
    assert chunks[0].text == NARRATED_TEXT


def test_chapters_past_the_target_stay_separate():
    chunks = chunk_source_text(NARRATED_MULTI, "narrated")
    assert len(chunks) == 3
    for chunk in chunks:
        assert NARRATED_MULTI[chunk.source_start : chunk.source_end] == chunk.text


def test_llm_concurrency_defaults_to_the_project_baseline(monkeypatch):
    """A second pool running deeper than COGNEE_LLM_CONCURRENCY would trip the
    same gateway limits that setting exists to avoid."""
    from novelvideo.utils.bounded_concurrency import default_llm_concurrency

    monkeypatch.delenv("STRUCTURED_LLM_CONCURRENCY", raising=False)
    assert default_llm_concurrency() == 2

    monkeypatch.setenv("STRUCTURED_LLM_CONCURRENCY", "5")
    assert default_llm_concurrency() == 5

    monkeypatch.setenv("STRUCTURED_LLM_CONCURRENCY", "0")
    with pytest.raises(ValueError):
        default_llm_concurrency()


async def test_reuse_key_separates_drama_from_narrated(structured_store, tmp_path):
    """The same text chunked two ways must not share a chunk plan."""
    from novelvideo.structured_ingest import ingest_source_text_structured

    store, state_dir = structured_store
    source = state_dir / "source.txt"
    source.write_text(NARRATED_MULTI, encoding="utf-8")

    narrated = await ingest_source_text_structured(
        store, str(source), spine_template="narrated"
    )
    again = await ingest_source_text_structured(
        store, str(source), spine_template="narrated"
    )
    assert again["run_id"] == narrated["run_id"]

    # Same bytes, different spine: a fresh plan, not the chapter-based one.
    drama = await ingest_source_text_structured(
        store, str(source), spine_template=""
    )
    assert drama["run_id"] != narrated["run_id"]


async def test_evidence_is_backfilled_when_the_characters_already_exist(
    structured_store, monkeypatch
):
    """Publishing characters and writing evidence are two steps.

    If the first succeeds and the second fails, a retry finds the characters
    already present. Keying evidence on "newly added" would leave them without
    provenance forever.
    """
    from novelvideo import structured_builders
    from novelvideo.cognee.pipeline import NovelCharacter
    from novelvideo.structured_extraction import extract_characters_from_chunks
    from novelvideo.structured_ingest import ingest_source_text_structured

    store, state_dir = structured_store
    source = state_dir / "source.txt"
    source.write_text(NARRATED_MULTI, encoding="utf-8")
    await ingest_source_text_structured(store, str(source), spine_template="narrated")

    # Stand in for a previous build that published the character but died
    # before its evidence landed.
    await store.add_character(NovelCharacter(name="林默"))
    assert await store.list_entity_evidence("character", "林默") == []

    agent = FakeAgent(
        {
            "第一章": ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
            )
        }
    )
    real_extract = extract_characters_from_chunks

    async def fake_extract(chunks, **kwargs):
        kwargs.pop("agent", None)
        kwargs.setdefault("adjudicate", False)
        return await real_extract(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks", fake_extract
    )

    added = await structured_builders.build_characters_structured(store)
    assert added == []  # nothing new to publish
    assert await store.list_entity_evidence("character", "林默"), (
        "evidence was never backfilled for an already-published character"
    )


async def test_a_run_with_no_characters_is_still_closed_out(
    structured_store, monkeypatch
):
    """A run left at "pending" tells the next build nothing about what remains."""
    from novelvideo import structured_builders
    from novelvideo.story_analysis import source_sha256
    from novelvideo.structured_extraction import extract_characters_from_chunks
    from novelvideo.structured_ingest import (
        STRUCTURED_PIPELINE_VERSION,
        STRUCTURED_SCHEMA_VERSION,
        ingest_source_text_structured,
    )

    store, state_dir = structured_store
    source = state_dir / "source.txt"
    source.write_text(NARRATED_MULTI, encoding="utf-8")
    await ingest_source_text_structured(store, str(source), spine_template="narrated")

    agent = FakeAgent({})  # every chunk yields nothing
    real_extract = extract_characters_from_chunks

    async def fake_extract(chunks, **kwargs):
        kwargs.pop("agent", None)
        kwargs.setdefault("adjudicate", False)
        return await real_extract(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks", fake_extract
    )
    assert await structured_builders.build_characters_structured(store) == []

    stored = await store.get_reusable_analysis_run(
        source_sha256=source_sha256(NARRATED_MULTI),
        schema_version=STRUCTURED_SCHEMA_VERSION,
        pipeline_version=STRUCTURED_PIPELINE_VERSION,
        spine_template="narrated",
    )
    assert stored["status"] == "completed"


# ── ambiguity adjudication ──────────────────────────────────────────────────


def _merged(name, count, *, aliases=()):
    from novelvideo.structured_extraction import MergedCharacter

    return MergedCharacter(
        name=name,
        aliases=set(aliases),
        evidence=[
            {
                "chunk_id": "c0",
                "source_start": index,
                "source_end": index + 1,
                "evidence_kind": "mention",
                "evidence_text": name,
            }
            for index in range(count)
        ],
    )


class AdjudicatorAgent:
    """Returns a scripted adjudication and records the prompt it received."""

    def __init__(self, groups=(), non_characters=(), explode=False):
        from novelvideo.structured_extraction import (
            CharacterAdjudication,
            SamePersonGroup,
        )

        self.explode = explode
        self.prompt = ""
        self.result = CharacterAdjudication(
            groups=[
                SamePersonGroup(canonical_name=c, alias_names=list(a))
                for c, a in groups
            ],
            non_characters=list(non_characters),
        )

    async def run(self, prompt: str):
        self.prompt = prompt
        if self.explode:
            raise RuntimeError("adjudicator unavailable")
        return SimpleNamespace(output=self.result)


async def test_adjudication_merges_a_nickname_into_its_character():
    """Per-chunk extraction cannot see that 小阳 is 郑旭阳; this step can."""
    from novelvideo.structured_extraction import adjudicate_characters

    merged = [_merged("郑旭阳", 38), _merged("小阳", 1)]
    agent = AdjudicatorAgent(groups=[("郑旭阳", ["小阳"])])

    result = await adjudicate_characters(merged, agent=agent)
    assert [item.name for item in result] == ["郑旭阳"]
    assert result[0].aliases == {"小阳"}
    assert len(result[0].evidence) == 39


async def test_adjudication_cannot_invent_a_character():
    """It may only group names it was given."""
    from novelvideo.structured_extraction import adjudicate_characters

    merged = [_merged("郑旭阳", 38), _merged("小阳", 1)]
    agent = AdjudicatorAgent(groups=[("查无此人", ["小阳"])])

    result = await adjudicate_characters(merged, agent=agent)
    assert {item.name for item in result} == {"郑旭阳", "小阳"}


async def test_adjudication_cannot_delete_a_load_bearing_character():
    """One bad call must not silently drop a lead from the cast."""
    from novelvideo.structured_extraction import adjudicate_characters

    merged = [_merged("郑玉琴", 96), _merged("郑家悦", 96), _merged("路人", 1)]
    agent = AdjudicatorAgent(non_characters=["郑玉琴", "路人"])

    result = await adjudicate_characters(merged, agent=agent)
    names = {item.name for item in result}
    assert "郑玉琴" in names, "a lead was dropped on the model's say-so"
    assert "路人" not in names


async def test_adjudication_failure_keeps_the_rule_result():
    """A degraded adjudicator must not lose the characters rules already found."""
    from novelvideo.structured_extraction import adjudicate_characters

    merged = [_merged("郑玉琴", 96), _merged("郑太", 5)]
    logs: list[str] = []

    result = await adjudicate_characters(
        merged, agent=AdjudicatorAgent(explode=True), on_log=logs.append
    )
    assert {item.name for item in result} == {"郑玉琴", "郑太"}
    assert any("裁决失败" in line for line in logs)


async def test_rarely_seen_candidates_get_source_context():
    """A bare quote rarely proves identity; the surrounding text usually does."""
    from novelvideo.structured_extraction import adjudicate_characters

    source = "▲郑旭阳走进来。郑玉琴皱眉。\n郑玉琴：小阳，你又闯祸了。\n"
    start = source.index("小阳")
    rare = _merged("小阳", 0)
    rare.evidence.append(
        {
            "chunk_id": "c0",
            "source_start": start,
            "source_end": start + 2,
            "evidence_kind": "dialogue",
            "evidence_text": "小阳",
        }
    )
    agent = AdjudicatorAgent()

    await adjudicate_characters(
        [_merged("郑旭阳", 38), rare], source_text=source, agent=agent
    )
    assert "上下文" in agent.prompt
    # The formal name sits next to the nickname, which is what makes the link
    # inferable at all.
    assert "郑旭阳" in agent.prompt


async def test_a_single_candidate_needs_no_adjudication():
    from novelvideo.structured_extraction import adjudicate_characters

    merged = [_merged("郑玉琴", 96)]
    agent = AdjudicatorAgent(non_characters=["郑玉琴"])
    assert await adjudicate_characters(merged, agent=agent) == merged


# ── scene adjudication ──────────────────────────────────────────────────────


def _scene(name, *, aliases=()):
    from novelvideo.models import NovelScene

    return NovelScene(name=name, aliases=list(aliases))


class SceneAdjudicatorAgent:
    def __init__(self, groups=(), explode=False):
        from novelvideo.structured_extraction import (
            SameLocationGroup, SceneAdjudication,
        )

        self.explode = explode
        self.prompt = ""
        self.result = SceneAdjudication(
            groups=[
                SameLocationGroup(canonical_name=c, alias_names=list(a))
                for c, a in groups
            ]
        )

    async def run(self, prompt: str):
        self.prompt = prompt
        if self.explode:
            raise RuntimeError("adjudicator unavailable")
        return SimpleNamespace(output=self.result)


async def test_scene_adjudication_merges_spellings_of_one_location():
    """Hand-written headings spell one room several ways."""
    from novelvideo.structured_extraction import adjudicate_scenes

    scenes = [_scene("郑玉琴办公室"), _scene("郑玉琴办公室内")]
    agent = SceneAdjudicatorAgent(groups=[("郑玉琴办公室", ["郑玉琴办公室内"])])

    result = await adjudicate_scenes(scenes, agent=agent)
    assert [s.name for s in result] == ["郑玉琴办公室"]
    assert "郑玉琴办公室内" in result[0].aliases


async def test_scene_adjudication_never_drops_a_location():
    """A duplicate is redundant art; a missing scene leaves shots with no asset.

    Unlike characters, there is no removal path here at all, so a model that
    proposes nothing simply leaves every scene standing.
    """
    from novelvideo.structured_extraction import adjudicate_scenes

    scenes = [_scene("郑家别墅客厅"), _scene("郑家别墅餐厅"), _scene("郑家别墅外")]
    result = await adjudicate_scenes(scenes, agent=SceneAdjudicatorAgent())
    assert {s.name for s in result} == {name.name for name in scenes}


async def test_scene_adjudication_cannot_invent_a_location():
    from novelvideo.structured_extraction import adjudicate_scenes

    scenes = [_scene("郑玉琴办公室"), _scene("郑玉琴办公室内")]
    agent = SceneAdjudicatorAgent(groups=[("查无此地", ["郑玉琴办公室内"])])

    result = await adjudicate_scenes(scenes, agent=agent)
    assert len(result) == 2


async def test_scene_adjudication_failure_keeps_every_scene():
    from novelvideo.structured_extraction import adjudicate_scenes

    scenes = [_scene("郑玉琴办公室"), _scene("郑玉琴办公室内")]
    logs: list[str] = []
    result = await adjudicate_scenes(
        scenes, agent=SceneAdjudicatorAgent(explode=True), on_log=logs.append
    )
    assert len(result) == 2
    assert any("裁决失败" in line for line in logs)


async def test_scene_prompt_reports_how_often_each_heading_is_used():
    """The most-used spelling is the better canonical name."""
    from novelvideo.structured_extraction import adjudicate_scenes

    scenes = [_scene("主任办公室"), _scene("郑家别墅客厅")]
    agent = SceneAdjudicatorAgent()
    await adjudicate_scenes(
        scenes, occurrences={"主任办公室": 18, "郑家别墅客厅": 16}, agent=agent
    )
    assert "出现 18 场" in agent.prompt
    assert "出现 16 场" in agent.prompt


def test_scene_heading_counts_come_from_the_script():
    from novelvideo.structured_builders import _scene_heading_counts

    script = (
        "第一集\n\n"
        "1-1 林家客厅 日 内\n人物：林默\n林默推开门。\n\n"
        "1-2 巷口 夜 外\n人物：林默\n林默走过巷口。\n\n"
        "1-3 林家客厅 夜 内\n人物：林默\n林默坐下。\n"
    )
    counts = _scene_heading_counts(script)
    assert counts.get("林家客厅") == 2
    assert counts.get("巷口") == 1


# ── resume after an outage, and source-change invalidation ──────────────────


class FlakyAgent:
    """Fails for a set of chunk labels, then can be repaired."""

    def __init__(self, outputs, failing=()):
        self.outputs = outputs
        self.failing = set(failing)
        # Keep the label vocabulary stable across repair, so a recovered agent
        # still recognises the chunk it previously refused.
        self.labels = list(outputs) + list(failing)
        self.calls: list[str] = []

    def repair(self):
        self.failing.clear()

    async def run(self, prompt: str):
        label = next((k for k in self.labels if k in prompt), "")
        self.calls.append(label)
        if label in self.failing:
            raise RuntimeError("gateway down")
        return SimpleNamespace(
            output=self.outputs.get(label, ChunkCharacterOutput())
        )


async def _ingested(store, state_dir, text=NARRATED_MULTI):
    from novelvideo.structured_ingest import ingest_source_text_structured

    source = state_dir / "source.txt"
    source.write_text(text, encoding="utf-8")
    return await ingest_source_text_structured(
        store, str(source), spine_template="narrated"
    )


def _patched_extract(monkeypatch, agent):
    from novelvideo.structured_extraction import extract_characters_from_chunks

    real = extract_characters_from_chunks

    async def fake(chunks, **kwargs):
        kwargs.pop("agent", None)
        kwargs.setdefault("adjudicate", False)
        return await real(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks", fake
    )


async def test_a_chunk_that_failed_is_retried_while_others_are_not(
    structured_store, monkeypatch
):
    """An outage mid-build must cost only the chunks it actually broke."""
    from novelvideo import structured_builders

    store, state_dir = structured_store
    run = await _ingested(store, state_dir, NARRATED_MULTI)

    agent = FlakyAgent(
        outputs={
            "第一章": ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
            ),
            "第三章": ChunkCharacterOutput(
                characters=[_candidate("苏晴", quotes=["苏晴告诉林默一个秘密。"])]
            ),
        },
        failing=["第二章"],
    )
    _patched_extract(monkeypatch, agent)

    await structured_builders.build_characters_structured(store)
    assert len(agent.calls) == 3
    failed = await store.list_analysis_chunks(run["run_id"], status="failed")
    assert [row["chunk_id"] for row in failed] == ["chapter-0001"]

    # The gateway comes back and the user clicks build again.
    agent.repair()
    agent.calls.clear()
    await structured_builders.build_characters_structured(store)

    assert agent.calls == ["第二章"], "a healthy chunk was paid for twice"
    assert not await store.list_analysis_chunks(run["run_id"], status="failed")


async def test_editing_the_source_discards_the_stored_plan(
    structured_store, monkeypatch
):
    """A result produced from text that has since changed is not a result."""
    from novelvideo import structured_builders

    store, state_dir = structured_store
    await _ingested(store, state_dir, NARRATED_MULTI)

    outputs = {
        "第一章": ChunkCharacterOutput(
            characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
        )
    }
    agent = FlakyAgent(outputs=outputs)
    _patched_extract(monkeypatch, agent)

    await structured_builders.build_characters_structured(store)
    first_calls = len(agent.calls)
    assert first_calls > 0

    # Rewriting novel.txt without re-importing: the hash no longer matches any
    # recorded run, so nothing may be replayed.
    (Path(store.project_dir) / "novel.txt").write_text(
        NARRATED_MULTI + "\n第四章 结局\n\n他终于释怀。\n", encoding="utf-8"
    )
    agent.calls.clear()
    await structured_builders.build_characters_structured(store)

    assert agent.calls, "stale results were replayed for text that changed"


# ── appellations ────────────────────────────────────────────────────────────


def _candidate_with_appellations(name, quotes, appellations):
    c = _candidate(name, quotes=quotes)
    c.appellations = list(appellations)
    return c


def test_an_appellation_only_one_character_claims_becomes_an_alias():
    """Packed chunks hold several scenes, so nicknames surface alongside names."""
    text = "郑玉琴走进客厅。刘管家喊了一声郑太。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(
                characters=[
                    _candidate_with_appellations("郑玉琴", [text], ["郑太"]),
                    _candidate("刘管家", quotes=[text]),
                ]
            ),
        )
    ]
    merged = {m.name: m for m in merge_character_candidates(outcomes)}
    assert merged["郑玉琴"].aliases == {"郑太"}
    assert merged["刘管家"].aliases == set()


def test_an_appellation_two_characters_claim_is_dropped():
    """Two claimants means the model could not attribute it.

    A wrong alias resolves confidently to the wrong person, which is worse than
    no alias at all.
    """
    text = "郑玉琴走进客厅。刘管家喊了一声郑太。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(
                characters=[
                    _candidate_with_appellations("郑玉琴", [text], ["郑太"]),
                    _candidate_with_appellations("刘管家", [text], ["郑太"]),
                ]
            ),
        )
    ]
    for item in merge_character_candidates(outcomes):
        assert "郑太" not in item.aliases


def test_an_appellation_absent_from_the_chunk_is_rejected():
    text = "郑玉琴走进客厅。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(
                characters=[
                    _candidate_with_appellations("郑玉琴", [text], ["女王陛下"])
                ]
            ),
        )
    ]
    assert merge_character_candidates(outcomes)[0].aliases == set()


def test_a_generic_appellation_is_not_recorded_as_an_alias():
    text = "郑玉琴走进客厅。她的母亲在门口。"
    outcomes = [
        (
            _chunk(text),
            ChunkCharacterOutput(
                characters=[
                    _candidate_with_appellations("郑玉琴", [text], ["母亲"])
                ]
            ),
        )
    ]
    assert merge_character_candidates(outcomes)[0].aliases == set()
