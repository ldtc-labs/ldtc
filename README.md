<p align="center">
  <img src="docs/assets/banner.jpg" alt="LDTC" width="800" />
</p>

<p align="center">
  <em>A falsifiable criterion and open verification harness for measuring self-maintenance.</em>
</p>

<p align="center">
  <a href="https://github.com/ldtc-labs/ldtc/actions/workflows/ci.yml"><img src="https://github.com/ldtc-labs/ldtc/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://github.com/ldtc-labs/ldtc/actions/workflows/release.yml"><img src="https://github.com/ldtc-labs/ldtc/actions/workflows/release.yml/badge.svg" alt="Release" /></a>
  <a href="https://pypi.org/project/ldtc/"><img src="https://img.shields.io/pypi/v/ldtc" alt="PyPI Version" /></a>
  <a href="https://pypi.org/project/ldtc/"><img src="https://img.shields.io/pypi/pyversions/ldtc" alt="Python Versions" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/pypi/l/ldtc" alt="License: MIT" /></a>
  <a href="https://docs.ldtc.dev/"><img src="https://img.shields.io/website?url=https%3A%2F%2Fdocs.ldtc.dev&label=docs" alt="Docs" /></a>
  <a href="https://doi.org/10.5281/zenodo.17073880"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.17073880.svg" alt="DOI" /></a>
</p>

<p align="center">
  <a href="https://docs.ldtc.dev/">Documentation</a> ·
  <a href="https://docs.ldtc.dev/getting-started/">Getting Started</a> ·
  <a href="https://docs.ldtc.dev/examples/">Examples</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Overview

LDTC is a minimal, substrate-agnostic verification harness for measuring loop dominance: the degree to which a system's predictive dependence is concentrated in a closed self-maintenance loop (Lloop) rather than in its open exchanges (Lexchange), summarized by the loop-dominance margin M in decibels. It evaluates the falsifiable NC1/SC1 criterion at fixed Δt, enforces guardrails through an enclave-protected LREG with hash-chained audit and Δt governance, and runs Ω-perturbation trials with device-signed indicators. The criterion originated in the Loop-Dominance Theory of Consciousness, which motivates the instrument and gives it its name; adopting the measure commits you to no position on consciousness. The toolkit includes a CLI, reproducible configuration profiles (R₀ through R*), and an optional hardware adapter for ingesting real telemetry.

## Features

- **Loop-dominance measurement:** Computes Lloop and Lexchange at fixed Δt using VAR-Granger and Kraskov k-NN mutual information.
- **C/Ex partitioning:** Deterministic partitioning with hysteresis and greedy ΔL loop-gain growth.
- **Guardrails and attestation:** LREG enclave, hash-chained audit log, Δt governance, and smell tests that can invalidate runs.
- **Device-signed indicators:** Ed25519-signed derived indicators (NC1, SC1, Mq, counters); raw LREG values are never exported.
- **Ω perturbation battery:** Power sag, sustained ingress flood, control outage (designed SC1 failure), command conflict, and exogenous subsidy trials.
- **Adversarial gaming battery:** Replayed actuation tapes, hidden-tether (wizard-of-oz) control, and oscillator telemetry inflation; the harness must refuse to certify all three (NC1 fails or the run is invalidated).
- **Emergence under learning:** A policy network trained from scratch (survival, service, and homeostasis reward; no loop-dominance term) whose checkpoints are measured by the production harness, with matched state-independent ablations of the trained policy.
- **Refusal semantics:** An arbiter refuses risky commands when M is below threshold and measures refusal latency.
- **Reporting and figures:** Timeline plots, SC1 tables, and verification bundles under `artifacts/`.
- **Reproducible configs:** R₀ defaults, negative controls, and example R* profiles for calibration.

## Quick Start

### Installation

```bash
pip install ldtc
```

### Usage

```bash
# Run a baseline NC1 verification
ldtc run --config configs/profile_r0.yml

# Run an Ω power-sag perturbation trial
ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10
```

## Documentation

Visit [docs.ldtc.dev](https://docs.ldtc.dev/) for the full documentation, including getting started guides, core concepts, calibration and reporting guides, API reference, and Jupyter notebook examples.

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, coding standards, and guidelines for submitting pull requests.

## License

[MIT](LICENSE)
