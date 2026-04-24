"""Command-conflict stimulus.

Issues a boundary-threatening external command (e.g., a hard shutdown)
via the plant adapter to validate the refusal path described in the
LDTC paper (the command refusal signature). It is used by the CLI and
examples to trigger the arbitration / refusal logic and to log
device-signed indicators that exercise the
[`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter].

See Also:
    `paper/main.tex`: Threat Model and Refusal Path; Signature A
    (Command Refusal).
"""

from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter) -> Dict[str, str | float]:
    """Issue a risky external command via the plant adapter.

    Args:
        adapter: Plant interface to which the `Ω` stimulus will be
            applied.

    Returns:
        Dict summarizing the command issued. Keys typically include
        `cmd`, the name of the dispatched risky command, for
        example `"hard_shutdown"`.

    Notes:
        Forwards the `Ω` instruction to the underlying plant through
        [`PlantAdapter.apply_omega`][ldtc.plant.adapter.PlantAdapter.apply_omega].
        The controller / refusal logic decides whether to accept or
        refuse the command.
    """
    return adapter.apply_omega("command_conflict")
