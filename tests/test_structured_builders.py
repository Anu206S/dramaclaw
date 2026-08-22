"""structured_v2 project-level builds: characters, scenes, props.

The rules under test are the conservative ones. A character name is at once a
SQLite primary key, a REST identifier and an asset directory name, so the
merging rules must refuse to guess, and evidence must be verifiable against the
source or the candidate never reaches the table.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from novelvideo.knowledge_pipeline import KNOWLEDGE_PIPELINE_KEY, STRUCTURED_V2
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
    chunks = chunk_source_text(NARRATED_TEXT, "narrated")
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
    merged = await extract_characters_from_chunks(chunks, agent=agent)
    assert {item.name for item in merged} == {"林默", "苏晴"}


async def test_one_failing_chunk_does_not_discard_the_others():
    """A single unparseable scene must not take the whole build down with it."""
    chunks = chunk_source_text(NARRATED_TEXT, "narrated")
    agent = FakeAgent(
        {
            "第一章": ChunkCharacterOutput(
                characters=[_candidate("林默", quotes=["林默回到阔别十年的故乡。"])]
            )
        },
        fail_labels=["第二章"],
    )
    logs: list[str] = []
    merged = await extract_characters_from_chunks(
        chunks, agent=agent, on_log=logs.append
    )
    assert [item.name for item in merged] == ["林默"]
    assert any("失败" in line for line in logs)


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
    await extract_characters_from_chunks(chunks, agent=SlowAgent(), concurrency=4)
    assert peak > 1
    assert peak <= 4


# ── builders ────────────────────────────────────────────────────────────────


@pytest.fixture
async def structured_store(tmp_path):
    from novelvideo.sqlite_store import SQLiteStore

    state_dir = tmp_path / "user" / "structured"
    state_dir.mkdir(parents=True)
    (state_dir / "project_config.json").write_text(
        json.dumps({KNOWLEDGE_PIPELINE_KEY: STRUCTURED_V2, "spine_template": "narrated"}),
        encoding="utf-8",
    )
    (state_dir / "novel.txt").write_text(NARRATED_TEXT, encoding="utf-8")
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
    source.write_text(NARRATED_TEXT, encoding="utf-8")
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
    quoted = NARRATED_TEXT[
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
        return await real_extract(chunks, agent=agent, **kwargs)

    monkeypatch.setattr(
        "novelvideo.structured_extraction.extract_characters_from_chunks",
        fake_extract,
    )
    await structured_builders.build_characters_structured(store)
