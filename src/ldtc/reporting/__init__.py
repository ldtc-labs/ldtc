"""Reporting helpers for verification artifacts.

`reporting` is the last stop in an LDTC run: it turns the audit log
into the human-readable artifacts the rest of the world sees, without
ever leaking raw `𝓛` values or CI bounds:

- [`style`][ldtc.reporting.style] holds Matplotlib and Graphviz theming
  (palette, fonts, vector-friendly defaults).
- [`tables`][ldtc.reporting.tables] provides CSV writers for SC1
  tables; they refuse to emit raw LREG fields.
- [`timeline`][ldtc.reporting.timeline] renders audit-driven timelines
  (`M (dB)`, normalized `𝓛`, `Ω` shading).
- [`artifacts`][ldtc.reporting.artifacts] is the end-to-end bundle
  builder: timeline, SC1 table, and manifest from one audit log.

Together, these modules render a publication-style timeline, a small
manifest, and an SC1 results CSV. Everything they emit is locked to
read-only on POSIX-like filesystems so an artifact directory can be
treated as a frozen demo result.
"""
