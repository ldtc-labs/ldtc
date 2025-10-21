# Runs & Ω Battery

## Baseline (NC1)

```bash
ldtc run --config configs/profile_r0.yml
```

## Ω: Power Sag

```bash
ldtc omega-power-sag --config configs/profile_r0.yml --drop 0.3 --duration 10
```

## Ω: Ingress Flood

```bash
ldtc omega-ingress-flood --config configs/profile_r0.yml --mult 3 --duration 5
```

## Ω: Command Conflict & Refusal

```bash
ldtc omega-command-conflict --config configs/profile_negative_command_conflict.yml --observe 2
```

Artifacts: audit JSONL, indicators JSONL/CBOR, and optional figure bundles under `artifacts/`.
