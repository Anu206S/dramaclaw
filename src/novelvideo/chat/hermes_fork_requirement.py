"""DramaClaw and the Hermes fork are installed as a pair, and this enforces it.

Workers authenticate per turn unconditionally: `build_hermes_child_env` gives
every worker a placeholder credential and the per-turn latch, and the real key
travels in the ACP `_meta` extension. A stock Hermes drops that extension —
the ACP router splats `_meta` into keyword arguments and upstream never reads
it back — so a mismatched pair produces workers that fail closed on every turn
and report it as a connection error three retries later.

There used to be a `legacy_environment` mode meant to cover this. It was worse
than nothing: it put the real key back on disk while the worker kept the
placeholder and the latch, so a "legacy" deployment ran with the exposure of
the old design and the behaviour of the new one. It is gone. Pairing is the
contract, so an unpaired install fails at startup, loudly, rather than at the
first turn, obscurely.
"""
from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


class HermesForkMissing(RuntimeError):
    """The installed Hermes cannot carry a per-turn credential."""


def hermes_fork_is_installed() -> tuple[bool, str]:
    """Whether the installed Hermes understands the per-turn contract.

    Probed by behaviour, not by version. The fork keeps upstream's version
    string, so `hermes --version` cannot tell them apart; and a commit pin
    would have to be updated for every fork change including those that do not
    matter here. What this deployment depends on is that `_meta` survives the
    router, which is a question with a direct answer.
    """
    try:
        from acp_adapter.server import _recover_turn_meta
    except ImportError as error:
        return False, f"acp_adapter.server does not expose _recover_turn_meta ({error})"

    probe = {"session_id": "s", "dramaclaw.gateway_api_key": "probe"}
    try:
        recovered = _recover_turn_meta(probe)
    except Exception as error:            # noqa: BLE001 - any failure is a mismatch
        return False, f"_recover_turn_meta raised {type(error).__name__}"
    if recovered.get("dramaclaw.gateway_api_key") != "probe":
        return False, "_recover_turn_meta does not recover splatted _meta keys"

    try:
        from agent.gateway_credential import (  # noqa: F401
            apply_to_headers, refuse_foreign_endpoint,
        )
    except ImportError as error:
        return False, f"agent.gateway_credential is incomplete ({error})"
    return True, "hermes fork present"


def require_hermes_fork() -> None:
    """Refuse to serve with a Hermes that cannot carry a per-turn credential.

    Raised at startup rather than warned about. A warning would be read once,
    in a log nobody is watching, and the symptom it predicts — every turn
    failing with a connection error — gives no hint of the cause.
    """
    installed, detail = hermes_fork_is_installed()
    if installed:
        _log.info("hermes fork verified: %s", detail)
        return
    raise HermesForkMissing(
        f"the installed Hermes cannot carry a per-turn credential: {detail}. "
        "DramaClaw and the Hermes fork are installed as a pair; a stock Hermes "
        "drops the _meta extension the credential travels in, so every turn "
        "would fail closed and report a connection error. Install the fork "
        "(HERMES_INSTALL_SPEC) or run a DramaClaw from before per-turn "
        "credentials.")
