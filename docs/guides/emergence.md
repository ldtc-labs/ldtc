# Emergence under learning

The strongest objection to any loop-dominance criterion is
circularity: if the plant and its controller were designed so that
the internal nodes predict one another, then measuring high
`L_loop` only confirms the design. The emergence pipeline answers
that objection with a system whose loop is **not** designed. A tiny
policy network is trained from scratch on a plant with no intrinsic
internal couplings, the training objective never mentions loop
dominance, the partition, or the estimator, and the production
harness then measures every stage of training. Loop dominance rises
with competence, and collapses when the same trained policy is
replayed without its state dependence.

## The plant

`configs/profile_emergence.yml` configures the adversarial test
plant (the same one the replayed-actuation and hidden-tether
scenarios use): the intrinsic cross-couplings `c_TE`, `c_RT`, and
`c_RE` are zeroed and self-damping is weak, so left alone the
internal nodes share no dynamics beyond noise. Serving demand heats
and wears the system, cooling and repair cost energy, and harvest
is finite. Whatever couples `E`, `T`, and `R` to one another in
this system is the controller's state-to-actuation pathway, and
nothing else.

## The policy and the objective

`scripts/train_agent.py` trains the policy
(`ldtc.plant.policy_controller.MLPPolicy`, a pure-NumPy MLP) with
an antithetic evolution strategy. The policy is interoceptive: it
observes the internal nodes `(E, T, R)` only, like the hand-coded
controller it replaces, so the learned law is internal-state
feedback by construction (with exteroceptive inputs the optimizer
also learns feedforward control from the demand channel, which the
harness correctly attributes to exchange). The reward has three
terms:

- **Uptime.** One point per surviving tick; the episode ends on
  boundary failure (energy depletion, overheating, integrity
  loss).
- **Service.** Reward proportional to the demand actually served
  (demand times the unthrottled fraction), so blanket load
  shedding has an opportunity cost.
- **Homeostasis.** A capped penalty proportional to each internal
  node's deviation from its setpoint.

Episodes are stressed by randomized power sags and ingress floods.
The terms are calibrated so that no state-blind policy does well:
a do-nothing policy overheats in floods, a constant-actuation
policy exhausts its energy store in sags or pays heavy deviation
penalties, and only state-coupled feedback (cool when hot, repair
when worn, gate spending on the energy store, shed load under
distress) scores highly. None of the terms reference `L_loop`,
`L_ex`, `M`, or the `C`/`Ex` partition.

## The measurement

`scripts/emergence.py` sweeps the saved checkpoints (0, 10, 25,
50, and 100 percent of training) through the `run-policy` CLI
handler: the same sliding window, estimators, guardrails, audit
chain, and attestation as every other run in the repository,
across `N` seeds per checkpoint. At the final checkpoint it also
measures two matched, state-independent ablations of the trained
policy:

- **Shuffled**: actions drawn i.i.d. from a recorded tape of the
  policy's own closed-loop behavior (identical marginal action
  statistics, no state dependence).
- **Frozen**: the tape's mean action held constant.

If the measured loop dominance were an artifact of actuation
statistics, the ablations would preserve it. If it is carried by
the learned feedback, both must collapse it.

## Run it

```bash
make train-agent    # ES training -> artifacts/emergence/checkpoints
make emergence      # checkpoint sweep -> artifacts/emergence
```

Or directly, to choose seeds or skip pieces:

```bash
python scripts/train_agent.py --generations 600 --seed 7
python scripts/emergence.py --seeds 15 [--rstar] [--no-ablations]
```

Single checkpoint, by hand:

```bash
python -m ldtc.cli.main run-policy \
  --config configs/profile_emergence.yml \
  --policy artifacts/emergence/checkpoints/ckpt_100.json \
  [--ablation shuffled|frozen]
```

## Outputs

Written to `artifacts/emergence/`:

- `training_log.json`: ES fitness history and checkpoint metadata.
- `emergence_results.json` / `.csv`: per-condition aggregates
  (median `M` with bootstrap CI, NC1 pass rate with Wilson CI,
  validity, certified-window fractions) plus per-run rows.
- `figures/fig_emergence.{png,pdf,svg}`: training curve with
  checkpoint marks, and measured `M` per checkpoint with the
  ablation endpoints.

The seed is the unit of replication, with the same statistics the
[study](study.md#statistics) uses.

## Reading the result

The signature has three parts. The untrained checkpoint does not
certify: near-constant actuation leaves both influence estimates
at their noise floors, the margin is pinned at 0 dB, and the
`L_loop` gate refuses. Loop dominance rises across training as the
policy learns state-coupled control, with the trained checkpoints
certifying NC1 across seeds. Both ablations of the same trained
policy fail NC1 on every seed, on valid runs, and they fail the
same way the replayed-actuation attack fails: the quiet plant
keeps the *margin* misleadingly positive, but the measured
`L_loop` falls to the estimator's null bias, far below the trained
policy's, and the noise gate refuses certification. Together these
show the harness tracks the *learned closure of the loop*, not the
plant, the actuation statistics, or the experimenter's wiring.

## See also

- [Runs and Ω Battery](runs.md): the adversarial battery this
  plant comes from.
- [Study and Results](study.md): the multi-seed methodology.
- `paper/main.tex`: Results, "Loop dominance emerges under
  learning."
