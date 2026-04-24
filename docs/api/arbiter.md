# ldtc.arbiter

Refusal semantics and the homeostasis controller policy. The
arbiter is what gives the harness an opinion about *unsafe*
commands when the loop's measurement margin is degraded.

| Module | Headline symbols | Use it for |
| ------ | ---------------- | ---------- |
| [`refusal`](#refusal) | [`RefusalArbiter`][ldtc.arbiter.refusal.RefusalArbiter], [`RefusalDecision`][ldtc.arbiter.refusal.RefusalDecision] | Threat-model gate for risky commands; measures `T_refuse` and audits the decision. |
| [`policy`](#policy) | [`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy], [`ControlAction`][ldtc.arbiter.policy.ControlAction] | Tiny homeostasis controller used by the in-process plant. Reads state, predicts risk from `LREG.latest()`, asks the arbiter, writes actuators. |

::: ldtc.arbiter
    options:
      members: false
      show_root_heading: false
      show_source: false

## refusal

::: ldtc.arbiter.refusal

## policy

::: ldtc.arbiter.policy
