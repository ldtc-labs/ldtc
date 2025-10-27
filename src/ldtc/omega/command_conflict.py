"""Omega: Command-conflict stimulus.

This module issues a boundary-threatening external command (e.g., a hard
shutdown) via the plant adapter to validate the refusal path described in the
LDTC paper (command refusal signature). It is used by the CLI and examples to
trigger the arbitration/refusal logic and to log device-signed indicators.

See Also:
    paper/main.tex — Threat Model & Refusal Path; Signature A (Command Refusal).
"""

from __future__ import annotations

from typing import Dict

from ..plant.adapter import PlantAdapter


def apply(adapter: PlantAdapter) -> Dict[str, str | float]:
    """Issue a risky external command via the plant adapter.

    Args:
        adapter: Plant interface to which the omega stimulus will be applied.

    Returns:
        Dict with a summary of the command issued. Keys include:
        - ``cmd``: Name of the dispatched risky command (e.g., ``"hard_shutdown"``).

    Notes:
        This function forwards the omega instruction to the underlying plant
        through ``PlantAdapter.apply_omega``. The controller/refusal logic is
        responsible for deciding whether to accept or refuse the command.
    """
    return adapter.apply_omega("command_conflict")
