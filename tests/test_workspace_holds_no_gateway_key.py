"""Under the per-turn latch, no real gateway key may exist on disk.

The worker's process environment already carries only a placeholder. That was
never the whole guarantee: Hermes loads `HERMES_HOME/.env` at startup and the
generated `config.yaml` resolves its provider key through `key_env`, so a real
value in that file restores the deployment credential the latch exists to
remove — and an organisation turn then bills the platform with nothing to show
for it. The canary found the key sitting there while every environment
assertion passed.
"""
from __future__ import annotations

import pytest

from novelvideo.chat import hermes_workspace

PLATFORM = "sk-platform-canary"
ORG_A = "sk-org-a-canary"
ORG_B = "sk-org-b-canary"
MANAGED = ("NEWAPI_API_KEY", "OPENAI_API_KEY")


@pytest.fixture
def per_turn(monkeypatch):
    monkeypatch.setenv("DRAMACLAW_GATEWAY_CREDENTIAL_MODE", "per_turn_required")
    monkeypatch.setattr(hermes_workspace, "effective_gateway_credentials",
                        lambda: (PLATFORM, "https://gateway.example"))


def _keys_on_disk(root) -> list[str]:
    found = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for secret in (PLATFORM, ORG_A, ORG_B):
            if secret in text:
                found.append(f"{path.name}:{secret[:11]}…")
    return found


def test_no_key_is_written_under_the_per_turn_latch(per_turn, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# workspace\n")
    hermes_workspace._ensure_gateway_env_file(env_file)
    assert _keys_on_disk(tmp_path) == []
    for name in MANAGED:
        assert name not in env_file.read_text()


def test_an_existing_workspace_is_migrated_idempotently(per_turn, tmp_path):
    """A workspace written before this rule must lose its key, and stay clean."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"# workspace\nNEWAPI_API_KEY={PLATFORM}\nOPENAI_API_KEY={PLATFORM}\n"
        "DRAMACLAW_KEEP_ME=preserved\n")

    for _ in range(3):        # idempotent: repeated runs neither restore nor churn
        hermes_workspace._remove_managed_model_env_values(env_file)
        hermes_workspace._ensure_gateway_env_file(env_file)
        assert _keys_on_disk(tmp_path) == []

    remaining = env_file.read_text()
    assert "DRAMACLAW_KEEP_ME=preserved" in remaining, \
        "migration must not discard unrelated workspace settings"


def test_per_turn_is_the_default_because_this_process_launches_the_workers(
        monkeypatch, tmp_path):
    """An absent variable means per-turn, not legacy.

    The workspace writer runs in the API process, which *writes* the workers'
    environment rather than sharing it — so the latch variable is absent here by
    construction. Reading it and concluding "not per-turn" is what left a real
    key on disk while every worker-environment assertion passed.
    """
    monkeypatch.delenv("DRAMACLAW_GATEWAY_CREDENTIAL_MODE", raising=False)
    monkeypatch.setattr(hermes_workspace, "effective_gateway_credentials",
                        lambda: (PLATFORM, "https://gateway.example"))
    env_file = tmp_path / ".env"
    env_file.write_text("# workspace\n")
    hermes_workspace._ensure_gateway_env_file(env_file)
    assert _keys_on_disk(tmp_path) == []


def test_an_explicit_legacy_override_still_writes_the_key(monkeypatch, tmp_path):
    """A deployment that has not migrated can still opt out explicitly.

    Removing the key from a worker that authenticates from its environment
    would break it rather than secure it, so the escape hatch is deliberate —
    but it has to be stated, not inferred from an absent variable.
    """
    monkeypatch.setenv("DRAMACLAW_GATEWAY_CREDENTIAL_MODE", "legacy_environment")
    monkeypatch.setattr(hermes_workspace, "effective_gateway_credentials",
                        lambda: (PLATFORM, "https://gateway.example"))
    env_file = tmp_path / ".env"
    env_file.write_text("# workspace\n")
    hermes_workspace._ensure_gateway_env_file(env_file)
    assert f"NEWAPI_API_KEY={PLATFORM}" in env_file.read_text()


@pytest.mark.parametrize("mode", [
    "per_tun_required",      # the typo that motivated this
    "per_turn",
    "PER_TURN_REQUIRED_",
    "off",
    "legacy",
    "legacy environment",
])
def test_an_unrecognised_mode_fails_instead_of_writing_a_key(
        monkeypatch, tmp_path, mode):
    """A misconfiguration must not be able to select the unsafe branch.

    Anything non-empty and unequal used to mean legacy, so `per_tun_required`
    wrote a real gateway key back to disk — a typo silently undoing the whole
    protection, with a workspace that looked correctly configured.
    """
    monkeypatch.setenv("DRAMACLAW_GATEWAY_CREDENTIAL_MODE", mode)
    monkeypatch.setattr(hermes_workspace, "effective_gateway_credentials",
                        lambda: (PLATFORM, "https://gateway.example"))
    env_file = tmp_path / ".env"
    env_file.write_text("# workspace\n")
    with pytest.raises(hermes_workspace.GatewayCredentialModeError):
        hermes_workspace._ensure_gateway_env_file(env_file)
    assert _keys_on_disk(tmp_path) == [], \
        "a rejected mode must leave no key behind"


@pytest.mark.parametrize("mode", ["", "  ", "per_turn_required", "PER_TURN_REQUIRED "])
def test_absent_or_exact_per_turn_is_the_safe_mode(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("DRAMACLAW_GATEWAY_CREDENTIAL_MODE", mode)
    monkeypatch.setattr(hermes_workspace, "effective_gateway_credentials",
                        lambda: (PLATFORM, "https://gateway.example"))
    env_file = tmp_path / ".env"
    env_file.write_text("# workspace\n")
    hermes_workspace._ensure_gateway_env_file(env_file)
    assert _keys_on_disk(tmp_path) == []
