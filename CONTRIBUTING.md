### Contributing to LDTC Hello-World

Thanks for your interest in contributing. This repository is a verification harness for the Loop‑Dominance (NC1/SC1) pipeline described in the manuscript. Contributions should keep the code reproducible, auditable, and consistent with the paper’s symbols and assumptions (Δt, M, ε, τmax, σ, C/Ex partition, Ω battery, LREG/attestation).

## Quick start

Development uses Python ≥ 3.9.

```bash
# install runtime deps (editable)
make install

# install dev tooling (pytest, ruff, black, mypy)
make dev

# run tests, lint, type-check, and format
make test
make lint
make typecheck
make fmt

# smoke runs
make run          # baseline NC1
make omega-power-sag   # Ω power-sag demo
```

## Project layout (high-level)

- `src/ldtc/`
  - `arbiter/` – policy and refusal semantics
  - `attest/` – indicators, exporter, keys (LREG-derived)
  - `cli/` – command-line interface and entrypoints
  - `guardrails/` – audit, Δt guards, smell-tests
  - `lmeas/` – estimators, metrics, partitioning
  - `omega/` – perturbation generators (power sag, ingress flood, command conflict)
  - `plant/` – sim/hw adapters and models
  - `reporting/` – artifacts, tables, timelines
  - `runtime/` – scheduler and windows
- `configs/` – R₀ defaults, negative controls, example R* profile
- `scripts/` – calibration, indicator verification, batch helpers
- `tests/` – unit tests
- `docs/` – method notes and figures

## Coding guidelines

- Style: Black; lint: Ruff; typing: MyPy (settings in `pyproject.toml`).
- Prefer explicit, descriptive names; follow repository symbol mapping to the paper.
- Add/extend tests in `tests/` for new behavior; keep fast unit tests (no network/large IO).
- Keep artifacts under `artifacts/` only; do not commit generated files.

Common commands:

```bash
make test            # pytest -q
make lint            # ruff check .
make typecheck       # mypy src tests scripts
make fmt             # black src tests examples scripts
```

## Conventional Commits

This project uses Conventional Commits. Use the form:

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Commit message character set

- Encoding: UTF‑8 is allowed and preferred across subjects and bodies.
- Subjects may include UTF‑8 symbols (e.g., Δ, 𝓛, λ/θ/κ) when they add clarity; keep the subject ≤ 72 chars and avoid emoji.
- If maximum legacy compatibility is needed, prefer ASCII in the subject and use UTF‑8 in the body.

Example (UTF‑8 subject):

```
feat(lmeas,cli): implement greedy Δ𝓛 loop-gain partitioning with hysteresis; add λ/θ/κ knobs
```

Accepted types (stick to the standard):

- `build` – build system or external dependencies (e.g., requirements, packaging)
- `chore` – maintenance (no src/ behavior change)
- `ci` – continuous integration configuration (workflows, pipelines)
- `docs` – documentation only
- `feat` – user-facing feature or capability
- `fix` – bug fix
- `perf` – performance improvements
- `refactor` – code change that neither fixes a bug nor adds a feature
- `revert` – revert of a previous commit
- `style` – formatting/whitespace (no code behavior)
- `test` – add/adjust tests only

Recommended scopes (choose the smallest, most accurate unit; prefer module/directory names):

- Module/directory scopes:
  - `arbiter` – policy and refusal semantics
  - `attest` – indicators, exporter, keys (LREG-derived)
  - `cli` – command-line interface and entrypoints
  - `guardrails` – audit, Δt guards, smell-tests
  - `lmeas` – estimators, metrics, partitioning
  - `omega` – perturbation generators (power sag, ingress flood, command conflict)
  - `plant` – sim/hw adapters and models
  - `reporting` – artifacts, tables, timelines
  - `runtime` – scheduler and windows

- Other scopes:
  - `configs` – configuration files (R₀ defaults, negative controls, example R* profile)
  - `deps` – dependency updates and version pins (e.g., requirements files)
  - `docker` – containerization (e.g., `Dockerfile`, image build/runtime settings)
  - `examples` – example scripts and minimal demos under `examples/`
  - `makefile` – `Makefile` targets and build helpers
  - `notebooks` – Jupyter notebooks under `notebooks/`
  - `paper` – LaTeX manuscript sources under `paper/` (e.g., `main.tex`, `macros.tex`, `refs.bib`, `Makefile`, `scripts/`)
  - `pyproject` – `pyproject.toml` packaging/build metadata and tool config
  - `repo` – repository metadata and top-level files (e.g., `README.md`, `CONTRIBUTING.md`, `LICENSE`, `CITATION.cff`, `.gitignore`); also docs assets like images under `docs/assets/`
  - `scripts` – utility/CLI scripts under `scripts/`
  - `tests` – unit/integration tests under `tests/`
  - `workflows` – CI pipelines under `.github/workflows/`

Note: Avoid redundant type==scope pairs (e.g., `docs(docs)`). Prefer a module scope (e.g., `docs(attest)`) or `docs(repo)` for top-level repository updates.

Examples:

```text
build(deps): refresh pinned versions
chore(makefile): add figures target for paper assets
chore(pyproject): bump version to 0.2.0
ci(workflows): add indicator verification job
docs(attest): clarify Mq bit width and signing scheme
docs(notebooks): clarify demo parameters in 02_sc1_omega.ipynb
docs(repo): update LDTC logo asset in docs/assets
feat(lmeas): add Kraskov kNN MI path with configurable k
fix(omega): correct power-sag duration units to seconds
perf(plant): reduce allocation in sim step to lower GC pauses
refactor(runtime): extract jitter accounting from scheduler loop
revert(cli): revert omega ingress flag rename
test(guardrails): add Δt governance invalidation cases
```

Examples (no scope):

```text
build: update packaging metadata
chore: update .gitignore patterns
docs: add Zenodo DOI
revert: revert "refactor(runtime): extract jitter accounting from scheduler loop"
style: format code with Black
```

Breaking changes:

- Use `!` after the type/scope or a `BREAKING CHANGE:` footer.

```text
feat(lmeas)!: change default Mmin from 1 dB to 3 dB

BREAKING CHANGE: Default NC1 threshold raised to 3 dB; update configs.
```

### Multiple scopes (optional)

- Comma-separate scopes without spaces: `type(scope1,scope2): ...`
- Prefer a single scope when possible; use multiple only when the change genuinely spans tightly related areas.

Scope ordering (house style):

- Put the most impacted scope first (e.g., `repo`), then any secondary scopes.
- For extra consistency, alphabetize the remaining scopes after the primary.
- Keep it to 1–3 scopes max.

Example:

```text
feat(reporting,cli): add SC1 figure bundle; CLI wires new subcommand
```

Primary = `reporting` (new figure generation and bundling). Secondary = `cli` (exposes/wires the subcommand).

Examples:

```text
feat(cli,reporting): add figures subcommand and timeline export
fix(guardrails,attest): block raw LREG reads and enforce indicator-only exports
refactor(runtime,lmeas): decouple scheduler tick from windowing logic
```

## Pull request checklist

- Tests: added/updated; `make test` passes.
- Lint/format/type-check: `make lint`, `make fmt`, `make typecheck` pass.
- Docs: update `docs/` and `README.md` if behavior, symbols, or indicators change.
- Configs: update `configs/profile_r0.yml` and example R* mapping if thresholds/symbols move.
- Artifacts: none committed; runs write to `artifacts/` only.

## Adding a new Ω perturbation or estimator (quick recipe)

- Ω: implement under `src/ldtc/omega/`, add CLI wiring in `cli/`, add tests in `tests/test_omega.py`.
- Estimator: implement in `src/ldtc/lmeas/`, expose config flags, and extend tests in `tests/test_estimators.py`.
- Update indicators/reporting if exported fields change; update docs.

## Versioning and releases

- The version is tracked in `pyproject.toml` (`project.version`). Use SemVer where practical.
- Maintainers bump versions as part of release PRs (include release notes in the PR body).

## Security and provenance

- LREG/attestation paths are measurement-only; do not expose raw LREG contents outside enclave abstractions in code or docs.
- Δt governance and audit rules must not be bypassed in contributions; changes require tests and documentation.

## License

By contributing, you agree that your contributions are licensed under the repository’s MIT License.
