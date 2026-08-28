"""Delegated project boundaries shared by API and project resolution."""

from __future__ import annotations

from fastapi import HTTPException


def enforce_agent_project_scope(user: dict, project_id: str) -> None:
    """A parent user's membership must not widen a delegated project token."""
    if user.get("credential_kind") != "agent_session":
        return
    if (
        user.get("current_scope_kind") != "project"
        or user.get("current_project_id") != project_id
    ):
        raise HTTPException(status_code=403, detail="Agent session scope mismatch")
