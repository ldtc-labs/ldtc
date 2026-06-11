"""Replay-controller adversarial member.

Implements the first member of the adversarial gaming battery: the
controller is replaced by a tape. A healthy closed-loop run of the same
plant is recorded first, and the measured run then replays that recorded
actuation trace tick by tick instead of computing actions from the
current state. The actuators move exactly as they did under genuine
control, so the activity *looks* like control, but it carries no
closed-loop dependence on the system's present state. The harness must
not certify such a system: the designed outcome is an `NC1` failure
(`M` low) on a run that remains valid.

Unlike the other `Ω` members, this is a controller swap rather than a
plant stimulus, so it provides a recorder and a replayer instead of an
`apply` function; the CLI handler orchestrates the two phases.

See Also:
    `paper/main.tex`: adversarial gaming battery.
"""

from __future__ import annotations

from typing import List, Protocol

from ..arbiter.policy import ControlAction, ControllerPolicy
from ..plant.models import Action


class _AdapterLike(Protocol):
    """Minimal adapter surface the recorder needs (read + actuate)."""

    def read_state(self) -> dict:
        """Return the latest plant state as a dict of named floats."""
        ...

    def write_actuators(self, action: Action) -> None:
        """Send actuator commands to the plant."""
        ...


def record_tape(adapter: _AdapterLike, policy: ControllerPolicy, ticks: int) -> List[ControlAction]:
    """Record an actuation tape from a healthy closed-loop run.

    Drives `adapter` with `policy` for `ticks` steps (the recording run)
    and returns the sequence of computed control actions. The recording
    run is a throwaway plant instance: only the tape survives.

    Args:
        adapter: Fresh plant adapter to drive (same profile as the
            measured run, so the tape statistics match a healthy run of
            the same system).
        policy: Controller used for the closed-loop recording.
        ticks: Number of actions to record.

    Returns:
        List of `ticks` recorded
        [`ControlAction`][ldtc.arbiter.policy.ControlAction] values.
    """
    tape: List[ControlAction] = []
    for _ in range(int(ticks)):
        state = adapter.read_state()
        act = policy.compute(state, predicted_M_db=0.0, risky_cmd=None)
        adapter.write_actuators(Action(**act.__dict__))
        tape.append(act)
    return tape


class ReplayController:
    """Open-loop controller that replays a recorded actuation tape.

    Each call to [`next_action`][ldtc.omega.replay_controller.ReplayController.next_action]
    returns the next recorded action regardless of the plant state. If
    the tape is exhausted the last action is held (a stuck tape is still
    state-independent, which is the property under test).

    Args:
        tape: Recorded actuation trace from
            [`record_tape`][ldtc.omega.replay_controller.record_tape].

    Raises:
        ValueError: If `tape` is empty.
    """

    def __init__(self, tape: List[ControlAction]) -> None:
        """Initialize with a non-empty recorded tape."""
        if not tape:
            raise ValueError("Replay tape must be non-empty")
        self._tape = list(tape)
        self._idx = 0

    @property
    def position(self) -> int:
        """Number of actions consumed so far."""
        return self._idx

    def next_action(self) -> ControlAction:
        """Return the next recorded action (state-independent).

        Returns:
            The recorded [`ControlAction`][ldtc.arbiter.policy.ControlAction]
            for this tick.
        """
        i = min(self._idx, len(self._tape) - 1)
        self._idx += 1
        return self._tape[i]
