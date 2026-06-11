"""LDTC: a real-time NC1/SC1 verification harness.

LDTC (Loop-Dominance Theory of Consciousness) is a single-machine
harness for falsifying or accepting the *closed-loop* (NC1) and
*steady-state under perturbation* (SC1) criteria from the LDTC paper.
The package is split into small, focused subpackages that mirror the
paper's section structure:

| Subpackage | Responsibility |
| ---------- | -------------- |
| `runtime` | Fixed-Δt scheduler, window utilities, and timing guards. |
| `lmeas` | Loop / exchange influence (𝓛) estimators, metrics, diagnostics, and partition management. |
| `arbiter` | Refusal arbiter and controller policy that decide whether a step may proceed. |
| `guardrails` | Audit log, Δt governance, LREG (live registry), and smell-tests. |
| `attest` | Device-signed derived indicators and key handling. |
| `reporting` | Timelines, tables, and run bundles for human and machine consumption. |
| `omega` | Perturbation primitives (the Ω battery: power sag, ingress flood, command conflict, ...). |
| `plant` | Software and hardware adapters and small process models. |

The CLI entrypoint `ldtc.cli.main` orchestrates these pieces into a
verification *run* that produces device-signed indicator artifacts and a
human-readable timeline.

Example:
    Run a baseline verification with the included R0 profile:

    ```bash
    python -m ldtc.cli.main run --config configs/profile_R0.yml
    ```

    Then inspect indicators:

    ```python
    import json
    from pathlib import Path

    latest = sorted(Path("artifacts/runs").glob("*/indicators/*.json"))[-1]
    print(json.loads(latest.read_text())["indicators"])
    ```

Notes:
    The package version is exposed as `ldtc.__version__` and is the
    single source of truth used by `python -m ldtc.cli.main --version`,
    the docs site, and `pyproject.toml` (kept in sync via the
    `semantic_release.version_variables` configuration).

See Also:
    Online docs: <https://docs.ldtc.dev/>.
    The paper (`paper/main.tex`) for the formal definitions of NC1, SC1,
    Mq, ε, τ_rec, and σ.
"""

from __future__ import annotations

__all__ = [
    "__version__",
]

__version__ = "1.0.0"
