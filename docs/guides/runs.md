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

## Hardware-in-the-loop (optional)

Select the hardware adapter and UDP telemetry in your config:

```yaml
# in configs/profile_r0.yml (example)
plant:
  adapter: hardware        # or "sim" (default)
  transport: udp           # or "serial" (requires pyserial)
  udp_bind_host: 0.0.0.0
  udp_bind_port: 5005
  # Optional control channel back to device
  # udp_control_host: 127.0.0.1
  # udp_control_port: 5006
  telemetry_timeout_sec: 2.0
```

Send telemetry as JSON over UDP with keys `E,T,R,demand,io,H` in [0,1]. Example:

```python
import socket, json
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(json.dumps({"E":0.6,"T":0.3,"R":0.9,"demand":0.2,"io":0.1,"H":0.015}).encode(), ("127.0.0.1", 5005))
```

The CLI ingests these values through the same LREG/Ω/attestation path.
