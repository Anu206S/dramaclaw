"""The evidence identity must survive every hop of the real chat path.

Every layer here was a place the identity was silently dropped: the pool facade
declares an explicit signature and swallowed unknown keywords, and the service
call site simply never passed them. Unit tests on the issuer all passed anyway,
which is why this asserts the plumbing rather than the minting.
"""

from __future__ import annotations

import inspect

import pytest

from novelvideo.chat import hermes_pool, hermes_sdk, service


def test_the_pool_facade_forwards_the_identity() -> None:
    """A __getattr__ proxy would forward anything, but stream is explicit."""
    signature = inspect.signature(hermes_pool._ManagedHermesThread.stream)
    for name in ("episode_id", "project_id"):
        assert name in signature.parameters, (
            f"{name} is dropped by the pool facade before it reaches the worker"
        )


def test_the_worker_accepts_the_identity() -> None:
    signature = inspect.signature(hermes_sdk.HermesSdkThread.stream)
    for name in ("episode_id", "project_id"):
        assert name in signature.parameters


@pytest.mark.asyncio
async def test_the_facade_actually_passes_them_through() -> None:
    seen: dict[str, object] = {}

    class FakeThread:
        async def stream(self, prompt, *, current_project=None, episode_id=None, project_id=None):
            seen.update(prompt=prompt, current_project=current_project,
                        episode_id=episode_id, project_id=project_id)
            if False:  # pragma: no cover - makes this an async generator
                yield None

    class FakeOwner:
        async def _begin_turn(self, slot): return None
        async def _finish_turn(self, slot): return None

    class FakeSlot:
        thread = FakeThread()

    facade = hermes_pool._ManagedHermesThread(FakeOwner(), FakeSlot())
    async for _ in facade.stream("hi", current_project="p", episode_id="ep", project_id="pr"):
        pass
    assert seen == {"prompt": "hi", "current_project": "p",
                    "episode_id": "ep", "project_id": "pr"}


def test_home_scope_states_the_absence_of_a_project_explicitly() -> None:
    """BrainClaw refuses to invent a grouping, so 'no project' must be said."""
    from novelvideo.chat.hermes_egress import HOME_SCOPE_EGRESS_PROJECT_ID

    identity = service._evidence_identity(None, None, "main")
    assert identity["project_id"] == HOME_SCOPE_EGRESS_PROJECT_ID
    assert identity["episode_id"].startswith("conversation:")


def test_a_canvas_is_its_own_episode_and_a_project_groups_them() -> None:
    class Scope:
        canvas_id = "canvas-7"

    canvas = service._evidence_identity("proj-a", Scope(), "freezone:main")
    plain = service._evidence_identity("proj-a", None, "main")

    assert canvas["episode_id"] == "canvas:canvas-7"
    assert canvas["episode_id"] != plain["episode_id"], "a canvas is not the plain conversation"
    # The project is what groups distinct episodes for fold-splitting.
    assert canvas["project_id"] == plain["project_id"] == "proj-a"


def test_the_same_conversation_is_one_stable_episode() -> None:
    """Over-grouping costs power; under-grouping manufactures independence."""
    first = service._evidence_identity("proj-a", None, "main")
    second = service._evidence_identity("proj-a", None, "main")
    assert first == second

    other_profile = service._evidence_identity("proj-a", None, "freezone:x")
    assert other_profile["episode_id"] != first["episode_id"]
    assert other_profile["project_id"] == first["project_id"]


def test_different_projects_never_share_a_group() -> None:
    a = service._evidence_identity("proj-a", None, "main")
    b = service._evidence_identity("proj-b", None, "main")
    assert a["project_id"] != b["project_id"]
    assert a["episode_id"] != b["episode_id"]
