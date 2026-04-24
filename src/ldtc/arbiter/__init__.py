"""Arbitration and refusal policy for boundary preservation.

`arbiter` implements LDTC's "survival comes first" policy. It exposes a
small refusal arbiter that gates risky external commands when the
predicted loop margin or basic resource constraints indicate the system
is near a boundary it must not cross, and a controller policy that
layers homeostatic actuator setpoints on top of that arbiter.

| Module | Responsibility |
| ------ | -------------- |
| [`refusal`][ldtc.arbiter.refusal] | The refusal arbiter (`RefusalArbiter`) and its `RefusalDecision` payload. |
| [`policy`][ldtc.arbiter.policy] | The simple `ControllerPolicy` used by the verification harness. |
"""
