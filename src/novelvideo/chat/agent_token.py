"""Shared lazy resolution for short-lived DramaClaw agent tokens."""

from __future__ import annotations

import os
from pathlib import Path


def agent_token_configured() -> bool:
    """Return whether a static token or rotating token file is configured."""

    return bool(
        os.environ.get("DRAMACLAW_AGENT_TOKEN", "").strip()
        or os.environ.get("DRAMACLAW_AGENT_TOKEN_FILE", "").strip()
    )


def current_agent_token() -> str:
    """Read the current turn token lazily so long-lived MCP processes stay safe."""

    token_file = os.environ.get("DRAMACLAW_AGENT_TOKEN_FILE", "").strip()
    if token_file:
        try:
            return Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return os.environ.get("DRAMACLAW_AGENT_TOKEN", "").strip()
