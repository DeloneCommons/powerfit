# Main molecular QTAIM benchmark data

This directory stores the completed PubChem-derived molecular benchmark used
for Experiment J.

## Current benchmark state

The committed benchmark is complete:

- 100 molecules total;
- 50 acyclic systems;
- 50 cyclic systems.

All rows in `systems_final.csv` now have committed downstream artifacts for
the frozen geometry/topology pipeline:

- `structures/` - optimized XYZ geometries used downstream;
- `molden/` - committed Molden wavefunction files;
- `qtaim/` - parsed QTAIM / critical-point JSON records extracted from
  Multiwfn;
- `multiwfn_raw/` - raw Multiwfn text logs for the main benchmark;
- `selection/` - deterministic PubChem-selection audit files, including the
  archived `systems.csv`, `systems_reserve.csv`, and selection metadata from
  the original PubChem-backed curation pass.

## Manifests

- `systems_final.csv` - full 100-system benchmark;
- `systems_final_acyclic.csv` - acyclic subset;
- `systems_final_cyclic.csv` - cyclic subset.

The old `systems_pending19.csv` helper manifest was removed because the
archive is no longer partial.

## Selection note

The benchmark was built from deterministic PubChem-backed searches followed
by local RDKit filtering and connectivity-SMILES deduplication. The
committed repository stores the selected systems and downstream artifacts;
it does not bundle any raw PubChem bulk dump.
