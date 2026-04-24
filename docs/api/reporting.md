# ldtc.reporting

Paper-quality figure and table generation. Reads only the audit
log; cannot reach into [`LREG`][ldtc.guardrails.lreg.LREG], so
nothing it produces leaks raw `𝓛`.

| Module | Headline symbols | Use it for |
| ------ | ---------------- | ---------- |
| [`style`](#style) | [`COLORS`][ldtc.reporting.style], [`apply_matplotlib_theme`][ldtc.reporting.style.apply_matplotlib_theme], [`apply_graphviz_theme`][ldtc.reporting.style.apply_graphviz_theme], [`new_graph`][ldtc.reporting.style.new_graph] | The shared palette and matplotlib / graphviz themes. |
| [`tables`](#tables) | [`write_sc1_table`][ldtc.reporting.tables.write_sc1_table] | Per-trial SC1 results CSV: `eta, delta, tau_rec, M_post, pass`. |
| [`timeline`](#timeline) | [`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline] | Paper-style timeline: normalized `𝓛`, `M (dB)`, `Mmin` rule, shaded `Ω` window, audit-event tick rug. |
| [`artifacts`](#artifacts) | [`bundle`][ldtc.reporting.artifacts.bundle] | Convenience entry point that turns one audit log into a complete frozen artifact directory (timeline + table + manifest + config snapshot + notice). |

See [Reporting](../guides/reporting.md) for the operator guide.

::: ldtc.reporting
    options:
      members: false
      show_root_heading: false
      show_source: false

## style

::: ldtc.reporting.style

## tables

::: ldtc.reporting.tables

## timeline

::: ldtc.reporting.timeline

## artifacts

::: ldtc.reporting.artifacts
