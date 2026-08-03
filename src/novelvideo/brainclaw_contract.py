"""Shared BrainClaw routing and fixed-task profile contract."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from typing import Iterator, Mapping


class BrainClawProfile(StrEnum):
    COGNEE_GRAPH_INGEST = "cognee_graph_ingest"
    EPISODE_SCENE_PLANNING = "episode_scene_planning"
    EPISODE_PROP_PLANNING = "episode_prop_planning"
    GLOBAL_VIDEO_MOTION_PLANNING = "global_video_motion_planning"
    KEYFRAME_TRANSITION_PROMPT_GENERATION = "keyframe_transition_prompt_generation"
    SEEDANCE2_PROMPT_COMPOSITION = "seedance2_prompt_composition"
    GLOBAL_VIDEO_IDENTITY_DETECTION = "global_video_identity_detection"
    IDENTITY_CAST_PLANNING = "identity_cast_planning"
    IDENTITY_DEFAULT_ANALYSIS = "identity_default_analysis"
    IDENTITY_SPECIAL_ANALYSIS = "identity_special_analysis"
    IDENTITY_APPEARANCE_WRITING = "identity_appearance_writing"
    LITERAL_BEAT_METADATA = "literal_beat_metadata"
    SCENE_BLOCK_NORMALIZATION = "scene_block_normalization"
    SCENE_ENVIRONMENT_ENRICHMENT = "scene_environment_enrichment"
    FREEZONE_TRANSLATION = "freezone_translation"
    FREEZONE_STORY_SCRIPT_WRITING = "freezone_story_script_writing"
    FREEZONE_VISION_ANALYSIS = "freezone_vision_analysis"
    STYLE_ANALYSIS = "style_analysis"
    CONTENT_REWRITE = "content_rewrite"
    SCREENPLAY_NORMALIZATION = "screenplay_normalization"
    EPISODE_SCENE_RECONCILIATION = "episode_scene_reconciliation"
    NARRATED_SCENE_ASSET_PLANNING = "narrated_scene_asset_planning"
    STAGING_PROP_PLANNING = "staging_prop_planning"
    EPISODE_STORY_PLANNING = "episode_story_planning"
    COGNEE_EVENT_EXTRACTION = "cognee_event_extraction"


PROFILE_HEADER = "X-BrainClaw-Profile"
PROFILE_VERSION_HEADER = "X-BrainClaw-Profile-Version"
PROFILE_VERSION = "1"

_profile_context: ContextVar[BrainClawProfile | None] = ContextVar(
    "brainclaw_profile",
    default=None,
)


def current_brainclaw_profile() -> BrainClawProfile | None:
    return _profile_context.get()


@contextmanager
def brainclaw_profile_scope(
    profile: BrainClawProfile | None,
) -> Iterator[None]:
    """Apply one fixed-task profile only inside the current async context."""
    token = _profile_context.set(profile)
    try:
        yield
    finally:
        _profile_context.reset(token)


def is_brainclaw_runtime() -> bool:
    """Return whether the effective LLM route is RelayClaw BrainClaw."""
    from novelvideo.model_gateway_settings import get_effective_llm_config

    return get_effective_llm_config().is_brainclaw


def brainclaw_profile_headers(
    profile: BrainClawProfile | None = None,
    *,
    brainclaw_active: bool | None = None,
) -> dict[str, str]:
    selected = profile or current_brainclaw_profile()
    if selected is None:
        return {}
    active = is_brainclaw_runtime() if brainclaw_active is None else brainclaw_active
    if not active:
        return {}
    return {
        PROFILE_HEADER: selected.value,
        PROFILE_VERSION_HEADER: PROFILE_VERSION,
    }


def merge_brainclaw_headers(
    headers: Mapping[str, str] | None,
    profile: BrainClawProfile | None = None,
    *,
    brainclaw_active: bool | None = None,
) -> dict[str, str]:
    """Preserve caller headers and add the centrally-defined profile contract."""
    merged = dict(headers or {})
    merged.update(
        brainclaw_profile_headers(
            profile,
            brainclaw_active=brainclaw_active,
        )
    )
    return merged
