# Frequently asked questions

A grab bag of questions that come up while reading the paper, running
the harness, or hooking it up to a real device.

## What is LDTC, in one sentence?

LDTC (Loop-Dominance Theory of Consciousness) is a real-time verifier
that asks two questions every Δt: *is the loop dominant?* (NC1) and
*does it stay dominant when probed?* (SC1), and signs the answers
into a hash-chained audit log.

## How does this differ from generic control or anomaly detection?

A generic controller tries to keep a process variable inside bounds.
LDTC measures **whether the loop is doing the keeping** rather than
exogenous shocks or coincidence: `M = 𝓛_loop / 𝓛_ex`. SC1 then
perturbs the system on purpose and waits for `M` to recover. The
output is a falsifiable claim about loop authority, not just an "all
green" dashboard.

??? info "More precisely"
    NC1 (necessary condition) is satisfied when `M >= Mmin` for
    `>= Mq` consecutive windows. SC1 (sufficient condition) is
    satisfied when, after an `Ω` perturbation, `M_post` recovers to
    `>= Mmin - δ` within `<= τ_max`. The audit log records both.

## What does an "Ω trial" actually do?

It schedules an external perturbation in the middle of a run and
records what the controller does. The four built-in stimuli live in
[`ldtc.omega`][ldtc.omega]:

| Stimulus | What it perturbs |
|----------|------------------|
| `power_sag` | Reduces the available control authority. |
| `ingress_flood` | Bursts exogenous traffic into the plant. |
| `command_conflict` | Issues a boundary-threatening external command. |
| `exogenous_subsidy` | Injects unearned support so the loop looks dominant when it is not (a negative control). |

After Ω, the recovery window is measured and SC1 is evaluated.

## Why are the indicators so small?

By design. The signed CBOR payload is a few hundred bytes containing
**derived** quantities only: `nc1_pass`, `m_db`, `counter`,
`invalidated`, `last_sc1_pass`, the audit hash head, and the profile
id. Raw `𝓛` values, confidence intervals, and per-window timings
stay inside the LREG, never on the wire.

This keeps verification cheap (a small file plus a public key) and
deniability minimal (you can prove what was claimed, not what was
hidden).

## Can I run LDTC without hardware?

Yes. The default plant is the synthetic
[`Plant`][ldtc.plant.models.Plant] from
[`ldtc.plant.models`][ldtc.plant.models], which is sufficient for
reproducing the paper's NC1/SC1 plots and for unit tests. Real
devices plug in via [`ldtc.plant.hw_adapter`][ldtc.plant.hw_adapter]
(see the [Hardware adapter guide](../guides/hardware.md)).

## What Python version do I need?

3.9 or later for the package. The project's CI tests on 3.10 and
3.12. macOS users on Apple Silicon should prefer Homebrew's Python
3.12 over the system Python 3.9 because `mkdocs-material`'s social
plugin links against `cairo` and the system Python cannot find it.
See [Troubleshooting](troubleshooting.md#mkdocs-build-fails-with-cairo-or-cairosvg-errors).

## Can I change Δt mid-run?

No. Δt is set once at scheduler construction and is enforced by the
[`Δt` guard][ldtc.guardrails.dt_guard]. If you need a different
sampling rate, stop the scheduler, build a new one, and start a new
run. The guard exists to make sure you cannot trick `M` by silently
slowing the loop.

## What invalidates a run?

Anything the smell tests catch. Examples:

- The audit chain is broken (a record's `prev_hash` does not match).
- The LREG was written to from outside `LREG.write` (monotonicity
  broken).
- The bootstrap CIs are pathologically wide (`ci_inflation`).
- Δt jitter exceeds the configured percentile.

When invalidated, the LREG flips an irreversible flag and the
exporter stops claiming NC1/SC1. The run is recorded but cannot be
counted as a passing trial.

## Can I run multiple harnesses against the same plant?

Yes, but treat each as an independent trial. Use distinct output
directories and distinct profile ids in the indicator config so you
can match `.cbor` files back to their LREG. The audit log is
per-process; do not share a file across processes.

## How do I cite LDTC?

See [Citation](citation.md) for a BibTeX block and a recommended
in-text reference.

## Where do bugs and feature requests go?

Open an issue on the
[ldtc-labs/ldtc](https://github.com/ldtc-labs/ldtc) repository. For
questions about the paper itself, please open a discussion rather
than an issue so the conversation stays browsable.

## See also

- [Troubleshooting](troubleshooting.md) for concrete error messages.
- [Style guide](style-guide.md) if you are writing docs or
  docstrings.
- [Contributing](contributing.md) for the development workflow.
