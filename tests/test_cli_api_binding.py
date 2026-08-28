"""CE binds locally by default; explicit/container and EE binds stay available."""

import pytest
from typer.testing import CliRunner

from novelvideo.cli import app


@pytest.mark.parametrize("edition,dsn,host", [
    ("ce", "", "127.0.0.1"),
    ("ee", "postgresql://synthetic.invalid/control", "0.0.0.0"),
])
def test_api_default_host_respects_auth_mode(monkeypatch, edition, dsn, host):
    calls = []
    monkeypatch.setenv("ST_EDITION", edition)
    monkeypatch.setenv("ST_CONTROL_PLANE_DSN", dsn)
    monkeypatch.delenv("NOVELVIDEO_API_HOST", raising=False)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(app, ["api"])
    assert result.exit_code == 0, result.output
    assert calls[0]["host"] == host


@pytest.mark.parametrize("arguments,configured_host", [
    (["api", "--host", "0.0.0.0"], ""),
    (["api"], "0.0.0.0"),
])
def test_ce_explicit_remote_bind_warns_without_breaking_container_start(monkeypatch, arguments, configured_host):
    calls = []
    monkeypatch.setenv("ST_EDITION", "ce")
    monkeypatch.setenv("ST_CONTROL_PLANE_DSN", "")
    monkeypatch.setenv("NOVELVIDEO_API_HOST", configured_host)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert calls[0]["host"] == "0.0.0.0"
    assert "CE has no login" in result.output
