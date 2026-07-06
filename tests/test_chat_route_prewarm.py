import pytest
from starlette.websockets import WebSocketDisconnect

from novelvideo.api.routes import chat as chat_route
from novelvideo.chat.store import ChatScope


@pytest.mark.anyio
async def test_send_scope_changed_returns_none_when_client_disconnected(monkeypatch) -> None:
    class DisconnectedWebSocket:
        async def send_json(self, payload):
            raise WebSocketDisconnect(code=1006)

    async def fake_history(username, scope, *, project_ctx=None):
        return []

    monkeypatch.setattr(chat_route, "_history", fake_history)

    result = await chat_route._send_scope_changed(
        DisconnectedWebSocket(),
        {"username": "admin"},
        "admin",
        ChatScope(kind="home"),
    )

    assert result is None


def test_ws_connect_does_not_prewarm_default_home_scope() -> None:
    assert chat_route._should_prewarm_on_ws_connect(ChatScope(kind="home")) is False


def test_ws_connect_can_prewarm_non_home_scope() -> None:
    assert chat_route._should_prewarm_on_ws_connect(ChatScope(kind="project", id="project_a")) is True


def test_scope_from_model_preserves_freezone_canvas_scope() -> None:
    scope = chat_route._scope_from_model(
        chat_route.ChatScopePayload(
            kind="project",
            id="project-a",
            surface="freezone",
            canvasId="canvas-a",
            agentId="agent-2",
        )
    )

    assert scope == ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-2",
    )


def test_scope_from_model_ignores_agent_for_director_scope() -> None:
    scope = chat_route._scope_from_model(
        chat_route.ChatScopePayload(
            kind="project",
            id="project-a",
            surface="director",
            agentId="agent-2",
        )
    )

    assert scope == ChatScope(kind="project", id="project-a", surface="director")


def test_freezone_canvas_bridge_dir_is_agent_scoped(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))

    main_dir = chat_route._canvas_bridge_dir("admin", profile="freezone:main")
    second_dir = chat_route._canvas_bridge_dir("admin", profile="freezone:agent-2")

    assert main_dir != second_dir
    assert main_dir.parent == second_dir.parent
    assert main_dir.parent.name == "supertale_canvas_command_bridge"
    assert ".hermes-freezone" in main_dir.parts
