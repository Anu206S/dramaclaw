"""Character extraction straight from source text, without a knowledge graph.

The legacy path asks Cognee for graph context and lets a model name whoever it
finds there.  Structured extraction inverts that: the model only reports what a
specific span of text supports, and every candidate it returns must quote the
span it came from.  Quotes that cannot be found in the source are dropped, so a
hallucinated name has no route into the character table.

Merging is deliberately conservative.  A character's name is simultaneously a
SQLite primary key, a REST identifier and an asset directory name, so a wrong
merge is expensive to undo and a wrong split is cheap.  Rules therefore only
merge what the text states outright, and anything genuinely ambiguous is left
as separate candidates rather than guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from novelvideo.story_analysis import SourceChunk
from novelvideo.utils.bounded_concurrency import (
    default_llm_concurrency,
    map_bounded,
)

# Titles and kinship terms refer to whoever is on stage at the time. The same
# word in two chapters is routinely two different people, so they never merge
# across chunks on their own and never become aliases automatically.
GENERIC_ADDRESS_TERMS = {
    "母亲", "父亲", "爸爸", "妈妈", "娘", "爹", "儿子", "女儿",
    "哥哥", "姐姐", "弟弟", "妹妹", "爷爷", "奶奶", "外公", "外婆",
    "医生", "护士", "老师", "司机", "老板", "警察", "士兵", "侍卫",
    "陛下", "殿下", "大人", "公子", "小姐", "夫人", "先生", "少爷",
    "掌柜", "伙计", "路人", "村民", "宫女", "太监", "将军", "丫鬟",
    "男人", "女人", "老人", "孩子", "少年", "少女", "他", "她",
}

# Explicit alias statements. Only these license an alias link; a model asserting
# two names are the same without the text saying so is not enough.
_ALIAS_PATTERNS = [
    re.compile(r"(?P<a>[一-鿿]{2,6})\s*(?:又名|本名|原名|真名|化名|人称|人称是|即)\s*(?P<b>[一-鿿]{2,6})"),
    re.compile(r"(?P<a>[一-鿿]{2,6})\s*(?:又|也)\s*(?:叫|称|唤)(?:作|做)?\s*(?P<b>[一-鿿]{2,6})"),
    re.compile(r"(?P<a>[一-鿿]{2,6})\s*(?:小名|乳名|别号|外号|绰号)\s*(?:叫|是|为)?\s*(?P<b>[一-鿿]{2,6})"),
]


class CharacterEvidence(BaseModel):
    quote: str = Field(description="原文中的一句完整引用，必须逐字来自输入文本")
    kind: str = Field(default="mention", description="mention / dialogue / description")


class CharacterCandidate(BaseModel):
    name: str = Field(description="角色在本片段中的称呼，保持原文写法")
    aliases: list[str] = Field(default_factory=list, description="仅限本片段原文明确写出的别名")
    gender: str = Field(default="", description="male / female / 空字符串表示未知")
    description: str = Field(default="", description="本片段支持的简短描述")
    evidence: list[CharacterEvidence] = Field(default_factory=list)


class ChunkCharacterOutput(BaseModel):
    characters: list[CharacterCandidate] = Field(default_factory=list)


CHARACTER_EXTRACTION_SYSTEM_PROMPT = """你是剧本/小说的角色抽取器。输入是作品中的一个片段。

只根据本片段判断，不要推测片段以外的信息。

规则：
- name 用本片段原文中出现的称呼，保持原文写法，不要翻译或改写。
- 每个角色至少给出一条 evidence.quote，必须是本片段原文中逐字出现的一句话。
- 不要编造引用。找不到原文依据的角色不要输出。
- aliases 只填本片段原文明确写出的别名，例如“林默又名小默”。
  仅仅是同一段里出现的另一个称呼，不算别名。
- 不确定两个称呼是不是同一个人时，分别输出两个角色，不要合并。
- 旁白、画外音、镜头提示不是角色。
- 群体（众人、士兵们、村民们）不是角色。"""


@dataclass
class MergedCharacter:
    """One character after deterministic merging across chunks."""

    name: str
    aliases: set[str] = field(default_factory=set)
    gender: str = ""
    description: str = ""
    evidence: list[dict] = field(default_factory=list)
    chunk_ids: set[str] = field(default_factory=set)
    # Names seen in the same text that could be this character but were never
    # stated to be. Surfaced as suggestions; never merged automatically.
    ambiguous_with: set[str] = field(default_factory=set)


def _create_character_extraction_agent(agent: Any = None):
    if agent is not None:
        return agent

    from pydantic_ai import Agent

    from novelvideo.config import (
        get_newapi_structured_output_model_settings,
        get_newapi_text_pydantic_model,
    )

    return Agent(
        get_newapi_text_pydantic_model(
            "CHARACTER_BUILD_MODEL",
            "gemini-3-flash-preview",
            capability="text.generate.agent",
        ),
        system_prompt=CHARACTER_EXTRACTION_SYSTEM_PROMPT,
        model_settings=get_newapi_structured_output_model_settings(),
        output_type=ChunkCharacterOutput,
        name="Structured Character Extractor",
    )


def normalize_character_name(value: str) -> str:
    """Collapse spacing and punctuation noise without altering the name."""
    cleaned = (value or "").replace("　", " ").strip()
    cleaned = cleaned.strip("：:，,。.、·「」『』\"'()（）【】[]")
    return " ".join(cleaned.split())


def is_generic_address(name: str) -> bool:
    return normalize_character_name(name) in GENERIC_ADDRESS_TERMS


def find_explicit_aliases(text: str) -> set[tuple[str, str]]:
    """Return alias pairs the text states outright.

    Only an explicit statement licenses an alias link, because merging two names
    rewrites a primary key that assets and REST paths already point at.
    """
    pairs: set[tuple[str, str]] = set()
    for pattern in _ALIAS_PATTERNS:
        for match in pattern.finditer(text or ""):
            first = normalize_character_name(match.group("a"))
            second = normalize_character_name(match.group("b"))
            if first and second and first != second:
                pairs.add((first, second))
    return pairs


def verify_evidence(
    quote: str, chunk: SourceChunk
) -> tuple[int, int] | None:
    """Locate a quote inside the chunk and return its absolute source offsets.

    A quote that is not present verbatim is rejected: this check is the only
    thing standing between a model's imagination and the character table.
    """
    needle = (quote or "").strip()
    if not needle:
        return None
    local = chunk.text.find(needle)
    if local < 0:
        # Whitespace inside a quote is not meaningful in Chinese prose, and
        # models routinely normalize it. Retry ignoring it before rejecting.
        compact_needle = re.sub(r"\s+", "", needle)
        compact_text = re.sub(r"\s+", "", chunk.text)
        if not compact_needle or compact_needle not in compact_text:
            return None
        return (chunk.source_start, chunk.source_end)
    return (chunk.source_start + local, chunk.source_start + local + len(needle))


async def extract_characters_from_chunks(
    chunks: list[SourceChunk],
    *,
    agent: Any = None,
    concurrency: int | None = None,
    cached_outcomes: Optional[list] = None,
    on_log: Optional[Callable[[str], None]] = None,
    on_chunk_done: Optional[Callable[[SourceChunk, ChunkCharacterOutput], Any]] = None,
    on_chunk_failed: Optional[Callable[[SourceChunk, BaseException], Any]] = None,
) -> tuple[list[MergedCharacter], list[tuple[SourceChunk, BaseException]]]:
    """Extract and merge characters across chunks.

    Chunks are independent, so they run in parallel up to ``concurrency``. A
    chunk that fails is reported and skipped rather than failing the build: one
    unparseable scene must not discard every other scene's characters.
    """

    def log(message: str) -> None:
        if on_log:
            on_log(message)

    replayed = list(cached_outcomes or [])
    if not chunks:
        # Everything was replayed from a previous run; merging still has to run,
        # because merging is what turns per-chunk candidates into characters.
        return merge_character_candidates(replayed), []

    runner = _create_character_extraction_agent(agent)

    async def analyse(chunk: SourceChunk) -> tuple[SourceChunk, ChunkCharacterOutput]:
        result = await runner.run(
            f"【片段 {chunk.section_label}】\n{chunk.text}"
        )
        output = result.output
        if on_chunk_done:
            await _maybe_await(on_chunk_done(chunk, output))
        return chunk, output

    failures: list[tuple[SourceChunk, BaseException]] = []

    def record_failure(chunk: SourceChunk, exc: BaseException) -> None:
        log(f"⚠️ 片段 {chunk.section_label} 抽取失败，已跳过: {exc}")
        failures.append((chunk, exc))

    outcomes = await map_bounded(
        chunks,
        analyse,
        limit=default_llm_concurrency() if concurrency is None else concurrency,
        on_error=record_failure,
    )
    # Reported after the batch so the callback may be async without turning the
    # error path inside map_bounded into an awaiting one.
    for chunk, exc in failures:
        if on_chunk_failed:
            await _maybe_await(on_chunk_failed(chunk, exc))

    succeeded = [outcome for outcome in outcomes if outcome is not None]
    log(f"片段抽取完成: {len(succeeded)}/{len(chunks)} 成功")

    # Replayed chunks merge alongside fresh ones, so a resumed build produces
    # the same characters as an uninterrupted one.
    return merge_character_candidates(replayed + succeeded), failures


def merge_character_candidates(
    outcomes: list[tuple[SourceChunk, ChunkCharacterOutput]],
) -> list[MergedCharacter]:
    """Merge per-chunk candidates using rules only, no model judgement.

    Identical names merge. Explicit alias statements merge. Everything else stays
    separate, because a wrong merge silently destroys data while a wrong split
    is a visible duplicate the user can fix.
    """
    merged: dict[str, MergedCharacter] = {}
    alias_pairs: set[tuple[str, str]] = set()

    for chunk, output in outcomes:
        alias_pairs |= find_explicit_aliases(chunk.text)

        for candidate in output.characters:
            name = normalize_character_name(candidate.name)
            if not name or is_generic_address(name):
                continue

            verified: list[dict] = []
            for item in candidate.evidence:
                span = verify_evidence(item.quote, chunk)
                if span is None:
                    continue
                verified.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "source_start": span[0],
                        "source_end": span[1],
                        "evidence_kind": item.kind or "mention",
                        "evidence_text": item.quote.strip(),
                    }
                )

            # No verifiable quote means nothing in the source supports this
            # character. Drop it rather than trusting the model's assertion.
            if not verified:
                continue

            entry = merged.get(name)
            if entry is None:
                entry = MergedCharacter(name=name)
                merged[name] = entry

            entry.evidence.extend(verified)
            entry.chunk_ids.add(chunk.chunk_id)
            if not entry.gender and candidate.gender in {"male", "female"}:
                entry.gender = candidate.gender
            if not entry.description and candidate.description.strip():
                entry.description = candidate.description.strip()

            for alias in candidate.aliases:
                normalized_alias = normalize_character_name(alias)
                if not normalized_alias or normalized_alias == name:
                    continue
                # A model-proposed alias is only a suggestion unless the text
                # states it. Record it as ambiguity for the user to resolve.
                if (name, normalized_alias) in alias_pairs or (
                    normalized_alias,
                    name,
                ) in alias_pairs:
                    entry.aliases.add(normalized_alias)
                elif not is_generic_address(normalized_alias):
                    entry.ambiguous_with.add(normalized_alias)

    _apply_explicit_alias_merges(merged, alias_pairs)
    return sorted(merged.values(), key=lambda item: (-len(item.evidence), item.name))


def _apply_explicit_alias_merges(
    merged: dict[str, MergedCharacter], alias_pairs: set[tuple[str, str]]
) -> None:
    """Fold explicitly-stated aliases into their primary entry.

    The entry with more evidence wins the primary name, so the canonical record
    is the one the text actually develops rather than a passing nickname.
    """
    for first, second in alias_pairs:
        left = merged.get(first)
        right = merged.get(second)
        if left is None or right is None or left is right:
            # An alias statement naming someone who was never extracted still
            # registers on whichever side exists.
            if left is not None and second not in merged:
                left.aliases.add(second)
            elif right is not None and first not in merged:
                right.aliases.add(first)
            continue

        primary, secondary = (
            (left, right) if len(left.evidence) >= len(right.evidence) else (right, left)
        )
        primary.aliases.add(secondary.name)
        primary.aliases |= secondary.aliases
        primary.aliases.discard(primary.name)
        primary.evidence.extend(secondary.evidence)
        primary.chunk_ids |= secondary.chunk_ids
        primary.ambiguous_with |= secondary.ambiguous_with
        primary.ambiguous_with.discard(primary.name)
        primary.ambiguous_with -= primary.aliases
        if not primary.gender:
            primary.gender = secondary.gender
        if not primary.description:
            primary.description = secondary.description
        merged.pop(secondary.name, None)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value
