# ldtc.plant

The plant: in-process software model and a hardware-in-the-loop
adapter that speaks UDP / serial. Both adapters satisfy the same
[`AdapterProtocol`][ldtc.cli.main.AdapterProtocol] used by the
CLI, so all `Ω` modules and indicators work unchanged.

| Module | Headline symbols | Use it for |
| ------ | ---------------- | ---------- |
| [`models`](#models) | [`Plant`][ldtc.plant.models.Plant], [`PlantState`][ldtc.plant.models.PlantState], [`PlantParams`][ldtc.plant.models.PlantParams], [`Action`][ldtc.plant.models.Action] | Tiny `(E, T, R, demand, io, H)` dynamics with controllable harvest, demand, and Ω hooks. |
| [`scenarios`](#scenarios) | [`default_params`][ldtc.plant.scenarios.default_params], [`low_power_params`][ldtc.plant.scenarios.low_power_params], [`hot_ambient_params`][ldtc.plant.scenarios.hot_ambient_params] | Preset [`PlantParams`][ldtc.plant.models.PlantParams] for the baseline, low-power, and hot-ambient scenarios used in figures and CLI profiles. |
| [`adapter`](#adapter) | [`PlantAdapter`][ldtc.plant.adapter.PlantAdapter] | Wraps `Plant` to expose `read_state` / `write_actuators` / `apply_omega` to the CLI. |
| [`hw_adapter`](#hw_adapter) | [`HardwarePlantAdapter`][ldtc.plant.hw_adapter.HardwarePlantAdapter] | Same API over UDP or serial; for hardware-in-the-loop runs. See [Hardware in the loop](../guides/hardware.md). |

::: ldtc.plant
    options:
      members: false
      show_root_heading: false
      show_source: false

## models

::: ldtc.plant.models

## scenarios

::: ldtc.plant.scenarios

## adapter

::: ldtc.plant.adapter

## hw_adapter

::: ldtc.plant.hw_adapter
