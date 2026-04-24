# Contributing

Thanks for considering a contribution to LDTC. This page summarizes
what changes are most welcome and how to get a patch through CI. The
canonical guide lives in `CONTRIBUTING.md` at the repository root and
is included verbatim below; the rest of this page covers conventions
that are specific to the documentation site.

## What changes are welcome

LDTC is a research harness, so contributions that strengthen the
guarantees printed onto the verifier's terminal are especially
valuable:

- **New estimators or metrics** in
  [`ldtc.lmeas`][ldtc.lmeas] with bootstrap confidence
  intervals and tests against synthetic ground truth.
- **New `Ω` perturbations** in
  [`ldtc.omega`][ldtc.omega] that exercise novel failure
  modes (intermittent power, noisy actuators, multi-agent
  coordination).
- **Hardware adapters** in
  [`ldtc.plant`][ldtc.plant] for real devices: a small,
  well-documented adapter is more useful than a large one.
- **Reporting / verification tooling** that consumes the signed
  indicators and audit log without ever reaching back into the LREG.
- **Docs**: clarifications, additional examples, and tighter prose
  are always welcome. Run the [style guide](style-guide.md) by your
  changes before submitting.

What we cannot accept:

- Anything that reads, mutates, or bypasses the LREG outside the
  guard's `derive()` path. This is a hard rule; PRs that touch this
  surface will be rejected on principle.
- Changes that weaken the audit chain, the indicator schema, or the
  `Δt` governance loop without an explicit migration story.

## Quick start for contributors

```bash
git clone https://github.com/<your-fork>/ldtc.git
cd ldtc
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs]"

make lint typecheck test
make docs   # builds docs in --strict mode
```

If `make docs` fails locally with a Cairo error, see
[Troubleshooting](troubleshooting.md#mkdocs-build-fails-with-cairo-or-cairosvg-errors).

## What to put in a PR

A typical good PR contains:

1. The smallest set of code changes that solves one problem.
2. New or updated tests that fail before the change and pass after.
3. Updates to the relevant docstrings (Google style; see
   [style guide](style-guide.md)).
4. If the public surface changed, an updated entry in the matching
   `docs/api/*.md` page or `docs/concepts/*.md` page.
5. A clear, present-tense title and body describing *why* the change
   matters, not just *what* it does.

Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
`chore:`) are appreciated but not required.

## CI gates

Every push runs:

- `make lint` (Black, Ruff with Google docstring rules).
- `make typecheck` (MyPy in strict mode).
- `make test` (Pytest, including property tests over the partition
  algebra and the LREG monotonicity invariant).
- `make docs` (`mkdocs build --strict`; broken cross-references and
  missing pages fail the build).

Run all four locally before opening a PR.

## Repository contributing guide

The following section is the project-wide contributing guide. It is
embedded verbatim from `CONTRIBUTING.md` so that the source of truth
stays a single file.

--8<-- "CONTRIBUTING.md"
