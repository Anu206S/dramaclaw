"""A DramaClaw that authenticates per turn must not run on a stock Hermes.

The failure it prevents is the one that cost the most to find: a stock Hermes
accepts the ACP prompt, drops the `_meta` extension the credential travels in,
and the worker then refuses to egress. The OpenAI SDK wraps that refusal as a
connection error and retries three times, so the symptom appears fourteen
seconds later, names the network, and the gateway sees no request at all.

There is no legacy mode to fall back to. One existed and was worse than none:
it put the real key back on disk while the worker kept the placeholder and the
latch, so a "legacy" deployment carried the old design's exposure and the new
design's behaviour at the same time.
"""
from __future__ import annotations

import sys
import types

import pytest

from novelvideo.chat import hermes_fork_requirement as requirement


@pytest.fixture
def stock_hermes(monkeypatch):
    """A Hermes whose router drops `_meta`, which is what upstream does."""
    server = types.ModuleType("acp_adapter.server")
    server._recover_turn_meta = lambda kwargs: kwargs.get("_meta") or {}
    package = types.ModuleType("acp_adapter")
    package.server = server
    monkeypatch.setitem(sys.modules, "acp_adapter", package)
    monkeypatch.setitem(sys.modules, "acp_adapter.server", server)


@pytest.fixture
def forked_hermes(monkeypatch):
    server = types.ModuleType("acp_adapter.server")
    server._recover_turn_meta = lambda kwargs: (
        kwargs.get("_meta") or {k: v for k, v in kwargs.items() if "." in k})
    package = types.ModuleType("acp_adapter")
    package.server = server
    credential = types.ModuleType("agent.gateway_credential")
    credential.apply_to_headers = lambda h, u: False
    credential.refuse_foreign_endpoint = lambda u: None
    agent = types.ModuleType("agent")
    agent.gateway_credential = credential
    for name, module in (("acp_adapter", package), ("acp_adapter.server", server),
                         ("agent", agent), ("agent.gateway_credential", credential)):
        monkeypatch.setitem(sys.modules, name, module)


def test_a_stock_hermes_is_refused(stock_hermes):
    installed, detail = requirement.hermes_fork_is_installed()
    assert not installed
    assert "_meta" in detail


def test_the_fork_is_accepted(forked_hermes):
    installed, detail = requirement.hermes_fork_is_installed()
    assert installed, detail


def test_the_refusal_names_the_cause_and_the_fix(stock_hermes):
    with pytest.raises(requirement.HermesForkMissing) as caught:
        requirement.require_hermes_fork()
    message = str(caught.value)
    assert "_meta" in message, "the message must name what is actually missing"
    assert "HERMES_INSTALL_SPEC" in message, "and how to fix it"


def test_a_missing_hermes_is_refused_rather_than_assumed_present(monkeypatch):
    monkeypatch.setitem(sys.modules, "acp_adapter", None)
    installed, _ = requirement.hermes_fork_is_installed()
    assert not installed


def test_a_probe_that_raises_counts_as_a_mismatch(monkeypatch):
    """A fork half-installed, or broken, is not a fork."""
    server = types.ModuleType("acp_adapter.server")

    def explode(_kwargs):
        raise RuntimeError("half-installed")

    server._recover_turn_meta = explode
    package = types.ModuleType("acp_adapter")
    package.server = server
    monkeypatch.setitem(sys.modules, "acp_adapter", package)
    monkeypatch.setitem(sys.modules, "acp_adapter.server", server)

    installed, detail = requirement.hermes_fork_is_installed()
    assert not installed
    assert "RuntimeError" in detail
