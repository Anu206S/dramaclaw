"""BrainClaw's additions must not change what non-BrainClaw deployments do.

The risk is not Static routing. It is that three of these changes are not
opt-in features at all:

- every worker DramaClaw launches now carries the per-turn credential latch,
  whether or not BrainClaw is configured;
- a latched worker refuses any host but its configured gateway;
- the workspace no longer writes the gateway key to disk.

A deployment that points Hermes at its own OpenAI-compatible endpoint, or runs
its own NewAPI, never asked for any of that. These tests state what such a
deployment is entitled to: its turns still authenticate, still reach its own
endpoint, and never need a capability it has no key to mint.
"""
from __future__ import annotations

import pytest

from novelvideo.chat import hermes_egress, hermes_workspace
from novelvideo.chat.hermes_pool import _resolve_turn_gateway_api_key

BYO_ENDPOINT = "https://llm.customer.example"
BYO_KEY = "sk-customer-own-key"


@pytest.fixture
def byo_gateway(monkeypatch):
    """A customer's own OpenAI-compatible endpoint, no BrainClaw anywhere."""
    monkeypatch.setattr(hermes_workspace, "effective_gateway_credentials",
                        lambda: (BYO_KEY, BYO_ENDPOINT))
    monkeypatch.setattr("novelvideo.chat.hermes_pool.effective_gateway_credentials",
                        lambda: (BYO_KEY, BYO_ENDPOINT))
    for name in ("BRAINCLAW_CAPABILITY_KEYRING_FILE",
                 "BRAINCLAW_CAPABILITY_SIGNING_KEY_ID",
                 "BRAINCLAW_CONTROL_CONTEXT_GROUPING_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)


# -- 1. BrainClaw not configured at all -------------------------------------

def test_a_platform_turn_still_authenticates_without_any_brainclaw_key(byo_gateway):
    """No authorization means the configured key, exactly as before.

    This is the path every ordinary turn takes on a deployment that has never
    heard of BrainClaw. If it returned None the worker would refuse the turn,
    because the latch is on for every worker now.
    """
    assert _resolve_turn_gateway_api_key(None) == BYO_KEY


def test_the_worker_environment_is_self_consistent_for_a_byo_deployment(byo_gateway):
    """The placeholder and the latch must arrive together.

    Either alone is a broken worker: a latch without a per-turn key refuses
    every turn, and a placeholder without a latch would authenticate with a
    string that is not a credential.
    """
    from tests.test_hermes_evidence_identity_passthrough import _build_child_environment

    environment = _build_child_environment(hermes_egress, BYO_KEY)
    assert environment["NEWAPI_API_KEY"] == hermes_egress.PER_TURN_CREDENTIAL_PLACEHOLDER
    assert environment[hermes_egress.GATEWAY_CREDENTIAL_MODE_ENV] == (
        hermes_egress.PER_TURN_CREDENTIAL_MODE)


def test_a_capability_is_not_required_to_take_a_turn(byo_gateway):
    """A deployment with no capability key must not be forced to mint one."""
    from novelvideo.chat.hermes_sdk import _issue_turn_capability

    capability = _issue_turn_capability(
        trajectory_id="tr-1", project_id="proj-1", turn_id="turn-1")
    assert capability is None, "no key configured means no capability, not an error"


def test_an_unconfigured_issuer_is_not_counted_as_a_failure(byo_gateway):
    """Otherwise every ordinary deployment reports a permanent failure."""
    from novelvideo.chat import evidence_metrics

    evidence_metrics.reset_for_test()
    from novelvideo.chat.hermes_sdk import _issue_turn_capability

    _issue_turn_capability(trajectory_id="tr-1", project_id="proj-1", turn_id="t")
    assert evidence_metrics.halting_counts() == {}
    evidence_metrics.reset_for_test()


# -- 2. the customer's own endpoint is reachable ----------------------------

def test_a_turn_for_a_different_gateway_is_refused_not_silently_retargeted(byo_gateway):
    """Cross-tenant safety still applies on a BYO deployment."""
    from novelvideo.chat.hermes_pool import GatewayOriginMismatch
    from novelvideo.ports.model_credentials import CredentialReference, RequestCredential
    from novelvideo.chat.hermes_egress import HermesTurnAuthorization
    from novelvideo.egress_context import TrustedEgressContext
    from novelvideo.ports.authz import BillingPrincipal

    reference = CredentialReference(source="organization", credential_id="c",
                                    key_version=1, org_id="org-1")
    context = TrustedEgressContext(
        envelope_id="e", project_id="p", task_type="chat", requester_user_id="u",
        root_task_id="r", admission_id="a", admitted_at="2026-08-19T00:00:00Z",
        membership_id="m", authz_version=1,
        billing_principal=BillingPrincipal(kind="organization", id="org-1"),
        credential=reference)
    elsewhere = HermesTurnAuthorization.for_test(
        context=context,
        credential=RequestCredential(reference=reference, api_key="sk-other",
                                     base_url="https://somewhere.else.example"))
    with pytest.raises(GatewayOriginMismatch):
        _resolve_turn_gateway_api_key(elsewhere)


# -- 3. the workspace change must not strand a legacy deployment ------------

def test_a_legacy_deployment_can_still_keep_its_key_on_disk(monkeypatch, tmp_path):
    """The opt-out exists for deployments that authenticate from the workspace.

    Removing the key there would break such a worker rather than secure it, so
    the escape hatch is deliberate — but it must be stated, never inferred.
    """
    monkeypatch.setenv("DRAMACLAW_GATEWAY_CREDENTIAL_MODE", "legacy_environment")
    monkeypatch.setattr(hermes_workspace, "effective_gateway_credentials",
                        lambda: (BYO_KEY, BYO_ENDPOINT))
    env_file = tmp_path / ".env"
    env_file.write_text("# workspace\n")
    hermes_workspace._ensure_gateway_env_file(env_file)
    assert f"NEWAPI_API_KEY={BYO_KEY}" in env_file.read_text()
