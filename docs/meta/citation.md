# Citation

If you use LDTC in academic work, a research artifact, or a
production deployment, please cite the software and the underlying
paper. The repository ships a `CITATION.cff` (Citation File Format)
at the root that GitHub renders into a structured citation widget.

## Recommended in-text reference

> Carey, O. (2025). *A verification harness for Loop-Dominance
> NC1/SC1 on a single machine* (Version 1.0.0). Zenodo.
> https://doi.org/10.5281/zenodo.17073880

## BibTeX

```bibtex
@software{carey_ldtc_2025,
  author       = {Owen Carey},
  title        = {{LDTC: Single-Machine, Real-Time Digital
                   Boundary Organism}},
  year         = {2025},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.17073880},
  url          = {https://github.com/ldtc-labs/ldtc},
  license      = {MIT}
}

@article{carey_ldtc_paper_2025,
  author = {Owen Carey},
  title  = {A verification harness for Loop-Dominance NC1/SC1 on a
            single machine},
  year   = {2025},
  note   = {Companion paper to the LDTC software release.}
}
```

## Citing a specific run

When you cite LDTC results, also cite the specific signed indicator
bundle that produced them. A bundle includes:

- The CBOR payload (`ind_*.cbor`) and its JSON mirror (`ind_*.jsonl`).
- The Ed25519 public key (`pub.pem`).
- The corresponding `audit.jsonl` and `manifest.json`.

This lets a third party reproduce the verification end to end. See
[Reporting and figures](../guides/reporting.md#regenerating-a-bundle-from-an-audit-log)
for the canonical regeneration command.

## Structured metadata

The repository ships
[`CITATION.cff`](https://citation-file-format.github.io/) at the
root. Tools such as Zenodo, GitHub, and Zotero pick it up
automatically. To export to other formats locally:

```bash
pip install cffconvert
cffconvert -if CITATION.cff -of bibtex -o ldtc.bib
cffconvert -if CITATION.cff -of apalike
```

## See also

- [Contributing](contributing.md) for how patches and forks should
  attribute upstream.
- [FAQ](faq.md#how-do-i-cite-ldtc) for the short version.
