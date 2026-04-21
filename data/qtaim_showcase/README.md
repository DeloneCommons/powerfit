# QTAIM showcase data

This directory stores the small fixed showcase pack used for the curated J4
representability panel.

## Frozen showcase contents

- `systems.csv` - downstream manifest for the fixed showcase cases;
- `structures/` - committed XYZ geometries used for the showcase analysis;
- `molden/` - committed Molden wavefunction files;
- `qtaim/` - parsed Multiwfn topology JSON records;
- `multiwfn_run_summary.csv` - one-line run summary for the committed
  topology extraction.

## Important geometry note

The showcase XYZ files are not treated as geometry-optimization outputs.
Several cases were committed deliberately as idealized or symmetry-broken
analysis geometries in order to probe screened pairs, symmetry sensitivity,
and cage-like higher-order topology. Therefore the archive no longer keeps a
`geomopt/` placeholder directory.

## Raw logs

The showcase does not commit a placeholder `multiwfn_raw/` directory. If the
showcase topology extraction is rerun locally, the helper script can rebuild
raw logs transiently, but the parsed JSON files remain the paper-facing data
products.
