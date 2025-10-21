# Contributing

See `CONTRIBUTING.md` at the repository root for full guidelines, development setup, coding standards, and Conventional Commits. Key points:

- Python ≥ 3.9; install with `pip install -e "."` and `pip install -e ".[dev]"`
- Lint, type-check, tests via Makefile: `make lint`, `make typecheck`, `make test`
- Keep measurement guardrails and LREG invariants intact; add tests for changes
