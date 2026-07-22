import pytest
from starlette.websockets import WebSocketDisconnect

from novelvideo.api.routes import chat as chat_route
from novelvideo.chat.store import ChatScope
from novelvideo.freezone.canvas_command_bridge import (
    put_pending_clarification_event,
    put_pending_skill_studio_event,
    wait_canvas_command_result,
    wait_clarification_result,
    wait_skill_studio_result,
)


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


def test_canvas_command_wait_writes_timeout_result(tmp_path) -> None:
    bridge_dir = tmp_path / "bridge"
    result = wait_canvas_command_result(
        "bridge-a",
        timeout_seconds=0,
        poll_seconds=0.01,
        bridge_dir=bridge_dir,
        timeout_result={
            "ok": False,
            "tool_call_status": "failed",
            "canvas_apply_status": "timeout",
            "cancelled": True,
            "errors": ["Timed out waiting for frontend canvas command result."],
        },
    )

    assert result is not None
    assert result["ok"] is False
    assert result["canvas_apply_status"] == "timeout"
    assert result["cancelled"] is True
    assert (bridge_dir / "bridge-a.result.json").exists()


def test_canvas_command_tool_result_prefers_user_message_and_agent_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))
    captured: dict[str, object] = {}

    def fake_resolve_canvas_command(key, result, *, bridge_dir=None):
        captured["key"] = key
        captured["result"] = result
        captured["bridge_dir"] = bridge_dir
        return {"ok": True}

    monkeypatch.setattr(chat_route, "resolve_canvas_command", fake_resolve_canvas_command)

    payload = chat_route.CanvasCommandToolResultIn(
        bridge_key="bridge-a",
        project_id="project-a",
        canvas_id="canvas-a",
        agent_id="agent-1",
        tool_call_status="failed",
        canvas_apply_status="failed",
        errors=["edge output role planning_text is not accepted by target imageGenNode"],
        command_results=[
            {
                "commandIndex": -1,
                "type": "validate",
                "status": "error",
                "label": "校验画布命令",
                "error": "Expected source role input_text for link_type prompt_for",
            }
        ],
        message="Frontend executor failed to apply the canvas command.",
        user_message="当前文本需要先作为生成提示词连接到图片节点，我会按可执行的提示词来源来处理。",
        agent_hint="Do not mention raw protocol details such as planning_text or prompt_for.",
    )

    chat_route._resolve_canvas_command_tool_result_payload(payload, username="admin")

    result = captured["result"]
    assert isinstance(result, dict)
    assert result["message"] == payload.user_message
    assert result["user_message"] == payload.user_message
    assert result["agent_instruction"] == payload.agent_hint
    assert result["agent_hint"] == payload.agent_hint
    assert "planning_text" in result["errors"][0]


@pytest.mark.anyio
async def test_watch_pending_skill_studio_events_emits_freezone_bridge_event(monkeypatch, tmp_path) -> None:
    class CapturingWebSocket:
        def __init__(self) -> None:
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)
            raise RuntimeError("stop watcher after first send")

    bridge_dir = tmp_path / "bridge"
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: bridge_dir)
    event = {
        "type": "skill_studio.questions",
        "skill_studio_session_id": "skill_studio_01",
        "title": "确定方向",
        "questions": [{"id": "scope", "title": "主要做什么？", "options": []}],
    }
    put_pending_skill_studio_event(
        key="skill-key-1",
        project_id="project-a",
        canvas_id="canvas-a",
        event=event,
        bridge_dir=bridge_dir,
    )
    websocket = CapturingWebSocket()

    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )
    chat_route.chat_store.append_message("admin", scope, "user", "创建一个 Skill", turn_id="turn-a")

    await chat_route._watch_pending_skill_studio_events(
        websocket=websocket,
        username="admin",
        scope=scope,
        turn_id="turn-a",
        send_lock=None,
        emitted_bridge_keys=set(),
        started_at=0,
    )

    assert websocket.sent == [
        {
            "type": "skill_studio.event",
            "scope": {
                "kind": "project",
                "id": "project-a",
                "surface": "freezone",
                "canvasId": "canvas-a",
                "agentId": "agent-1",
            },
            "turn_id": "turn-a",
            "canvas_id": "canvas-a",
            "agent_id": "agent-1",
            "bridge_key": "skill-key-1",
            "event": event,
        }
    ]
    messages = chat_route.chat_store.list_messages("admin", scope)
    assert messages[-1]["turn_id"] == "turn-a"
    assert messages[-1]["ui_events"][0]["type"] == "skill_studio.questions"
    assert messages[-1]["ui_events"][0]["skill_studio_session_id"] == "skill_studio_01"
    assert messages[-1]["ui_events"][0]["bridge_key"] == "skill-key-1"
    assert messages[-1]["ui_events"][0]["canvas_id"] == "canvas-a"
    assert messages[-1]["ui_events"][0]["agent_id"] == "agent-1"


@pytest.mark.anyio
async def test_watch_pending_skill_studio_events_emits_status_progress_event(monkeypatch, tmp_path) -> None:
    class CapturingWebSocket:
        def __init__(self) -> None:
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)
            raise RuntimeError("stop watcher after first send")

    bridge_dir = tmp_path / "bridge"
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: bridge_dir)
    event = {
        "type": "skill_studio.status",
        "skill_studio_session_id": "skill_studio_01",
        "status": "draft_recipe_ready",
        "message": "已生成 Recipe 1 / 2",
    }
    put_pending_skill_studio_event(
        key="skill-status-1",
        project_id="project-a",
        canvas_id="canvas-a",
        event=event,
        bridge_dir=bridge_dir,
    )
    websocket = CapturingWebSocket()
    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )
    chat_route.chat_store.append_message("admin", scope, "user", "创建一个 Skill", turn_id="turn-a")

    await chat_route._watch_pending_skill_studio_events(
        websocket=websocket,
        username="admin",
        scope=scope,
        turn_id="turn-a",
        send_lock=None,
        emitted_bridge_keys=set(),
        started_at=0,
    )

    assert websocket.sent[0]["type"] == "skill_studio.event"
    assert websocket.sent[0]["bridge_key"] == "skill-status-1"
    assert websocket.sent[0]["event"] == event
    messages = chat_route.chat_store.list_messages("admin", scope)
    assert messages[-1]["ui_events"][0]["type"] == "skill_studio.status"
    assert messages[-1]["ui_events"][0]["message"] == "已生成 Recipe 1 / 2"


def test_skill_studio_status_frame_uses_backend_intent_detection() -> None:
    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )

    frame = chat_route._skill_studio_status_frame(
        scope=scope,
        turn_id="turn-a",
        text="我想创建一个宣传家乡文化的海报 skill",
    )

    assert frame == {
        "type": "skill_studio.status",
        "scope": {
            "kind": "project",
            "id": "project-a",
            "surface": "freezone",
            "canvasId": "canvas-a",
            "agentId": "agent-1",
        },
        "turn_id": "turn-a",
        "status": "routing",
        "message": "正在整理 Skill 方向...",
    }
    assert chat_route._skill_studio_status_frame(
        scope=scope,
        turn_id="turn-b",
        text="帮我加一个视频节点",
    ) is None


def test_skill_studio_status_frame_uses_user_text_not_canvas_context() -> None:
    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )

    enhanced_text = (
        "查看下当前节点详情然后返回ok\n\n"
        "[SUPERTALE_CANVAS_NODE_REFERENCES]\n"
        "node_type: skillNode\n"
        "available_actions: add_next_node, run_skill\n"
        "[/SUPERTALE_CANVAS_NODE_REFERENCES]"
    )

    assert chat_route._skill_studio_status_frame(
        scope=scope,
        turn_id="turn-node-detail",
        text=enhanced_text,
        user_text="查看下当前节点详情然后返回ok",
    ) is None


def test_resolve_skill_studio_tool_result_writes_bridge_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path)
    payload = chat_route.SkillStudioToolResultIn(
        turn_id="turn-a",
        bridge_key="skill-key-1",
        project_id="project-a",
        canvas_id="canvas-a",
        agent_id="agent-1",
        skill_studio_status="answered",
        action="submit",
        selections={"scope": "planning"},
        message="用户已提交选择",
    )

    resolved = chat_route._resolve_skill_studio_tool_result_payload(payload, username="alice")

    assert resolved["ok"] is True
    assert resolved["skill_studio_status"] == "answered"
    assert resolved["selections"] == {"scope": "planning"}
    assert resolved["agent_instruction"] == "Continue the Skill Studio flow using the frontend response."
    assert wait_skill_studio_result("skill-key-1", timeout_seconds=0.1, bridge_dir=tmp_path) == resolved


def test_resolve_saved_skill_studio_tool_result_tells_agent_catalog_is_formal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path)
    saved_items: list[tuple[str, dict]] = []

    def fake_save_user_agent_config_item(*, username: str, kind: str, payload: dict) -> dict:
        assert username == "alice"
        saved_items.append((kind, payload))
        return payload

    monkeypatch.setattr(chat_route, "save_user_agent_config_item", fake_save_user_agent_config_item)
    payload = chat_route.SkillStudioToolResultIn(
        turn_id="turn-a",
        bridge_key="skill-key-2",
        project_id="project-a",
        canvas_id="canvas-a",
        agent_id="agent-1",
        skill_studio_status="catalog_saved",
        action="confirm_add",
        draft={"skill": {"id": "home-culture-poster"}, "recipes": [{"id": "home-culture-poster-image"}]},
        message="已保存为正式 Skill / Recipe",
    )

    resolved = chat_route._resolve_skill_studio_tool_result_payload(payload, username="alice")

    assert resolved["ok"] is True
    assert resolved["skill_studio_status"] == "catalog_saved"
    assert resolved["saved_to_catalog"] is True
    assert resolved["saved_skill_ids"] == ["home-culture-poster"]
    assert resolved["saved_recipe_ids"] == ["home-culture-poster-image"]
    assert "saved" in resolved["agent_instruction"]
    assert "Do not ask the user to save it again" in resolved["agent_instruction"]
    assert saved_items == [
        ("skills", {"id": "home-culture-poster"}),
        ("recipes", {"id": "home-culture-poster-image"}),
    ]
    assert wait_skill_studio_result("skill-key-2", timeout_seconds=0.1, bridge_dir=tmp_path) == resolved


def test_resolve_cancelled_skill_studio_tool_result_stops_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path)
    payload = chat_route.SkillStudioToolResultIn(
        turn_id="turn-a",
        bridge_key="skill-key-3",
        project_id="project-a",
        canvas_id="canvas-a",
        agent_id="agent-1",
        skill_studio_status="catalog_cancelled",
        action="cancel",
        draft={"skill": {"id": "home-culture-poster"}, "recipes": []},
        message="用户已取消 Skill Studio 草稿保存。",
    )

    resolved = chat_route._resolve_skill_studio_tool_result_payload(payload, username="alice")

    assert resolved["ok"] is True
    assert resolved["skill_studio_status"] == "catalog_cancelled"
    assert resolved["saved_to_catalog"] is False
    assert "Do not continue" in resolved["agent_instruction"]
    assert "canvas" in resolved["agent_instruction"]
    assert "Continue the Skill Studio flow" not in resolved["agent_instruction"]
    assert wait_skill_studio_result("skill-key-3", timeout_seconds=0.1, bridge_dir=tmp_path) == resolved


def test_tool_result_payload_includes_structured_json() -> None:
    text = '{"ok":true,"skills":[{"id":"pixar-ip-brand-ad"}]}'

    payload = chat_route._tool_result_payload(text)

    assert payload["text"] == text
    assert payload["json"] == {"ok": True, "skills": [{"id": "pixar-ip-brand-ad"}]}


def test_tool_result_payload_prefers_explicit_structured_json() -> None:
    payload = chat_route._tool_result_payload(
        "freezone_skill_list result\n- **count:** 1",
        {"ok": True, "skills": [{"id": "pixar-ip-brand-ad"}]},
    )

    assert payload["text"].startswith("freezone_skill_list result")
    assert payload["json"] == {"ok": True, "skills": [{"id": "pixar-ip-brand-ad"}]}


def test_resolve_revision_skill_studio_tool_result_starts_question_flow(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path)
    payload = chat_route.SkillStudioToolResultIn(
        turn_id="turn-a",
        bridge_key="skill-key-4",
        project_id="project-a",
        canvas_id="canvas-a",
        agent_id="agent-1",
        skill_studio_status="revision_started",
        action="start_revision",
        draft={"skill": {"id": "home-culture-poster", "description": "当前草稿"}, "recipes": []},
        message="用户已启动 Skill Studio 草稿修改会话。",
    )

    resolved = chat_route._resolve_skill_studio_tool_result_payload(payload, username="alice")

    assert resolved["ok"] is True
    assert resolved["skill_studio_status"] == "revision_started"
    assert resolved["saved_to_catalog"] is False
    assert resolved["draft"] == payload.draft
    assert "Start a Skill Studio draft revision question flow" in resolved["agent_instruction"]
    assert "current draft" in resolved["agent_instruction"]
    assert "already asked to revise" in resolved["agent_instruction"]
    assert "Do not ask whether revision is needed" in resolved["agent_instruction"]
    assert "Do not ask whether to save the current draft" in resolved["agent_instruction"]
    assert "save_now" in resolved["agent_instruction"]
    assert "freezone_request_user_clarification" in resolved["agent_instruction"]
    assert "exactly one question object" in resolved["agent_instruction"]
    assert "wait for the answer before deciding the next question" in resolved["agent_instruction"]
    assert "freezone_begin_agent_catalog_draft" in resolved["agent_instruction"]
    assert "freezone_finish_agent_catalog_draft" in resolved["agent_instruction"]
    assert "expected_recipe_count" in resolved["agent_instruction"]
    assert "full draft count" in resolved["agent_instruction"]
    assert "Do not pass the full Skill/Recipe catalog in one tool call" in resolved["agent_instruction"]
    assert "Do not answer with prose" in resolved["agent_instruction"]
    assert "Do not save" in resolved["agent_instruction"]
    assert wait_skill_studio_result("skill-key-4", timeout_seconds=0.1, bridge_dir=tmp_path) == resolved


@pytest.mark.anyio
async def test_resolve_skill_studio_tool_result_persists_submitted_ui_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path / "bridge")
    monkeypatch.setattr(chat_route, "_project_context_for_scope", lambda *_args, **_kwargs: None)
    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )
    chat_route.chat_store.append_message("admin", scope, "user", "创建一个 Skill", turn_id="turn-a")
    chat_route.chat_store.append_ui_event(
        "admin",
        scope,
        "turn-a",
        {
            "type": "skill_studio.questions",
            "bridge_key": "skill-key-1",
            "skill_studio_session_id": "skill_studio_01",
            "questions": [],
        },
    )

    await chat_route.resolve_skill_studio_tool_result(
        chat_route.SkillStudioToolResultIn(
            turn_id="turn-a",
            bridge_key="skill-key-1",
            project_id="project-a",
            canvas_id="canvas-a",
            agent_id="agent-1",
            skill_studio_status="answered",
            action="submit",
            selections={"scope": {"option_ids": ["planning"], "custom_text": ""}},
            message="用户已提交选择",
        ),
        user={"username": "admin"},
    )

    messages = chat_route.chat_store.list_messages("admin", scope)
    submitted_events = [
        event
        for event in messages[-1]["ui_events"]
        if event.get("type") == "skill_studio.questions" and event.get("submitted") is True
    ]
    assert submitted_events
    assert submitted_events[-1]["bridge_key"] == "skill-key-1"
    assert submitted_events[-1]["action"] == "submit"
    assert submitted_events[-1]["selections"] == {"scope": {"option_ids": ["planning"], "custom_text": ""}}


@pytest.mark.anyio
async def test_resolve_skill_studio_draft_tool_result_persists_submitted_ui_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path / "bridge")
    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )
    draft = {
        "skill": {"id": "edited-skill", "description": "编辑后的草稿"},
        "recipes": [],
        "summary": "草稿已编辑",
    }
    chat_route.chat_store.append_message("admin", scope, "user", "创建一个 Skill", turn_id="turn-a")
    chat_route.chat_store.append_ui_event(
        "admin",
        scope,
        "turn-a",
        {
            "type": "skill_studio.draft",
            "bridge_key": "draft-key-1",
            "skill_studio_session_id": "skill_studio_01",
            "skill": {"id": "original-skill"},
            "recipes": [],
        },
    )

    await chat_route.resolve_skill_studio_tool_result(
        chat_route.SkillStudioToolResultIn(
            turn_id="turn-a",
            bridge_key="draft-key-1",
            project_id="project-a",
            canvas_id="canvas-a",
            agent_id="agent-1",
            skill_studio_status="draft_submitted",
            action="submit_draft",
            draft=draft,
            message="用户已提交草稿",
        ),
        user={"username": "admin"},
    )

    messages = chat_route.chat_store.list_messages("admin", scope)
    submitted_events = [
        event
        for event in messages[-1]["ui_events"]
        if event.get("type") == "skill_studio.draft" and event.get("submitted") is True
    ]
    assert submitted_events
    assert submitted_events[-1]["bridge_key"] == "draft-key-1"
    assert submitted_events[-1]["action"] == "submit_draft"
    assert submitted_events[-1]["draft"] == draft


@pytest.mark.anyio
async def test_receive_bridge_results_during_turn_resolves_skill_studio_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path / "bridge")
    saved_items: list[tuple[str, dict]] = []

    def fake_save_user_agent_config_item(*, username: str, kind: str, payload: dict) -> dict:
        assert username == "admin"
        saved_items.append((kind, payload))
        return payload

    monkeypatch.setattr(chat_route, "save_user_agent_config_item", fake_save_user_agent_config_item)

    class FakeWebSocket:
        def __init__(self) -> None:
            self.frames = [
                {
                    "type": "skill_studio.result",
                    "turn_id": "turn-a",
                    "bridge_key": "skill-ws-key-1",
                    "project_id": "project-a",
                    "canvas_id": "canvas-a",
                    "agent_id": "agent-1",
                    "skill_studio_status": "catalog_saved",
                    "action": "confirm_add",
                    "saved_to_catalog": True,
                    "draft": {
                        "skill": {"id": "home-culture-video"},
                        "recipes": [{"id": "home-culture-video-script"}],
                    },
                }
            ]

        async def receive_json(self):
            if self.frames:
                return self.frames.pop(0)
            raise chat_route.WebSocketDisconnect()

    await chat_route._receive_bridge_results_during_turn(
        websocket=FakeWebSocket(),  # type: ignore[arg-type]
        user={"username": "admin"},
        username="admin",
    )

    resolved = wait_skill_studio_result("skill-ws-key-1", timeout_seconds=0.1, bridge_dir=tmp_path / "bridge")
    assert resolved is not None
    assert resolved["skill_studio_status"] == "catalog_saved"
    assert resolved["saved_skill_ids"] == ["home-culture-video"]
    assert resolved["saved_recipe_ids"] == ["home-culture-video-script"]
    assert saved_items == [
        ("skills", {"id": "home-culture-video"}),
        ("recipes", {"id": "home-culture-video-script"}),
    ]


@pytest.mark.anyio
async def test_receive_bridge_results_during_turn_resolves_clarification_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path / "bridge")

    class FakeWebSocket:
        def __init__(self) -> None:
            self.frames = [
                {
                    "type": "assistant.clarification.result",
                    "turn_id": "turn-a",
                    "bridge_key": "clarify-test-key",
                    "project_id": "project-a",
                    "canvas_id": "canvas-a",
                    "agent_id": "agent-1",
                    "clarification_status": "answered",
                    "action": "submit",
                    "answers": {"scope": {"option_ids": ["locals"], "custom_text": ""}},
                    "message": "用户已完成选择，请结合当前上下文继续。",
                }
            ]

        async def receive_json(self):
            if self.frames:
                return self.frames.pop(0)
            raise chat_route.WebSocketDisconnect()

    await chat_route._receive_bridge_results_during_turn(
        websocket=FakeWebSocket(),  # type: ignore[arg-type]
        user={"username": "admin"},
        username="admin",
    )

    resolved = wait_clarification_result("clarify-test-key", timeout_seconds=0.1, bridge_dir=tmp_path / "bridge")
    assert resolved is not None
    assert resolved["clarification_status"] == "answered"
    assert resolved["answers"]["scope"]["option_ids"] == ["locals"]
    assert resolved["agent_instruction"] == "Continue using the frontend clarification response."


@pytest.mark.anyio
async def test_watch_pending_clarification_events_emits_freezone_bridge_event(monkeypatch, tmp_path) -> None:
    class CapturingWebSocket:
        def __init__(self) -> None:
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)
            raise RuntimeError("stop watcher after first send")

    bridge_dir = tmp_path / "bridge"
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: bridge_dir)
    event = {
        "type": "assistant.clarification.request",
        "clarification_id": "clarify_01",
        "title": "先确认方向",
        "questions": [{"id": "scope", "title": "主要做什么？", "options": []}],
    }
    put_pending_clarification_event(
        key="clarify-key-1",
        project_id="project-a",
        canvas_id="canvas-a",
        event=event,
        bridge_dir=bridge_dir,
    )
    websocket = CapturingWebSocket()

    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )
    chat_route.chat_store.append_message("admin", scope, "user", "创建一个 Skill", turn_id="turn-a")

    await chat_route._watch_pending_clarification_events(
        websocket=websocket,
        username="admin",
        scope=scope,
        turn_id="turn-a",
        send_lock=None,
        emitted_bridge_keys=set(),
        started_at=0,
    )

    assert websocket.sent == [
        {
            "type": "assistant.clarification.event",
            "scope": {
                "kind": "project",
                "id": "project-a",
                "surface": "freezone",
                "canvasId": "canvas-a",
                "agentId": "agent-1",
            },
            "turn_id": "turn-a",
            "canvas_id": "canvas-a",
            "agent_id": "agent-1",
            "bridge_key": "clarify-key-1",
            "event": event,
        }
    ]
    messages = chat_route.chat_store.list_messages("admin", scope)
    assert messages[-1]["turn_id"] == "turn-a"
    assert messages[-1]["ui_events"][0]["type"] == "assistant.clarification.request"
    assert messages[-1]["ui_events"][0]["clarification_id"] == "clarify_01"
    assert messages[-1]["ui_events"][0]["bridge_key"] == "clarify-key-1"


def test_resolve_clarification_tool_result_writes_bridge_result(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path)
    payload = chat_route.ClarificationToolResultIn(
        turn_id="turn-a",
        bridge_key="clarify-key-1",
        project_id="project-a",
        canvas_id="canvas-a",
        agent_id="agent-1",
        clarification_status="answered",
        action="submit",
        answers={"scope": {"option_ids": ["workflow"], "custom_text": "偏海报"}},
        message="用户已提交补充信息",
    )

    resolved = chat_route._resolve_clarification_tool_result_payload(payload, username="alice")

    assert resolved["ok"] is True
    assert resolved["clarification_status"] == "answered"
    assert resolved["answers"]["scope"]["option_ids"] == ["workflow"]
    assert resolved["agent_instruction"] == "Continue using the frontend clarification response."
    assert wait_clarification_result("clarify-key-1", timeout_seconds=0.1, bridge_dir=tmp_path) == resolved


@pytest.mark.anyio
async def test_resolve_clarification_tool_result_persists_submitted_ui_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NOVELVIDEO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(chat_route, "_canvas_bridge_dir", lambda *_args, **_kwargs: tmp_path / "bridge")
    scope = ChatScope(
        kind="project",
        id="project-a",
        surface="freezone",
        canvas_id="canvas-a",
        agent_id="agent-1",
    )
    chat_route.chat_store.append_message("admin", scope, "user", "需要补充信息", turn_id="turn-a")
    chat_route.chat_store.append_ui_event(
        "admin",
        scope,
        "turn-a",
        {
            "type": "assistant.clarification.request",
            "bridge_key": "clarify-key-1",
            "clarification_id": "clarify-1",
            "questions": [],
        },
    )

    await chat_route.resolve_clarification_tool_result(
        chat_route.ClarificationToolResultIn(
            turn_id="turn-a",
            bridge_key="clarify-key-1",
            project_id="project-a",
            canvas_id="canvas-a",
            agent_id="agent-1",
            clarification_status="answered",
            action="submit",
            answers={"scope": {"option_ids": ["user"], "custom_text": ""}},
            message="用户已提交补充信息",
        ),
        user={"username": "admin"},
    )

    messages = chat_route.chat_store.list_messages("admin", scope)
    submitted_events = [
        event
        for event in messages[-1]["ui_events"]
        if event.get("type") == "assistant.clarification.request" and event.get("submitted") is True
    ]
    assert submitted_events
    assert submitted_events[-1]["bridge_key"] == "clarify-key-1"
    assert submitted_events[-1]["answers"] == {"scope": {"option_ids": ["user"], "custom_text": ""}}


@pytest.mark.anyio
async def test_ai_assistant_access_check_uses_chat_feature_key(monkeypatch) -> None:
    seen = {}

    class FakeUsageMeter:
        async def require_feature_credit_balance(self, **kwargs):
            seen.update(kwargs)
            return {"allowed": True}

    monkeypatch.setattr(chat_route, "get_usage_meter", lambda: FakeUsageMeter())

    await chat_route._require_ai_assistant_access(
        user={"id": "usr_1", "username": "alice"},
        scope=ChatScope(kind="home"),
    )

    assert seen["user_id"] == "usr_1"
    assert seen["feature_key"] == "ai_assistant_chat"
    assert seen["project_id"] == ""
    assert seen["resource_kind"] == "chat"
    assert seen["metadata"]["scope"] == {"kind": "home", "id": None}
