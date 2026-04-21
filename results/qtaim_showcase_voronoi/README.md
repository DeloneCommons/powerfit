# QTAIM vs Voronoi showcase comparison

This directory contains a first-pass comparison between:
- QTAIM BCP support graphs from `data/qtaim_showcase/qtaim/*.json`
- ordinary Voronoi adjacency from `pyvoro2`
- one-shot power-fit Laguerre adjacency using projected BCP fractions

Files:
- `REPORT.md`: compact narrative summary of the first-pass showcase findings.
- `summary.csv`: per-system metrics
- `bcp_projection.csv`: per-BCP projected connector fractions and off-axis distances
- `voronoi_edges.csv`: raw ordinary-Voronoi face diagnostics
- `powerfit_edges.csv`: raw one-shot powerfit face diagnostics
- `symmetry_breaking_diffs.csv`: raw/visible edge-set differences between idealized and broken variants

Notes:
- The current visible-edge analysis uses `intersection_inside` as the base visibility criterion.
- The `intersection_edge_min_dist` values in this showcase foreshadow the clearance diagnostic that is formalized later in the J4a/J4b local-diagnostic branch.
