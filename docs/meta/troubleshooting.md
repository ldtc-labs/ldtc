# Troubleshooting

Common error messages from running, building, and verifying LDTC,
with the smallest fix that works. If you hit something that is not
covered here, please open an issue with the full traceback.

## Run-time errors

### `RuntimeError: Δt guard tripped: jitter exceeded threshold`

The fixed-interval scheduler measured a jitter percentile higher than
the configured ceiling. The run is invalidated.

Causes:

- The host is overloaded or running on a noisy laptop battery.
- The plant adapter is doing blocking I/O inside the tick callback.
- Δt is too small for the chosen `tick_fn` workload.

Fixes:

- Run on a quieter host, or pin the process to a CPU and disable
  power management (`sudo cpufreq-set -g performance`).
- Move blocking I/O out of the tick. Use a queue and read it
  non-blockingly inside the tick.
- Increase Δt in the CLI (`--dt 0.05`) or the run config; recalibrate
  thresholds afterwards.

### `ValueError: derived contains raw LREG key 'L_loop'`

The exporter's guard caught a leak. Some code path tried to put a
raw `𝓛` field into the signed indicator payload.

Fixes:

- Build the payload only via [`LREG.derive`][ldtc.guardrails.lreg.LREG.derive].
- Do not pass intermediate dicts from estimators directly into the
  exporter. The reason this is fatal is documented in
  [`ldtc.attest.exporter`][ldtc.attest.exporter].

### `RefusalArbiter` returns `RefusalDecision.refuse` unexpectedly

Either the boundary policy is too strict or the controller is
genuinely overshooting.

Fixes:

- Inspect the audit log entries around the refusal:
  `rg refusal_decided artifacts/audit.jsonl | tail`.
- Tune the boundary thresholds in your run config; do *not* relax
  them inside [`ldtc.arbiter.policy`][ldtc.arbiter.policy].
- If you are running an `Ω` trial, refusal is the expected behavior;
  it is the SC1 path under `command_conflict`.

### Audit chain is broken at end of run

Reported by [`audit_chain_broken`][ldtc.guardrails.smelltests.audit_chain_broken]
in the post-run smell tests. This invalidates the run.

Causes and fixes:

- The audit file was written by two processes at once. Use one
  process per output directory.
- The file was edited by hand or partially copied during the run.
  Don't do this; the chain is meant to be tamper-evident.
- The disk filled up mid-write. Free space and re-run.

## Verification errors

### `signature verification failed`

The verifier's public key does not match the private key used during
the run, or the indicator file was modified after signing.

Fixes:

- Pass the correct `--pub` path to the verifier (the one that pairs
  with the private key in the run's `--key` argument).
- Confirm the `.cbor` file is unchanged: `shasum -a 256
  artifacts/indicators/*.cbor` before and after copy.

### Verifier prints `nc1=False` but the plot looks fine

`M_db` is the loop-dominance margin in decibels. The verifier checks
**`nc1_pass`** which is the run-time gate at every window, and is
only set when `M >= Mmin` for `>= Mq` consecutive windows.

Fixes:

- Look at the audit log for `window_measured` events: was `M_db`
  above `Mmin` *every* window in the steady state, or only on
  average?
- Re-run with [calibration](../guides/calibration.md) to make sure
  `Mmin` matches the reference profile R*.

## Build / install errors

### `mkdocs build` fails with cairo or cairosvg errors

Symptom (typical):

```text
OSError: no library called "cairo-2" was found
no library called "libcairo-2" was found
```

Cause: the `mkdocs-material[imaging]` social plugin needs the
`cairo` system library. macOS's bundled Python 3.9 cannot find
Homebrew's `cairo` install at `/opt/homebrew/lib`.

Fix:

```bash
rm -rf .venv
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs]"
make docs
```

If you cannot use Homebrew Python (CI on a managed runner, for
example), set `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` for the
build step. This is a workaround; recreating the venv with the right
Python is the durable fix.

### `mkdocs build --strict` aborts with autoref warnings

Symptom:

```text
WARNING -  mkdocs_autorefs: Could not find cross-reference target 'ldtc.foo'
```

Causes:

- The symbol moved or was renamed; the docstring still points to the
  old path.
- A docstring references a private name (`_helper`) which is filtered
  out of the API site.

Fix:

- Update the cross-reference to the new symbol path.
- For private helpers, link to the public module
  ([`ldtc.foo`][ldtc.lmeas]) and describe the helper inline rather
  than linking to it.

### `pip install -e ".[dev,docs]"` is slow on first install

Expected. The docs extra pulls in `mkdocs-material[imaging]`, which
in turn installs `pillow` and `cairosvg`. This only happens once per
venv.

### Tests pass locally but fail in CI

Things to check, in order:

- Random seeds: confirm the test sets a seed
  (`np.random.seed(...)`). The estimators are bootstrap-based.
- Wall-clock asserts: avoid `assert elapsed < 0.1`; CI runners are
  noisy. Use the
  [`TickStats`][ldtc.runtime.scheduler.TickStats] percentiles instead.
- File ordering: `os.listdir` is not sorted. Sort explicitly when a
  test compares lists.

## Performance

### `make test` is slow

The property tests over the partition algebra dominate runtime.
Filter to a fast subset while iterating:

```bash
pytest -k "not property" -q
```

Then run the full suite before pushing.

### Estimators take longer than Δt

The harness will trip the Δt guard. Either reduce the per-window
sample size, switch to a cheaper estimator (`method="linear"`), or
increase Δt in your config and recalibrate.

## See also

- [FAQ](faq.md) for higher-level questions.
- [Style guide](style-guide.md) if a docstring change broke the
  build.
- [Hardware adapter guide](../guides/hardware.md) for adapter-side
  errors.
