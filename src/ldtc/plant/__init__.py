"""Plant models and adapters.

`plant` provides everything LDTC needs to interact with the system
under verification. The package keeps two stories deliberately separate:

- [`models`][ldtc.plant.models] is a small discrete-time software plant
  (`E` / `T` / `R` dynamics) and its data classes (`PlantParams`,
  `PlantState`, `Action`).
- [`scenarios`][ldtc.plant.scenarios] holds parameter presets for
  baseline, low-power, and hot-ambient runs.
- [`adapter`][ldtc.plant.adapter] is a thread-safe in-process adapter
  wrapping the software plant.
- [`hw_adapter`][ldtc.plant.hw_adapter] is a UDP / serial
  hardware-in-the-loop adapter that mirrors the in-process API.

Both adapters expose the same minimal surface:
[`read_state`][ldtc.plant.adapter.PlantAdapter.read_state],
[`write_actuators`][ldtc.plant.adapter.PlantAdapter.write_actuators],
and [`apply_omega`][ldtc.plant.adapter.PlantAdapter.apply_omega]. That
shared shape is what lets the [`omega`][ldtc.omega] modules work
unchanged across simulation and real hardware.
"""
