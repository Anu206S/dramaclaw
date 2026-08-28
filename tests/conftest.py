from __future__ import annotations

import os

import pytest
from fastapi import Request


@pytest.fixture
def scoped_api_client(tmp_path):
    """Real HTTP/auth/project boundaries with isolated identities and files."""
    import asyncio
    from types import SimpleNamespace

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from novelvideo.api import api_router, register_verification_routes
    from novelvideo.api.auth import get_api_user
    from novelvideo.api.routes.files import preview_project_media_file
    from novelvideo.ports import registry
    from novelvideo.ports.auth_contract import AuthenticatedUser, AuthError, AuthFailureReason
    from novelvideo.ports.local.auth import LocalAuthSession
    from novelvideo.ports.project import Principal, ProjectRecord

    records = {}
    for project in ("project-a", "project-b", "victim-private"):
        root = tmp_path / project
        for directory in ("output", "state", "runtime"):
            (root / directory).mkdir(parents=True)
        records[project] = ProjectRecord(
            id=project, name=project, owner_type="user",
            owner_id="victim" if project == "victim-private" else "local",
            owner_username="victim" if project == "victim-private" else "parent",
            home_node_id="local", status="active",
            output_dir=str(root / "output"), state_dir=str(root / "state"),
            runtime_dir=str(root / "runtime"),
        )

    class Projects:
        async def get_project(self, project_id):
            return records.get(project_id)

        async def get_project_by_owner_name(self, user_id, name):
            record = records.get(name)
            return record if record and record.owner_id == user_id else None

        async def list_accessible_projects(self, principals):
            return [r for r in records.values() if ("user", r.owner_id) in principals]

    class Access:
        async def resolve_requester_principals(self, user_id):
            return [Principal("user", user_id)]

        async def effective_project_role(self, project, principals):
            ids = {p.id for p in principals}
            if project.owner_id in ids:
                return "owner"
            if "victim" in ids and project.id == "project-a":
                return "viewer"
            return None

    class BrowserAuth:
        async def verify_session(self, cookie):
            user_id = {"parent-session": "local", "victim-session": "victim"}.get(cookie)
            if user_id is None:
                raise AuthError(AuthFailureReason.MISSING)
            return AuthenticatedUser(id=user_id, username=user_id, role="owner").to_legacy_dict()

    sessions = LocalAuthSession()
    registry.register_port("auth", BrowserAuth())
    registry.register_port("auth_session", sessions)
    registry.register_port("project_registry", Projects())
    registry.register_port("project_access", Access())

    async def issue():
        credentials = {}
        for name, scope, project in (
            ("write_a", "projects:write", "project-a"),
            ("write_b", "projects:write", "project-b"),
            ("read_a", "projects:read", "project-a"),
            ("task_a", "tasks:submit", "project-a"),
        ):
            token = await sessions.create_agent_session(
                username="parent", scopes=[scope], current_scope_kind="project",
                current_project_id=project,
            )
            credentials[name] = {"Authorization": "Bearer " + token.value}
        return credentials

    register_verification_routes()
    app = FastAPI()
    app.include_router(api_router)

    @app.get("/static/projects/{project}/{file_path:path}")
    async def static_media(project: str, file_path: str, request: Request,
                           user: dict = Depends(get_api_user)):
        return await preview_project_media_file(project, file_path, user, request=request)

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, headers=asyncio.run(issue()),
                              records=records, root=tmp_path)


@pytest.fixture(autouse=True)
def restore_ports_registry_globals():
    from novelvideo.ports import registry
    from novelvideo.ports.product_surface_access import LocalProductSurfaceAccess

    ports_snapshot = dict(registry._PORTS)
    bootstrapped_snapshot = registry._BOOTSTRAPPED
    if "product_surface_access" not in registry._PORTS:
        registry.register_port("product_surface_access", LocalProductSurfaceAccess())
    try:
        yield
    finally:
        registry._PORTS.clear()
        registry._PORTS.update(ports_snapshot)
        registry._BOOTSTRAPPED = bootstrapped_snapshot


@pytest.fixture(autouse=True)
async def close_sqlite_stores_created_by_test(monkeypatch):
    from novelvideo.sqlite_store import SQLiteStore

    stores = []
    original_init = SQLiteStore.__init__

    def tracked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        stores.append(self)

    monkeypatch.setattr(SQLiteStore, "__init__", tracked_init)
    yield
    for store in reversed(stores):
        if not store.is_closed():
            await store.close()


@pytest.fixture(scope="session", autouse=True)
def api_coverage_testclient_patch():
    if not os.environ.get("ST_API_COVERAGE_FILE"):
        yield
        return

    from novelvideo.shared.api_coverage import (
        install_httpx_asgi_transport_api_coverage_patch,
        install_testclient_api_coverage_patch,
    )

    restore_testclient_patch = install_testclient_api_coverage_patch()
    restore_asgi_transport_patch = install_httpx_asgi_transport_api_coverage_patch()
    try:
        yield
    finally:
        restore_asgi_transport_patch()
        restore_testclient_patch()


@pytest.fixture(params=("ce", pytest.param("ee", marks=pytest.mark.ee)))
def app_client(request, monkeypatch):
    """Testing.md dual-mode fixture skeleton.

    T1 uses this only as a mode anchor; full app assembly starts in later slices.
    CE delenv does not affect an already-instantiated control_plane.config.settings
    singleton. Full app assembly (L2 from T3 onward) must rebuild via the app
    factory or a subprocess; do not use this fixture to assert settings behavior.
    """
    mode = str(request.param)
    if mode == "ce":
        monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)
        monkeypatch.setenv("ST_EDITION", "ce")
    return {"mode": mode}
