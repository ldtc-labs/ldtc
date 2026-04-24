# Documentation style guide

This page describes how LDTC's documentation and source-level docstrings
are written. Follow it when authoring new code or revising existing
pages so the site renders consistently and `help()` reads cleanly in a
Python REPL or Jupyter notebook.

## TL;DR

- Use **Google-style** docstrings everywhere (modules, classes, functions).
- Let type hints carry the types; do not repeat them inside docstrings.
- Use Material **admonitions** (`!!! tip "Title"`) for callouts in
  Markdown, not plain `>` blockquotes.
- Cross-link API symbols using mkdocstrings autorefs:
  `` [`estimate_L`][ldtc.lmeas.estimators.estimate_L] ``.
- Reference the paper by section or box (for example,
  "see paper §4.2 NC1") rather than by page number.
- Comments explain **why**, not **what** (the code already says what).

## Grammar and punctuation

We follow the *Chicago Manual of Style* (17th edition) for prose.
Highlights:

- **No em dashes (`—`).** Use commas, parentheses, semicolons, colons,
  or full sentences instead. The exact replacement depends on context:
  use a pair of commas for a brief aside, parentheses for a longer one,
  a colon before a list or amplification, and a semicolon between two
  related independent clauses.
- **Use straight ASCII quotes and apostrophes** (`"` and `'`), not
  curly quotes. This keeps prose copy-pasteable into source code,
  terminals, and search.
- Use the **serial (Oxford) comma** in lists of three or more.
- Spell out **e.g.** and **i.e.** with periods and follow them with a
  comma: `e.g., a power-sag trial`.
- Hyphenate compound modifiers before a noun (`fixed-interval scheduler`,
  `device-signed indicator`) but not after (`the scheduler is fixed
  interval`).
- Use **sentence case** for headings and titles: only the first word
  and proper nouns are capitalized.

### Scientific symbols

LDTC's primitives use Greek and mathematical symbols throughout:
**Δt**, **𝓛**, **M**, **ε**, **τ**, **σ**, **Ω**, **NC1**, **SC1**, **Mq**.
Use them as Unicode (UTF-8) in prose, docstrings, commit messages, and
filenames where natural. ASCII fallbacks (`dt`, `L_loop`, `tau_rec`) are
fine inside identifiers and YAML keys, but the docs should match the
paper's notation. The repo's editor and CI configs already assume UTF-8
source files.

## Docstrings: Google style

LDTC follows the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
The `mkdocstrings` plugin is configured for Google style and renders
the standard sections as tables.

### Function or method

```python
def estimate_L(
    X: np.ndarray,
    C: Sequence[int],
    Ex: Sequence[int],
    method: str = "linear",
    p: int = 3,
) -> LResult:
    """Estimate loop and exchange influence over a C/Ex partition.

    Computes `L_loop` over partition `C` and `L_ex` from `Ex -> C`
    using the selected predictive-dependence metric. Confidence
    intervals are produced via circular block bootstrap.

    Args:
        X: Time-by-signal matrix of shape `(T, N)`.
        C: Indices of the loop partition.
        Ex: Indices of the exchange partition.
        method: One of `"linear"`, `"mi"`, `"mi_kraskov"`,
            `"transfer_entropy"`, or `"directed_information"`.
        p: VAR order for the linear estimator.

    Returns:
        An [`LResult`][ldtc.lmeas.estimators.LResult] with point
        estimates and `(lo, hi)` CI bounds for each metric.

    Raises:
        ValueError: If `method` is not supported.

    Example:
        ```python
        import numpy as np
        from ldtc.lmeas.estimators import estimate_L

        X = np.random.randn(200, 6)
        res = estimate_L(X, C=[0, 1, 2], Ex=[3, 4, 5], method="linear")
        print(res.L_loop, res.L_ex)
        ```
    """
```

Notes:

- The first line is an **imperative summary** ending in a period.
- Leave one blank line between the summary and the extended description.
- Use these sections in order: `Args:`, `Returns:`, `Yields:`,
  `Raises:`, `Note:`, `Warning:`, `Example:`. Skip any that don't apply.
- **Don't repeat type annotations** inside `Args:`; the rendered API
  table pulls them from the function signature automatically.
- Inside `Example:`, use a fenced code block (` ```python `) with the
  imports needed to run the snippet so users can copy it directly.

### Class

```python
class FixedScheduler:
    """Fixed-interval scheduler for measurement loops.

    Enforces a constant sampling interval Δt and invokes a tick
    callback every period until stopped. Tracks jitter statistics and
    emits optional audit events through a user-provided hook (see
    paper §4.5 Δt governance).

    Attributes:
        dt: Current target period in seconds.
        stats: A [`TickStats`][ldtc.runtime.scheduler.TickStats]
            instance holding tick counts and jitter percentiles.

    Example:
        ```python
        from ldtc.runtime.scheduler import FixedScheduler

        sched = FixedScheduler(dt=0.01, tick_fn=lambda t: print(t))
        sched.start()
        try:
            time.sleep(0.05)
        finally:
            sched.stop()
        ```
    """
```

The class summary describes the type's purpose. Document construction
in `__init__` only when there is more to say than the signature already
conveys (set `merge_init_into_class: true` in mkdocstrings; already
configured).

### Module

Every module should open with a one-line summary, an extended
description, a `See Also:` cross-reference to the relevant paper
section, and (when illustrative) a small example:

```python
"""Lmeas: Estimators for loop and exchange influence.

Lightweight predictive-dependence estimators used to compute loop
influence `L_loop` and exchange influence `L_ex` over a C/Ex
partition. Includes linear (Granger-like) and mutual-information
methods, with optional TE/DI proxies. Confidence intervals are
produced via circular block bootstrap per window.

See Also:
    paper/main.tex - Criterion; Methods: Measurement & Attestation.
"""
```

### Private helpers

Underscore-prefixed members (`_helper`) are filtered out of the public
API site (mkdocstrings `filters: ["!^_"]`). Keep their docstrings
short (one line is usually enough), but do write them: contributors
inspect them in editors and during code review.

## Comments: explain *why*

!!! quote "Rule of thumb"
    Comments are most useful when they explain things the reader cannot
    learn from the code itself.

Good comments:

- Document a non-obvious invariant or constraint (for example, "LREG
  must remain write-only across all paths").
- Explain a trade-off between two reasonable approaches.
- Cite the paper section, an external spec, RFC, or upstream issue.
- Warn about a subtle ordering requirement (for example, partition must
  be frozen before applying Ω).

Bad comments (don't add them):

- Narrating what the next line does (`# increment counter`).
- Restating the function name (`# compute the indicator`).
- TODOs without an owner or issue link; open a tracking issue and link
  it instead.

When you find a redundant comment during a refactor, delete it. The
diff will be smaller and the code will be easier to read.

## Markdown: admonitions over blockquotes

Use Material admonitions for callouts. They render with an icon, a
colored block, and a collapsible variant:

```markdown
!!! note
    Plain note.

!!! tip "Pro tip"
    Custom-titled tip.

!!! warning
    Heads-up about a footgun (for example, "this invalidates the run").

!!! danger "Do not bypass"
    Reserved for measurement guardrails: never bypass LREG, Δt
    governance, or audit-chain checks in production code.

??? info "Click to expand"
    Collapsed by default. Useful for long worked examples.
```

Reserve plain Markdown blockquotes (`>`) for *quoted text* (a quote
from the paper, a user, or an upstream project). Don't use them for
tips or warnings.

## Cross-linking

Mkdocstrings plus autorefs lets you link to any documented symbol from
plain Markdown. Prefer these short forms:

```markdown
The [`estimate_L`][ldtc.lmeas.estimators.estimate_L] function returns
an [`LResult`][ldtc.lmeas.estimators.LResult]. Pair it with
[`m_db`][ldtc.lmeas.metrics.m_db] to compute the loop-dominance
margin in decibels.
```

Inside a docstring, plain backticks plus the qualified name are
typically enough; autorefs picks them up via signature annotations
(`signature_crossrefs: true`).

When linking to the paper, use a short text reference such as
"paper §4.2 (NC1)" or "Box 1a (Invalidations)" rather than page
numbers, which can drift between revisions.

## Code samples

- Always tag the language: ` ```python `, ` ```bash `, ` ```yaml `,
  ` ```text `.
- Prefer **runnable** snippets that include the imports needed to
  copy-paste them.
- For longer multi-step examples (a baseline run plus an Ω trial plus
  verification), lean on Material's `pymdownx.tabbed` to present the
  variants side by side.

## Page structure

A typical concept or guide page follows this skeleton:

1. `# Title`. H1 only on the page itself; the site nav supplies the
   parent heading.
2. **One-paragraph summary** of what this page covers and who it's for.
3. **Sections** (`##`, `###`) covering the topic in order of increasing
   depth. Lead with the simplest example.
4. **Next steps** at the bottom with cross-links to related pages, to
   keep the reader moving.

```markdown
## Next steps

- Run a baseline: [Getting Started](../getting-started.md)
- Read the verification flow: [Lifecycle](lifecycle.md)
- Calibrate thresholds: [Calibration](../guides/calibration.md)
- Inspect the API: [`estimate_L`][ldtc.lmeas.estimators.estimate_L]
```

## Linting

Docstrings are checked by Ruff with the Google convention enabled:

```bash
ruff check src/ldtc
```

The relevant rule set lives in `pyproject.toml` under
`[tool.ruff.lint]`. The site build also runs in **strict mode**
(`mkdocs build --strict`) on every push and pull request, so missing
cross-references and broken links fail CI.
