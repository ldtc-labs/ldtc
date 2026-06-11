# Differential predictions and the thermostat objection

This page is the documentation companion to the paper's section
"Differential Predictions and the Thermostat Objection." It summarizes
where LDTC agrees with the major theories of consciousness, where it
diverges, and, most importantly, what a high loop-dominance margin does
and does not imply. The paper carries the citations; this page is the
short, code-facing version.

!!! note "LDTC reports a loop-dominance verdict, not a verdict on experience"
    Every LDTC call below is an NC1/SC1 decision about measurable
    self-maintenance (see the paper's Formal Criterion). Whether loop
    dominance has anything to do with phenomenal experience is an open
    interpretive question that the harness does not settle.

## The partition sets the question

An LDTC verdict is only defined relative to a declared `(C, Ex)`
partition that is fixed before measurement (see
[Definitions](definitions.md) and the
[Mental model](mental-model.md)). The partition decides which question
you are asking:

- A **whole-organism metabolic** partition asks whether the organism
  sustains itself. By that reading a sleeping or anesthetized body is
  still self-maintaining.
- A **cortical recurrent** partition asks whether a fronto-parietal
  self-maintenance loop dominates sensory-driven exchange. By that
  reading loop dominance can fall even while the body lives.

Because the consciousness literature is about brains, the comparison
table reports LDTC under the cortical partition so the columns line up.

## Where the theories agree and diverge

| Case | LDTC (NC1/SC1) | IIT (Φ) | GNW | FEP / active inference |
| ---- | -------------- | ------- | --- | ---------------------- |
| Dreamless sleep (NREM N3) | Cortical loop weakens; `M` predicted to fall | Reduced; effective connectivity breaks down; PCI low | Absent; global ignition lost | Reduced hierarchical inference |
| Propofol anesthesia | `M` predicted low; recurrent loop suppressed | Low; PCI drops across sedation | Absent; ignition lost | Reduced precision / self-evidencing |
| Split-brain | One or two loops is partition-dependent and measurable | Two complexes, possibly two centers | Reportability splits; unity contested | Ambiguous; one or two Markov blankets |
| Cerebral organoid | Metabolic NC1 may hold; no demonstrated cognitive loop | Minimal but nonzero; PCI proposed as an assay | Absent; no workspace | Minimal |
| LLM serving stack (autoscaled) | NC1 fails; self-maintenance is external | Near-zero Φ for feedforward inference | No global workspace | Not self-evidencing; no own boundary |
| Thermostat with battery backup | NC1 can pass; loop is real but NC1 is necessary, not sufficient | Tiny nonzero Φ; a "modicum of experience" | No; no workspace | Rudimentary active inference; has a Markov blanket |
| Simulation plant (this repo) | Passes NC1 (`M ≈ +23 dB`) and SC1; loop dominance certified, no consciousness claim | Low Φ; near-linear six-channel plant | No | A homeostat doing crude active inference |

Cells are either citable claims from the named theory's literature or
marked as our reading in the paper. The theories converge on the easy
cases (sleep, anesthesia, an LLM stack) and separate on the awkward
ones (split-brain, organoid, thermostat). LDTC's distinctive move is to
make the dividing question measurable rather than to settle it by
intuition.

## Biting the thermostat bullet

The plant in this repo is, structurally, a fancy thermostat: a
low-dimensional controller that regulates a handful of internal states.
A high `M` in such a system is not an embarrassment; it is exactly what
NC1, taken alone, is meant to permit.

!!! warning "NC1 is necessary, not sufficient"
    Loop dominance is a necessary condition for self-prioritizing
    self-maintenance, not a sufficient condition for consciousness. A
    battery-backed thermostat that managed its own power could clear
    `Mmin`. That says the loop is real and measurable, nothing more.

What SC1 adds is resilience: a system passes only if loop dominance
recovers, within a calibrated depth and time, after every member of a
pre-registered perturbation battery, including a designed-fail member
the criterion must reject (see the paper's Sufficient Condition and the
[Runs and Ω battery](../guides/runs.md) guide). SC1 raises the bar, but
it does not turn a necessary condition into a sufficient one for
phenomenology.

Three conditions a stronger account would need stay open under both
rules:

- **Richness of the loop.** A one-state regulator and a brain can both
  be loop-dominant while differing by every measure that matters.
- **Magnitude of 𝓛, not only the ratio `M`.** The loop-influence noise
  gate (see [Guardrails and invalidations](guardrails.md)) is a first,
  crude floor on absolute influence, not a richness measure.
- **Substrate.** Any physical theory of experience must eventually face
  questions LDTC does not address.

So what a high-`M` thermostat implies under LDTC is precise and modest:
the device has a genuine, self-prioritizing maintenance loop that an
auditor can certify and an adversary cannot easily fake (see the paper's
adversarial gaming results). What it does not imply is that the
thermostat is conscious, or that loop dominance is sufficient for
experience.

## Next steps

- Read the symbols: [Definitions](definitions.md)
- See the guardrails behind the noise gate: [Guardrails and invalidations](guardrails.md)
- Walk the validated battery: [Study and results](../guides/study.md)
- Get the one-paragraph picture: [Mental model](mental-model.md)
