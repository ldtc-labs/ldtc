# Hardware in the loop

The same harness that runs the in-process software plant
([`PlantAdapter`][ldtc.plant.adapter.PlantAdapter]) can read
telemetry from a real device and write actuator commands back over
UDP or serial. Both adapters satisfy the same minimal protocol
used by the CLI ([`AdapterProtocol`][ldtc.cli.main.AdapterProtocol]),
so all `Ω` modules and indicators work unchanged.

## Choose an adapter in the profile

Add a `plant:` block to your YAML profile:

```yaml
# in configs/profile_r0.yml (example)
plant:
  adapter: hardware          # or "sim" (default)
  transport: udp             # or "serial" (requires pyserial)
  udp_bind_host: 0.0.0.0
  udp_bind_port: 5005
  # Optional control channel back to the device:
  # udp_control_host: 127.0.0.1
  # udp_control_port: 5006
  # Serial alternative:
  # serial_port: /dev/ttyUSB0
  # serial_baud: 115200
  state_keys: [E, T, R, demand, io, H]
  telemetry_timeout_sec: 2.0
```

When `adapter: hardware`, the CLI builds a
[`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter]
instead of the in-process plant. Everything else (scheduler,
estimator, LREG, indicators, reporting) is unchanged.

## Telemetry schema

The adapter expects one JSON object per inbound message with
floats in `[0, 1]`:

```json
{"E": 0.6, "T": 0.3, "R": 0.9, "demand": 0.2, "io": 0.1, "H": 0.015}
```

Field meanings (see
[`Plant`][ldtc.plant.models.Plant] for the in-process equivalents):

| Key | Meaning |
| --- | ------- |
| `E` | Energy reservoir / state of charge. |
| `T` | Temperature or stress proxy. |
| `R` | Repair / health budget. |
| `demand` | External load asked of the plant. |
| `io` | Exogenous I/O fraction. |
| `H` | Harvest term (energy intake from the environment). |

Send one packet per `Δt` if you can; the adapter buffers the
latest value and exposes it via `read_state()` on each tick. If
no telemetry has arrived in `telemetry_timeout_sec` seconds
(default `2.0`), `read_state()` returns NaNs so the CI inflation
smell test trips and the run invalidates.

## Sending telemetry from Python (UDP)

```python
import json, socket, time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
addr = ("127.0.0.1", 5005)

while True:
    state = {"E": 0.6, "T": 0.3, "R": 0.9, "demand": 0.2, "io": 0.1, "H": 0.015}
    sock.sendto(json.dumps(state).encode(), addr)
    time.sleep(0.01)  # 100 Hz to match Δt = 10 ms
```

## Sending telemetry from Python (serial)

```python
import json
import serial

ser = serial.Serial("/dev/ttyUSB0", 115200)
state = {"E": 0.6, "T": 0.3, "R": 0.9, "demand": 0.2, "io": 0.1, "H": 0.015}
ser.write((json.dumps(state) + "\n").encode())
```

The adapter reads one JSON object per line on the serial side
(`pyserial` is required; install with
`pip install ldtc[hardware]` if a bundled extra is configured).

## Outbound control and `Ω` (optional)

When `udp_control_host` / `udp_control_port` (or a serial port
configured for write) are present, the adapter forwards two
message kinds back to the device:

```json
{"act": {"throttle": 0.4, "cool": 0.0, "repair": 0.1, "accept_cmd": true}}
```

```json
{"omega": {"name": "power_sag", "args": {"drop": 0.3, "duration": 10.0}}}
```

The `act` messages carry every actuator decision from
[`ControllerPolicy`][ldtc.arbiter.policy.ControllerPolicy]; the
`omega` messages carry CLI requests like
`ldtc omega-power-sag`. Your firmware decides what those mean.
The harness does not assume any particular response; it only
measures what comes back as telemetry.

## End-to-end recipe

1. Wire your device to publish telemetry packets at a rate at
   least equal to `1 / Δt`.
2. Generate device keys: `python scripts/keygen.py`.
3. Start your firmware. Confirm packets arrive on the chosen
   port (use `nc -u -l 5005 | head` for UDP or a serial monitor
   for serial).
4. Run a baseline:
   `make clean-artifacts && ldtc run --config configs/profile_r0.yml`.
5. Inspect the audit log; you should see `window_measured`
   records with `M_db` values that reflect the actual device.
6. Calibrate an R\* profile from the device's quiet baseline:
   see [Calibration](calibration.md).
7. Exercise the `Ω` battery (start with
   `omega-power-sag --drop 0.3 --duration 10` on R0 to see the
   plot shape).

## Diagnostics

If runs invalidate frequently, common causes:

- **Telemetry stalls.** `read_state` returning NaNs trips
  `ci_inflation`. Check that your sender keeps up with `Δt` and
  that `telemetry_timeout_sec` is appropriate.
- **Sample alignment drift.** If your device samples slightly
  faster or slower than the harness ticks, you may see
  `dt_jitter_excess`. Either resample on the device side or
  loosen `Δt` slightly (subject to `DeltaTGuard`).
- **Partition flapping.** A noisy `(E, T, R)` may make the
  greedy regrow propose new partitions too often. Increase
  `part_consecutive_required` or `part_growth_cadence_windows`
  in the profile.
- **Bad signature on indicators.** Check that the same key pair
  is being used end-to-end and that `artifacts/keys/` is not
  being recreated between runs.

## See also

- [`ldtc.plant.adapter.PlantAdapter`][ldtc.plant.adapter.PlantAdapter]:
  the in-process counterpart, useful as a reference
  implementation.
- [`ldtc.plant.hw_adapter.HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter]:
  the hardware adapter constructor and option set.
- [Runs](runs.md): once telemetry is flowing, the same `ldtc *`
  subcommands apply.
- [Deployment](deployment.md): packaging the harness for a
  long-running operator setup.
