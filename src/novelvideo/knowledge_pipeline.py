"""Project-bound knowledge pipeline selection (dual-track).

Two tracks coexist permanently:

``cognee_legacy``
    Everything created before structured extraction existed.  These projects are
    bound to a Cognee dataset and an embedding model, and their behaviour must
    not change.

``structured_v2``
    Deterministic extraction straight from the imported source text into SQLite.
    No embedding model, no vector index, no graph search.

The track is a permanent property of a project, chosen at creation time and
never migrated.  It is stored under ``knowledge_pipeline`` in
``project_config.json``.

Two rules make the dual track safe:

1. The track is read from the *raw* configuration file, never from the effective
   configuration.  ``_effective_project_config`` merges
   ``_default_project_config()`` over the stored values, so a default entry would
   silently reclassify every legacy project that predates the field.

2. A missing field means ``cognee_legacy``.  Absence of the embedding keys is not
   a usable signal either: ``ensure_cognee_embedding_binding_in_state_dir``
   backfills them for legacy projects, so only the explicit
   ``knowledge_pipeline`` field can be trusted.
"""

from __future__ import annotations

from pathlib import Path

KNOWLEDGE_PIPELINE_KEY = "knowledge_pipeline"

COGNEE_LEGACY = "cognee_legacy"
STRUCTURED_V2 = "structured_v2"


class KnowledgePipelineUnsupported(RuntimeError):
    """Raised when a project asks for a capability its track does not provide.

    Structured projects must fail loudly here rather than fall back to the
    Cognee path: a silent fallback would re-bind the project to an embedding
    model, which is exactly what the second track exists to avoid.
    """

    error_code = "KNOWLEDGE_PIPELINE_UNSUPPORTED"


def knowledge_pipeline_from_state_dir(state_dir: str | Path | None) -> str:
    """Return the track recorded for a project, defaulting to the legacy one."""
    if not state_dir:
        return COGNEE_LEGACY

    from novelvideo.project_config import load_project_config_file_from_state_dir

    raw = load_project_config_file_from_state_dir(state_dir)
    value = str(raw.get(KNOWLEDGE_PIPELINE_KEY, "") or "").strip()
    return STRUCTURED_V2 if value == STRUCTURED_V2 else COGNEE_LEGACY


def is_structured_v2(state_dir: str | Path | None) -> bool:
    return knowledge_pipeline_from_state_dir(state_dir) == STRUCTURED_V2


def is_cognee_legacy(state_dir: str | Path | None) -> bool:
    return not is_structured_v2(state_dir)
