# Data

Frozen input and intermediate data used by the paper artifact live here.

## Read these directories in this order

1. [qtaim_main/README.md](qtaim_main/README.md) — the full 100-system molecular
   benchmark used in Experiment J.
2. [qtaim_showcase/README.md](qtaim_showcase/README.md) — the small curated
   showcase pack used for the J4c mechanistic panel.
3. [proatomic/README.md](proatomic/README.md) — isolated-atom reference data and
   the frozen pair-law lookup used in J2/J3.

## Directory roles

- `qtaim_main/` — full benchmark manifests, committed geometries, Molden files,
  parsed QTAIM JSON, raw Multiwfn logs, and deterministic selection audit
  records.
- `qtaim_showcase/` — fixed downstream showcase cases for the curated J4c panel.
- `proatomic/` — isolated-atom PySCF/Multiwfn outputs and the frozen
  promolecule-based separator lookup.

## Important note

This repository stores the selected molecular systems and the downstream
artifacts used by the paper. It does not bundle a raw PubChem bulk dump.
