from dataclasses import replace
from types import SimpleNamespace

import pytest

from novelvideo.ports.project import ProjectRecord
from novelvideo.project_context import ProjectContext


def _record(tmp_path, *, status: str = "active") -> ProjectRecord:
    return ProjectRecord(
        id="01PROJECT",
        owner_type="user",
        owner_id="local",
        owner_username="alice",
        name="demo",
        home_node_id="local",
        output_dir=str(tmp_path / "output" / "alice" / "demo"),
        state_dir=str(tmp_path / "state" / "alice" / "demo"),
        runtime_dir=str(tmp_path / "runtime" / "alice" / "demo"),
        status=status,
    )


def _context(record: ProjectRecord) -> ProjectContext:
    return ProjectContext(
        project_id=record.id,
        project_name=record.name,
        owner_type=record.owner_type,
        owner_id=record.owner_id,
        owner_username=record.owner_username,
        requester_user_id="local",
        requester_username="alice",
        requester_principals=(("user", "local"),),
        effective_role="owner",
        home_node_id="local",
        output_dir=record.output_dir,
        state_dir=record.state_dir,
        runtime_dir=record.runtime_dir,
        is_home_node=True,
    )


@pytest.mark.asyncio
async def test_create_project_does_not_reuse_orphaned_same_name_data(monkeypatch, tmp_path):
    from novelvideo.api.routes import projects

    record = _record(tmp_path)
    old_canvas = tmp_path / "state" / "alice" / "demo" / "freezone" / "canvases"
    old_canvas.mkdir(parents=True)
    (old_canvas / "default.json").write_text('{"old": true}', encoding="utf-8")
    (tmp_path / "state" / "alice" / "demo" / "data.db").write_bytes(b"old workflow db")
    (tmp_path / "output" / "alice" / "demo").mkdir(parents=True)
    (tmp_path / "runtime" / "alice" / "demo").mkdir(parents=True)

    class Registry:
        async def create_project(self, **_kwargs):
            return record

        async def delete_uncommitted_project(self, _project_id):
            raise AssertionError("successful creation must not be compensated")

    async def fake_user_id(_user):
        return "local"

    def ensure_dirs(*, output_dir, state_dir, runtime_dir):
        for path in (output_dir, state_dir, runtime_dir):
            projects.Path(path).mkdir(parents=True, exist_ok=True)

    def save_config(state_dir, *, config):
        projects.Path(state_dir, "project_config.json").write_text(
            str(config),
            encoding="utf-8",
        )

    monkeypatch.setattr(projects, "validate_project_name", lambda _name: None)
    monkeypatch.setattr(projects, "user_id_from_api_user", fake_user_id)
    monkeypatch.setattr(projects, "get_project_registry", lambda: Registry())
    monkeypatch.setattr(projects, "ensure_project_dirs_at_paths", ensure_dirs)
    monkeypatch.setattr(projects, "save_project_config_in_state_dir", save_config)
    monkeypatch.setattr(
        projects,
        "embedding_model_binding_for_new_project",
        lambda: SimpleNamespace(internal_model="embed", dimensions=1024),
    )

    result = await projects.create_project(
        projects.ProjectCreate(name="demo"),
        user={"id": "local", "username": "alice"},
    )

    assert result["ok"] is True
    assert not projects.Path(record.state_dir, "freezone").exists()
    assert not projects.Path(record.state_dir, "data.db").exists()
    assert projects.Path(record.state_dir, "project_config.json").exists()
    assert not list(projects.Path(record.state_dir).parent.glob(".demo.orphaned-*"))


@pytest.mark.asyncio
async def test_purge_detaches_files_before_releasing_project_name(monkeypatch, tmp_path):
    from novelvideo.api.routes import projects

    record = _record(tmp_path, status="deleted")
    for raw_path in (record.output_dir, record.state_dir, record.runtime_dir):
        path = projects.Path(raw_path)
        path.mkdir(parents=True)
        (path / "retained.txt").write_text("old", encoding="utf-8")
    ctx = _context(record)
    calls: list[str] = []

    class Registry:
        async def get_project(self, _project_id):
            return record

        async def mark_project_purged(self, _project_id):
            assert all(
                not projects.Path(path).exists()
                for path in (record.output_dir, record.state_dir, record.runtime_dir)
            )
            calls.append("purged")
            return replace(record, purged_at="2026-07-31T00:00:00+00:00")

        async def delete_project_home(self, _project_id):
            calls.append("home")

    async def resolve_context(**_kwargs):
        return ctx

    async def emit_audit(**_kwargs):
        calls.append("audit")

    monkeypatch.setattr(projects, "resolve_project_context", resolve_context)
    monkeypatch.setattr(projects, "get_project_registry", lambda: Registry())
    monkeypatch.setattr(projects, "emit_project_audit", emit_audit)

    result = await projects.purge_project("01PROJECT", user={"username": "alice"})

    assert result["ok"] is True
    assert calls == ["purged", "home", "audit"]
    for raw_path in (record.output_dir, record.state_dir, record.runtime_dir):
        path = projects.Path(raw_path)
        assert not path.exists()
        assert not list(path.parent.glob(".demo.purging-*"))


@pytest.mark.asyncio
async def test_purge_restores_files_when_registry_purge_fails(monkeypatch, tmp_path):
    from novelvideo.api.routes import projects

    record = _record(tmp_path, status="deleted")
    for raw_path in (record.output_dir, record.state_dir, record.runtime_dir):
        path = projects.Path(raw_path)
        path.mkdir(parents=True)
        (path / "retained.txt").write_text("old", encoding="utf-8")
    ctx = _context(record)

    class Registry:
        async def get_project(self, _project_id):
            return record

        async def mark_project_purged(self, _project_id):
            raise RuntimeError("registry unavailable")

    async def resolve_context(**_kwargs):
        return ctx

    monkeypatch.setattr(projects, "resolve_project_context", resolve_context)
    monkeypatch.setattr(projects, "get_project_registry", lambda: Registry())

    with pytest.raises(RuntimeError, match="registry unavailable"):
        await projects.purge_project("01PROJECT", user={"username": "alice"})

    for raw_path in (record.output_dir, record.state_dir, record.runtime_dir):
        path = projects.Path(raw_path)
        assert (path / "retained.txt").read_text(encoding="utf-8") == "old"
        assert not list(path.parent.glob(".demo.purging-*"))
