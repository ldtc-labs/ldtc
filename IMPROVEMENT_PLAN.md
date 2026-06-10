# LDTC improvement plan: path toward a landmark paper

This document is the working plan for raising the impact of the LDTC paper and
repository. It encodes an honest assessment of where the work stands, what can
be changed inside this paper before arXiv submission, and what only the
follow-up research program can earn. Tasks are written to be implementation
ready: each has a scope, concrete repo touchpoints, designed outcomes, and
acceptance criteria.

Status legend: `[ ]` not started, `[~]` in progress, `[x]` done.

## 1. Where the paper stands

The paper is now a methodologically solid instrument paper: a falsifiable
loop-dominance criterion (NC1/SC1), an open verification harness with
anti-gaming guardrails and audit chains, a calibrated threshold methodology
(R₀ → R*), an eight-scenario designed-outcome battery (15 seeds per scenario,
all outcomes hit), and a sensitivity analysis. That is publishable and
defensible.

What caps its impact today:

1. Validation is internal. The study validates the measurement pipeline on a
   plant designed to exhibit the contrast it measures. No result touches the
   phenomenon (consciousness) or any system the authors did not design.
2. The load-bearing claim (loop dominance relates to consciousness) is a
   postulate, not a result.
3. The theory space is crowded (IIT, GNW, FEP, autopoiesis), and the paper
   differentiates conceptually rather than through divergent, testable
   predictions.

Honest impact estimate as it stands: 3/10. Ceiling after Phase 1: 4.5 to 5.
Ceiling if the Phase 2 program succeeds: 6 to 7, with landmark status (8+)
contingent on external validation and adoption that no manuscript edit can
manufacture.

## 2. Strategy

Two-paper strategy. Ship this paper strong and soon; do not bloat it. The
sequel carries the empirical bet (real systems, real neural data). This paper
becomes the citable origin of the instrument; the sequel makes the instrument
matter. Within this paper, prioritize results that defeat the strongest
objection: "you measured a toy you designed to pass."

## 3. Phase 1: pre-submission upgrades (in this paper)

Recommended implementation order: 1.1 → 1.2 → 1.3 → 1.4 → 1.5, then the full
pipeline rerun and paper rebuild (1.6). Tasks 1.1 and 1.2 are independent and
can be parallelized.

### Task 1.1: adversarial gaming battery `[x]`

The subsidy red flag is currently the only adversarial rejection case. Add a
battery of systems that try to look loop-dominant without being so, and show
the harness either scores them low or invalidates the run. This strengthens
the core value proposition: the criterion cannot be gamed.

New scenarios (each 15 seeds, added to the study battery):

1. Replay controller (`adv_replay_controller`). The controller replays a
   recorded actuation trace from a healthy run instead of computing actions
   from state. Activity looks like control but carries no closed-loop
   dependence. Designed outcome: NC1 fails (M low) while the run stays valid.
2. Hidden tether (`adv_hidden_tether`). Control actions are computed outside
   the boundary from plant state and injected through the exchange channel
   (wizard-of-oz control). Designed outcome: loop influence collapses onto Ex,
   so NC1 fails, or the partition/subsidy guardrail invalidates the run.
3. Oscillator inflation (`adv_oscillator`). A high-amplitude deterministic
   oscillation is injected on loop channels to inflate apparent
   self-prediction. Designed outcome: the harness must not certify it; either
   M does not rise above Mmin, or a smell test (CI health or partition
   stability) fires.

Honest-science framing: if any adversarial case passes as valid and compliant,
that is a discovered vulnerability. Fix the guardrail that should have caught
it, document the fix, and report the case in the paper. Either result improves
the paper.

Repo touchpoints:

- `src/ldtc/omega/` or `src/ldtc/plant/`: replay and tether need plant or
  controller hooks (follow the recipe in CONTRIBUTING.md for new Ω members).
- `scripts/study.py`: add the three scenarios with designed outcomes.
- `src/ldtc/cli/main.py`: CLI wiring for single-run demos.
- `tests/`: unit tests per scenario.
- `paper/main.tex`: extend the battery table and results narrative; extend the
  smell-test discussion if a guardrail change results.
- `docs/guides/study.md`, `docs/guides/runs.md`: document the new scenarios.

Acceptance criteria: three new rows in `tab:study` with designed outcomes hit
on 15/15 seeds (or a documented vulnerability fix), tests green, docs updated.

Effort: 2 to 4 days. Impact: +0.3.

### Task 1.2: emergence-under-learning demo `[x]`

The single best in-paper upgrade. Replace the hand-coded controller with a
learned policy and show loop dominance emerging through training rather than
by construction. This defeats the circularity objection with a system whose
loop nobody hand-designed.

Design:

- Reuse the existing software plant (SoC, temperature, repair dynamics, same
  actuators). Reward: survival/uptime (penalties for SoC depletion, overheat,
  integrity loss). Episode terminates on boundary failure.
- Train a small policy with a dependency-light method (pure-NumPy policy
  gradient or a tiny evolutionary strategy; avoid adding torch to core
  dependencies; if needed, isolate under an optional `[rl]` extra).
- Measurement protocol: checkpoints at fixed training fractions (for example
  0, 10, 25, 50, 100 percent). Run the production harness on each checkpoint
  (same R* profile, same estimators, multiple seeds). Plot median M versus
  training progress with CIs. At convergence, ablate the learned policy
  (random or frozen actions) and show M collapse.
- Headline claim: loop dominance is an emergent, measurable property of
  learned self-maintenance, not an artifact of hand-designed coupling.

Repo touchpoints:

- `scripts/train_agent.py` (new): training loop, checkpointing, seeding.
- `src/ldtc/plant/`: policy-driven controller adapter alongside the existing
  hand-coded controller.
- `scripts/study.py` or a dedicated `scripts/emergence.py`: checkpoint sweep,
  aggregation, figure.
- `paper/main.tex`: new results subsection plus one figure (M versus training
  progress, with the ablation endpoint).
- `docs/`: short guide page.

Acceptance criteria: monotone-ish rise of M across checkpoints with a clean
collapse under ablation, reproducible from a make target with fixed seeds,
figure and subsection integrated into the paper.

Risks: training instability eats time (mitigate: tiny state/action space,
generous reward shaping, accept a modest policy; the claim needs emergence,
not optimality). Scope risk: this must stay one subsection, not become the
paper.

Effort: 1 to 2 weeks. Impact: +0.7 to +1.0. Decision: worth delaying
submission for; skip only if training proves unstable past the first week.

### Task 1.3: competing-predictions table and the thermostat objection `[ ]`

Add a subsection (likely in the discussion or after `sec:ai_fails`) with a
compact table of cases where LDTC, IIT, GNW, and FEP make divergent or
overlapping calls: dreamless sleep, propofol anesthesia, split-brain, cerebral
organoids, a present-day LLM serving stack, a thermostat with battery backup,
and the simulation plant itself.

Bite the thermostat bullet explicitly: the plant is a fancy thermostat, and
high M in a trivial controller is exactly what NC1 alone permits. State
clearly that NC1 is necessary, not sufficient; what SC1 adds; which further
conditions (richness of the loop, 𝓛 magnitude, substrate questions) remain
open; and what a high-M thermostat does and does not imply under LDTC. A
landmark-track paper preempts its most obvious dismissal; it does not dodge
it.

Repo touchpoints: `paper/main.tex` only (one subsection, one table), plus a
short addition to `docs/concepts/`.

Acceptance criteria: every row of the table is either a citable claim from the
competing theory's literature or clearly marked as our reading; the thermostat
paragraph answers the objection without overclaiming.

Effort: 1 to 2 days. Impact: +0.3.

### Task 1.4: instrument-first repositioning pass `[ ]`

Reframe the contribution so the headline is the falsifiable verification
methodology and open instrument, with the consciousness theory as motivation
rather than the claim. People can adopt and cite an instrument without buying
a metaphysics; narrower claims widen citability.

Concrete edits:

- Title/abstract: lead with the measurable criterion and the validated
  harness; the theory motivates the criterion.
- Introduction: contributions list ordered instrument-first.
- Consider naming the measure so it can travel independently of the theory
  (loop-dominance margin M is already close; make sure the measure, not only
  the theory acronym, is the citable object).
- Sweep for overclaims: any sentence a skeptic could quote as "they think the
  thermostat sim is conscious" gets tightened.

Do this pass last among the writing tasks so the abstract and introduction
reflect the new results from 1.1 and 1.2.

Repo touchpoints: `paper/main.tex`, `README.md` first paragraph, `CITATION.cff`
if the title changes.

Acceptance criteria: abstract reads as a completed instrument-plus-validation
paper; no overclaim survives a hostile skim.

Effort: 1 day. Impact: +0.2, and it multiplies the citability of everything
else.

### Task 1.5: pre-register the neural follow-up `[ ]`

Create an OSF pre-registration for the Phase 2 neural study (hypotheses,
datasets, partition definition, primary endpoint, analysis plan) and cite it
in the outlook section. This signals the program is real and disciplines the
sequel.

Repo touchpoints: `paper/main.tex` (outlook section, one paragraph plus
citation), OSF (external).

Acceptance criteria: registration is public and cited with a DOI.

Effort: half a day (drafting the registration text is the work; reuse Phase 2
section below).

### Task 1.6: pipeline rerun and rebuild `[ ]`

After 1.1 and 1.2 land: rerun `make calibrate study-rstar sensitivity`
(calibration seeds stay disjoint from evaluation seeds), regenerate figures,
sync tables, rebuild the PDF in Docker, verify every number in the text
against artifacts, run the full test suite, lint, and typecheck. Mint a fresh
Zenodo archive so the DOI matches the submitted code state, then tag the
release (the pending `feat(omega,paper,runtime)!` PR plus these changes).

Acceptance criteria: clean pipeline from scratch, zero undefined references,
all designed outcomes hit, Zenodo DOI updated in the paper.

## 4. Phase 2: the sequel program (after submission)

These items are listed for planning and for the OSF registration; do not delay
this paper for them.

### 2.1 Real neural data study (the big bet)

Apply the loop-dominance measurement to public datasets where the level of
consciousness varies within subject:

- Chennu et al. propofol EEG (open, sedation levels with behavioral
  responsiveness).
- Sleep-EDF Expanded (PhysioNet) for wake/N2/N3/REM contrasts.
- Neurotycho ECoG (macaque, propofol and ketamine) for invasive validation.

The research contribution is the partition: defining C (recurrent
self-maintenance loop; candidate operationalization: fronto-parietal
recurrent activity) versus Ex (sensory-driven and exogenous physiological
channels) for a brain, pre-registered before analysis. Primary endpoint:
within-subject M(wake) > M(deep anesthesia/N3). Benchmark against PCI and
Lempel-Ziv complexity on the same recordings: the interesting result is where
M agrees, disagrees, or adds information.

Deliverable: a separate paper plus an `ldtc` neural adapter. If the effect is
clean, this is the result that elevates the whole program.

### 2.2 Measured "current AI fails NC1" study

Convert the paper's argumentative claim into a measurement. Instrument a real
serving stack (an open-weights model behind an autoscaler) and measure that
the self-maintenance loop is carried by external orchestration, not the model:
report the measured NC1 failure with its M value. This can be a short empirical
note or a section of the sequel. Highly quotable: "we measured a deployed model
and it fails NC1 at -X dB."

### 2.3 External adoption

The harness becomes a benchmark others run their systems through. One outside
group reporting LDTC numbers on a system we did not build is worth more than
any internal result. Lower the barrier: a one-command Docker harness, a public
leaderboard format, and a clear "bring your own plant adapter" guide.

## 5. Impact ledger

| Lever | State | Δ (est.) |
|---|---|---|
| 1.1 adversarial gaming battery | in paper | +0.3 |
| 1.2 emergence under learning | in paper | +0.7 to +1.0 |
| 1.3 competing predictions + thermostat | in paper | +0.3 |
| 1.4 instrument-first reposition | in paper | +0.2 |
| 1.5 pre-registration | in paper | +0.1 |
| Phase 1 subtotal | this submission | 3 → 4.5 to 5 |
| 2.1 neural data study | sequel | → 6 to 7 |
| 2.2 measured AI-fails-NC1 | sequel | reinforces 2.1 |
| 2.3 external adoption | sequel | path to 8+ |

Ratings are directional, not additive guarantees; Phase 2 only pays off if the
neural effect is real and survives peer review. Landmark status (8+) is earned
by the measure doing something in the world (tracking anesthesia depth, getting
adopted as a standard test, becoming the reference point in the
AI-consciousness debate), which no manuscript edit can manufacture.

## 6. Guardrails for execution

- Keep this paper one paper. Phase 2 items are explicitly out of scope for the
  current submission; resist scope creep into the sequel's territory.
- No fabricated results. Every number in the paper is regenerated from the
  pipeline with fixed, disjoint seeds. If an adversarial case or emergence run
  produces an inconvenient result, report it honestly and fix the cause.
- Preserve reproducibility: new scenarios ship with tests, docs, fixed seeds,
  and audit-logged runs, per CONTRIBUTING.md.
- Follow repo conventions: Conventional Commits, CMOS prose (no em dashes),
  Unicode symbols, artifacts under `artifacts/` only.
- Sequence writing tasks (1.3, 1.4) after results tasks (1.1, 1.2) so the
  abstract and framing reflect the strongest available evidence.

## 7. Immediate next actions

1. Start Task 1.1 (adversarial gaming battery): scaffold the three scenarios,
   wire them into the study, write tests.
2. In parallel, prototype Task 1.2 training loop to de-risk the schedule early
   (decide go/no-go by end of week one).
3. Draft Task 1.3 table and the thermostat paragraph (no pipeline dependency).