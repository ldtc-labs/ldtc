### Contributing to LDTC

Thanks for your interest in contributing. This repository is a verification harness for the Loop-Dominance (NC1/SC1) pipeline described in the manuscript. Contributions should keep the code reproducible, auditable, and consistent with the paper's symbols and assumptions (Δt, M, ε, τmax, σ, C/Ex partition, Ω battery, LREG/attestation).

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
  - `omega/` – perturbation generators (power sag, ingress flood, command conflict, adversarial gaming battery)
  - `plant/` – sim/hw adapters and models
  - `reporting/` – artifacts, tables, timelines
  - `runtime/` – scheduler and windows
- `configs/` – R₀ defaults, negative controls, example R* profile
- `scripts/` – calibration, indicator verification, batch helpers
- `tests/` – unit tests
- `docs/` – method notes and figures

## Coding guidelines

- Style: Black; lint: Ruff (with the Google docstring convention enabled); typing: MyPy (settings in `pyproject.toml`).
- Docstrings: Google-style throughout. See the project [documentation style guide](https://docs.ldtc.dev/meta/style-guide/) for the full conventions and examples, and the [Google Python Style Guide §3.8 Comments and Docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) for the upstream reference.
- Prose follows the *Chicago Manual of Style* (17th ed.): no em dashes, straight ASCII quotes, serial commas, sentence-case headings. Keep Greek and mathematical symbols (Δt, 𝓛, M, ε, τ, σ, Ω) as Unicode.
- Prefer explicit, descriptive names; follow repository symbol mapping to the paper.
- Add or extend tests in `tests/` for new behavior; keep fast unit tests (no network or large IO).
- Keep artifacts under `artifacts/` only; do not commit generated files.

Common commands:

```bash
make test            # pytest -q
make lint            # ruff check . (includes Google-style docstring rules on src/ldtc)
make typecheck       # mypy src tests scripts
make fmt             # black src tests examples scripts
make docs            # mkdocs build --strict
make docs-serve      # mkdocs serve (live preview at http://127.0.0.1:8000)
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
  - `omega` – perturbation generators (power sag, ingress flood, command conflict, adversarial gaming battery)
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
  - `mkdocs` – documentation site (MkDocs/Material) configuration and content under `docs/`
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

## Pull requests and squash merges

- PR title: use Conventional Commit format.
  - Example: `feat(cli): add figures subcommand`
  - Imperative mood; no trailing period; aim for ≤ 72 chars; use `!` for breaking changes.
  - Prefer one primary scope; use comma-separated scopes only when necessary.
- PR description: include brief sections: What, Why, How (brief), Testing, Risks/Impact, Docs/Follow-ups.
  - Link issues with keywords (e.g., `Closes #123`).
- Merging: use "Squash and merge" with "Pull request title and description".
- Keep PRs focused; avoid unrelated changes in the same PR.

Conventional Commits applies to the subject line (your PR title) and optional footers. The PR body is free-form; when squashing, it becomes the commit body. Place any footers at the bottom of the description.

Recommended PR template:

```text
What
- Short summary of the change

Why
- Motivation/user value

How (brief)
- Key implementation notes or decisions

Testing
- Local/CI coverage; links to tests if relevant

Risks/Impact
- Compat, rollout, perf, security; mitigations

Docs/Follow-ups
- Docs updated or TODO next steps

Closes #123
BREAKING CHANGE: <details if any>
Co-authored-by: Name <email>
```

## Pull request checklist

- PR title: Conventional Commits format (CI-enforced by `pr-lint.yml`).
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

- The version is tracked in `pyproject.toml` (`project.version`) and mirrored in `src/ldtc/__init__.py` as `__version__`. Both files are updated automatically by [python-semantic-release](https://python-semantic-release.readthedocs.io/).
- **Automated release pipeline** (on every merge to `main`):
  1. `python-semantic-release` scans Conventional Commit messages since the last tag.
  2. It determines the next SemVer bump: `feat` → **minor**, `fix`/`perf` → **patch**, `BREAKING CHANGE` → **major**.
  3. Version files are updated, `CHANGELOG.md` is generated, and a tagged release commit (`chore(release): vX.Y.Z`) is pushed.
  4. A GitHub Release is created with auto-generated release notes and the built sdist/wheel attached.
  5. When drafts are disabled, the package is also published to PyPI via Trusted Publishing.
- **Draft / published toggle**: the `DRAFT_RELEASE` variable at the top of `.github/workflows/release.yml` controls release mode. Set to `"true"` (the default) for draft GitHub Releases with PyPI publishing skipped; flip to `"false"` to publish releases and upload to PyPI immediately.
- Commit types that trigger a release: `feat` (minor), `fix` and `perf` (patch), `BREAKING CHANGE` (major). All other types (`build`, `chore`, `ci`, `docs`, `refactor`, `revert`, `style`, `test`) are recorded in the changelog but do **not** trigger a release on their own.
- Tag format: `v`-prefixed (e.g., `v1.1.0`).
- Manual version bumps are no longer needed; just merge PRs with valid Conventional Commit titles. For ad-hoc runs, use the workflow's **Run workflow** button (`workflow_dispatch`).

### Branching rules

- `main`: default branch; protected; mirrors PyPI.
- All work branches are created from `main`.

#### Branch naming

- Use lowercase kebab-case; no spaces; keep names concise (aim ≤ 40 chars).
- Branch prefixes match Conventional Commit types:
  - `feat/<scope>-<short-desc>`
  - `fix/<issue-or-bug>-<short-desc>`
  - `chore/<short-desc>`
  - `docs/<short-desc>`
  - `ci/<short-desc>`
  - `refactor/<scope>-<short-desc>`
  - `test/<short-desc>`
  - `perf/<short-desc>`
  - `build/<short-desc>`
- Optionally append an issue ID at the end (e.g., `feat/cli-figures-123`).
- Delete remote and local branches after merge.

Examples:

```text
feat/cli-figures
fix/omega-duration-units-123
docs/contributing-branch-naming
ci/mplbackend-agg-headless
build/lock-filters-ldtc
refactor/runtime-jitter-accounting
test/omega-suite
fix/attest-sig-verify
```

### CI

- **CI** (`ci.yml`): runs Black, Ruff, MyPy, pytest, and indicator verification on pushes to `main` and PRs.
- **PR Lint** (`pr-lint.yml`): validates the PR title against Conventional Commits format (protects squash merges) and checks individual commit messages via commitlint (protects rebase merges). Recommended: add the **PR title** job as a required status check in branch-protection settings.
- **Release** (`release.yml`): runs on merge to `main`; computes version, generates changelog, tags, creates GitHub Release, and (when `DRAFT_RELEASE` is `"false"`) publishes to PyPI.
- **Docs** (`docs.yml`): deploys documentation to GitHub Pages on push to `main`.
- **Build Paper** (`build-paper.yml`): compiles the LaTeX manuscript.

## Security and provenance

- LREG/attestation paths are measurement-only; do not expose raw LREG contents outside enclave abstractions in code or docs.
- Δt governance and audit rules must not be bypassed in contributions; changes require tests and documentation.

## License

By contributing, you agree that your contributions are licensed under the repository's MIT License.
