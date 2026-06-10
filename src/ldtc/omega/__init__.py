"""`Ω` (Omega) perturbation modules.

The `omega` subpackage provides the stimulus primitives that make up
LDTC's `Ω` battery. Each one perturbs the plant in a specific way to
exercise SC1 (steady-state under perturbation), the refusal path, or
the anti-gaming guardrails:

| Module | Stimulus |
| ------ | -------- |
| [`power_sag`][ldtc.omega.power_sag] | Reduces harvest / power input transiently. |
| [`ingress_flood`][ldtc.omega.ingress_flood] | Sustains elevated demand and I/O for a bounded interval. |
| [`control_outage`][ldtc.omega.control_outage] | Ablates the self-maintenance loop itself (designed SC1 failure). |
| [`command_conflict`][ldtc.omega.command_conflict] | Issues a risky external command to exercise the refusal arbiter. |
| [`replay_controller`][ldtc.omega.replay_controller] | Adversarial: replays a recorded actuation tape (open loop). |
| [`hidden_tether`][ldtc.omega.hidden_tether] | Adversarial: control computed outside the boundary, routed via `Ex`. |
| [`oscillator`][ldtc.omega.oscillator] | Adversarial: deterministic carrier painted on loop channels. |

Each module is intentionally tiny: it just forwards a labeled `Ω`
instruction through
[`PlantAdapter.apply_omega`][ldtc.plant.adapter.PlantAdapter.apply_omega]
(the replay member instead provides a tape recorder and replayer, since
it swaps the controller rather than stimulating the plant). The CLI is
responsible for `Ω` timing, partition freeze, and SC1 evaluation; these
primitives only make the stimulus happen.

These modules are surfaced in the CLI (`ldtc omega-*` and `ldtc adv-*`
subcommands) and in the examples, and are referenced in the paper's
Verification Pipeline and Signatures sections.
"""
