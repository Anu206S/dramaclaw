from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _reset_modules():
    import novelvideo.ports as ports
    import novelvideo.ports.registry as registry

    registry._PORTS.clear()
    registry._BOOTSTRAPPED = False
    api_auth = importlib.import_module("novelvideo.api.auth")
    return registry, ports, api_auth


def _request(*, cookie: str | None = None, authorization: str | None = None) -> Request:
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"st_session={cookie}".encode()))
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/me",
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


@pytest.mark.asyncio
async def test_browser_path_without_registered_auth_port_returns_pinned_503() -> None:
    _registry, _ports, api_auth = _reset_modules()

    with pytest.raises(HTTPException) as exc:
        await api_auth.get_api_user(_request())

    assert exc.value.status_code == 503
    assert exc.value.detail == "auth backend not initialised"


@pytest.mark.asyncio
async def test_cookie_path_without_registered_auth_port_returns_pinned_503() -> None:
    _registry, _ports, api_auth = _reset_modules()

    with pytest.raises(HTTPException) as exc:
        await api_auth.get_api_user(_request(cookie="bad-cookie"))

    assert exc.value.status_code == 503
    assert exc.value.detail == "auth backend not initialised"


@pytest.mark.asyncio
async def test_bearer_path_without_registered_auth_session_port_returns_pinned_401() -> None:
    _registry, _ports, api_auth = _reset_modules()

    with pytest.raises(HTTPException) as exc:
        await api_auth.get_api_user(_request(authorization="Bearer bad-token"))

    assert exc.value.status_code == 401
    assert exc.value.detail == "Agent sessions require control plane"


@pytest.mark.asyncio
async def test_verify_credential_for_request_keeps_ce_cookie_less_stream_alive(monkeypatch) -> None:
    registry, _ports, api_auth = _reset_modules()
    monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)
    monkeypatch.setenv("ST_EDITION", "ce")
    monkeypatch.setenv("ST_LOCAL_USERNAME", "alice")
    registry.ensure_bootstrap()

    user = await api_auth.verify_credential_for_request(_request())

    assert user == {"id": "local", "user_id": "local", "username": "alice", "role": "owner"}


@pytest.mark.asyncio
async def test_verify_credential_for_request_returns_none_for_ee_missing_cookie(
    monkeypatch,
) -> None:
    _registry, _ports, api_auth = _reset_modules()

    async def fail_browser_session(_raw_cookie):
        raise HTTPException(status_code=401, detail="Missing session or agent token")

    monkeypatch.setattr(api_auth, "_verify_browser_session", fail_browser_session)

    assert await api_auth.verify_credential_for_request(_request()) is None


@pytest.mark.parametrize("project", ["project-a", "project-b"])
def test_agent_body_and_query_project_match_delegated_scope(scoped_api_client, project):
    api = scoped_api_client
    headers = api.headers["write_a"]
    response = api.client.post("/api/v1/styles", headers=headers, json={
        "id": "scope_marker", "name": "Scope marker", "project": project,
    })
    expected = 200 if project == "project-a" else 403
    assert response.status_code == expected, response.text
    config_path = api.root / project / "state" / "project_config.json"
    if expected == 200:
        assert response.json()["ok"]
        assert "scope_marker" in config_path.read_text()
    else:
        assert not config_path.exists()
    assert api.client.get("/api/v1/styles", params={"project": project},
                          headers=api.headers["read_a"]).status_code == expected


def test_correctly_scoped_and_browser_style_writes_remain_available(scoped_api_client):
    api = scoped_api_client
    body = {"id": "own_scope", "name": "Own scope", "project": "project-b"}
    assert api.client.post("/api/v1/styles", headers=api.headers["write_b"], json=body).json()["ok"]
    api.client.cookies.set("st_session", "parent-session")
    body["id"] = "browser_scope"
    assert api.client.post("/api/v1/styles", json=body).json()["ok"]


@pytest.mark.parametrize("credential", ["task_a", "read_a"])
def test_restricted_agent_cannot_mutate_styles_or_upload(scoped_api_client, credential):
    api = scoped_api_client
    headers = api.headers[credential]
    assert api.client.post("/api/v1/styles", headers=headers, json={
        "id": "denied", "project": "project-a",
    }).status_code == 403
    assert api.client.delete("/api/v1/styles/denied?project=project-a", headers=headers).status_code == 403
    assert api.client.post("/api/v1/projects/project-a/freezone/upload", headers=headers,
                           files={"file": ("marker.html", b"<html>marker</html>", "text/html")}).status_code == 403
    assert not (api.root / "project-a" / "output" / "freezone" / "_uploads").exists()
    assert not (api.root / "project-a" / "state" / "project_config.json").exists()


@pytest.mark.parametrize("endpoint,extra", [
    ("notifications", {"text": "scope marker"}),
    ("ui-events", {"turn_id": "turn", "event": {"type": "marker"}}),
])
@pytest.mark.parametrize("scope", [{"kind": "project", "id": "project-b"}, {"kind": "home"}])
def test_chat_mutations_cannot_escape_agent_scope(scoped_api_client, endpoint, extra, scope):
    api = scoped_api_client
    response = api.client.post(f"/api/v1/chat/{endpoint}", headers=api.headers["write_a"],
                               json={"scope": scope, **extra})
    assert response.status_code == 403, response.text


def test_chat_notification_same_project_reaches_expected_sink(scoped_api_client, monkeypatch):
    from novelvideo.api.routes import chat

    captured = {}

    def record(username, project, text, **kwargs):
        captured.update(project=project, **kwargs)
        return {"role": "assistant", "text": text}

    monkeypatch.setattr(chat.chat_service, "add_assistant_message", record)
    api = scoped_api_client
    response = api.client.post("/api/v1/chat/notifications", headers=api.headers["write_a"],
                               json={"scope": {"kind": "project", "id": "project-a"}, "text": "marker"})
    assert response.status_code == 200, response.text
    assert captured["project_state_dir"] == api.root / "project-a" / "state"


@pytest.mark.parametrize("endpoint", ["/api/v1/projects", "/api/v1/projects/summaries"])
def test_project_listing_does_not_widen_current_project_scope(scoped_api_client, endpoint):
    api = scoped_api_client
    result = api.client.get(endpoint, headers=api.headers["read_a"])
    assert result.status_code == 200
    assert [p["id"] for p in result.json()["data"]] == ["project-a"]
    api.client.cookies.set("st_session", "parent-session")
    assert {p["id"] for p in api.client.get(endpoint).json()["data"]} == {"project-a", "project-b"}


@pytest.mark.parametrize("credential", ["task_a", "read_a"])
def test_restricted_agent_cannot_change_gateway(scoped_api_client, credential, monkeypatch):
    from novelvideo.api.routes import model_gateway

    monkeypatch.setenv("ST_EDITION", "ce")
    monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)

    def unexpected_write(*args, **kwargs):
        pytest.fail("restricted credential reached gateway configuration")

    monkeypatch.setattr(model_gateway, "save_official_newapi_key", unexpected_write)
    response = scoped_api_client.client.post(
        "/api/v1/model-gateway/official/config",
        headers=scoped_api_client.headers[credential],
        json={"newApiApiKey": "synthetic"},
    )
    assert response.status_code == 403, response.text


def test_task_only_agent_can_submit_authorized_task(scoped_api_client, monkeypatch):
    from types import SimpleNamespace
    from novelvideo.api.routes import characters

    captured = []

    class Backend:
        async def enqueue_project_task(self, ctx, **kwargs):
            captured.append({"ctx": ctx, **kwargs})
            return SimpleNamespace(task_state=SimpleNamespace(task_id="synthetic-task"),
                                   backend="synthetic", queue="default")

    monkeypatch.setattr(characters, "get_task_backend", lambda: Backend())
    monkeypatch.setattr(characters, "has_imported_novel", lambda project_dir: True)
    api = scoped_api_client
    response = api.client.post("/api/v1/projects/project-a/characters/build",
                               headers=api.headers["task_a"], json={})
    assert response.status_code == 200, response.text
    assert len(captured) == 1
    assert captured[0]["ctx"].project_id == "project-a"
    assert api.client.post("/api/v1/projects/project-b/characters/build",
                           headers=api.headers["task_a"], json={}).status_code == 403
    assert len(captured) == 1


def test_all_http_mutations_declare_an_exact_agent_scope(scoped_api_client):
    from fastapi.routing import APIRoute, iter_route_contexts

    def scopes(dependant):
        required = getattr(dependant.call, "required_agent_scope", None)
        return ({required} if required else set()).union(*(scopes(d) for d in dependant.dependencies))

    unscoped = []
    checked = set()
    for route in iter_route_contexts(scoped_api_client.client.app.routes):
        if not isinstance(route.original_route, APIRoute) or not route.methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if route.path == "/api/v1/auth/logout":
            continue  # Recovery clears only the caller's browser session cookie.
        checked.add(route.path)
        if not scopes(route.dependant):
            unscoped.append(route.path)
    assert unscoped == []
    assert {
        "/api/v1/styles",
        "/api/v1/projects/{project}/freezone/upload",
        "/api/v1/projects/{project}/episodes/{episode_num}/verify/consistency",
    } <= checked
