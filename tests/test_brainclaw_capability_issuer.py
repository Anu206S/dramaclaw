"""The DramaClaw side of the capability: minting and ACP injection."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from novelvideo import brainclaw_control_capability as cap

SIGNING_KEY = b"c" * 32
GROUPING_KEY = b"g" * 32
KEY_ID = "dc-capability-test"


@pytest.fixture
def issuer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> cap.ControlCapabilityIssuer:
    keyring = tmp_path / "capability-keyring.json"
    keyring.write_text(json.dumps({
        "schema_version": "brainclaw.control-context-keyring/v1",
        "keys": {KEY_ID: base64.b64encode(SIGNING_KEY).decode()},
    }))
    keyring.chmod(0o600)
    grouping = tmp_path / "grouping.key"
    grouping.write_bytes(GROUPING_KEY)
    grouping.chmod(0o600)
    monkeypatch.setenv("BRAINCLAW_CAPABILITY_KEYRING_FILE", str(keyring))
    monkeypatch.setenv("BRAINCLAW_CAPABILITY_SIGNING_KEY_ID", KEY_ID)
    monkeypatch.setenv("BRAINCLAW_CONTROL_CONTEXT_GROUPING_KEY_FILE", str(grouping))
    monkeypatch.setenv("BRAINCLAW_CONTROL_CONTEXT_GROUPING_KEY_EPOCH", "2")
    cap.reset_control_capability_issuer()
    built = cap.control_capability_issuer()
    assert built is not None
    yield built
    cap.reset_control_capability_issuer()


def _claims(header: str) -> dict:
    payload = header.split(".")[2]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def test_a_minted_capability_carries_only_pseudonymised_identity(issuer) -> None:
    header = issuer.issue(trajectory_id="tr-77", project_id="proj-4", turn_id="turn-a")
    claims = _claims(header)
    # Raw identifiers must never leave this process.
    assert "tr-77" not in header and "proj-4" not in header
    assert claims["trajectory_group_id"].startswith("hmac-sha256:")
    assert claims["project_group_id"] != claims["trajectory_group_id"]
    assert claims["grouping_key_epoch"] == 2
    assert claims["audience"] == cap.AUDIENCE
    assert claims["issuer"] == cap.ISSUER
    assert claims["turn_id"] == "turn-a"


def test_the_same_episode_is_stable_and_projects_group_across_episodes(issuer) -> None:
    """The three statistical layers have to survive minting."""
    a1 = _claims(issuer.issue(trajectory_id="tr-1", project_id="proj-x", turn_id="t1"))
    a2 = _claims(issuer.issue(trajectory_id="tr-1", project_id="proj-x", turn_id="t2"))
    b = _claims(issuer.issue(trajectory_id="tr-2", project_id="proj-x", turn_id="t3"))
    c = _claims(issuer.issue(trajectory_id="tr-3", project_id="proj-y", turn_id="t4"))

    assert a1["trajectory_group_id"] == a2["trajectory_group_id"], "one trajectory, one id"
    assert b["trajectory_group_id"] != a1["trajectory_group_id"], "different episodes differ"
    assert b["project_group_id"] == a1["project_group_id"], "same project groups them"
    assert c["project_group_id"] != a1["project_group_id"], "different projects separate"


def test_every_capability_is_unique_even_for_one_episode(issuer) -> None:
    """The nonce is what stops two turns producing an identical bearer token."""
    headers = {issuer.issue(trajectory_id="tr-1", project_id="proj-x", turn_id=f"t{i}")
               for i in range(20)}
    assert len(headers) == 20


def test_the_ttl_is_bounded(issuer) -> None:
    claims = _claims(issuer.issue(trajectory_id="tr-1", project_id="proj-x", turn_id="t"))
    lifetime = claims["expires_at"] - claims["issued_at"]
    assert 0 < lifetime <= cap.MAX_TTL_SECONDS
    assert lifetime == cap.DEFAULT_TTL_SECONDS


def test_one_secret_may_not_serve_both_roles(tmp_path: Path) -> None:
    """Sharing them would tie trajectory identity to signing-key rotation."""
    keyring = tmp_path / "k.json"
    keyring.write_text(json.dumps({
        "schema_version": "brainclaw.control-context-keyring/v1",
        "keys": {KEY_ID: base64.b64encode(SIGNING_KEY).decode()},
    }))
    keyring.chmod(0o600)
    grouping = tmp_path / "g.key"
    grouping.write_bytes(SIGNING_KEY)
    grouping.chmod(0o600)
    with pytest.raises(ValueError):
        cap.ControlCapabilityIssuer(
            keyring_path=keyring, signing_key_id=KEY_ID,
            grouping_key_path=grouping, grouping_key_epoch=1,
        )


def test_an_unconfigured_deployment_issues_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BRAINCLAW_CAPABILITY_KEYRING_FILE", "BRAINCLAW_CAPABILITY_SIGNING_KEY_ID",
                 "BRAINCLAW_CONTROL_CONTEXT_GROUPING_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    cap.reset_control_capability_issuer()
    assert cap.control_capability_issuer() is None
    cap.reset_control_capability_issuer()


# --- ACP injection --------------------------------------------------------

def test_the_turn_helper_never_raises_into_the_conversation(monkeypatch) -> None:
    """Attestation is observability; it must not be able to fail a turn."""
    from novelvideo.chat import hermes_sdk

    # No identity at all.
    assert hermes_sdk._issue_turn_capability(
        trajectory_id=None, project_id=None, turn_id="t") is None
    assert hermes_sdk._issue_turn_capability(
        trajectory_id="ep", project_id=None, turn_id="t") is None

    # A broken issuer.
    def explode() -> None:
        raise RuntimeError("keyring on fire")

    monkeypatch.setattr(
        "novelvideo.brainclaw_control_capability.control_capability_issuer", explode
    )
    assert hermes_sdk._issue_turn_capability(
        trajectory_id="ep", project_id="proj", turn_id="t") is None


def test_the_helper_mints_whenever_an_identity_and_issuer_exist(issuer) -> None:
    """No runtime gate here on purpose — see the startup check instead."""
    from novelvideo.chat import hermes_sdk

    header = hermes_sdk._issue_turn_capability(
        trajectory_id="tr-9", project_id="proj-9", turn_id="turn-9")
    assert header is not None
    assert _claims(header)["turn_id"] == "turn-9"
