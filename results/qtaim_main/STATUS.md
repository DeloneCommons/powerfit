# Experiment J status (full benchmark refresh)

The molecular QTAIM benchmark is complete at **100/100 systems**. The archived
J1--J4 outputs under `results/qtaim_main/` have been refreshed on the frozen
100-system benchmark.

## Benchmark size

- processed systems: 100/100
- acyclic systems: 50
- cyclic systems: 50
- skipped rows: 0

## J1: dataset/topology audit

- total QTAIM BCP edges: 3975
- total RCP count: 442
- total CCP count: 12
- molecules with at least one RCP: 90.0%
- molecules with at least one CCP: 9.0%
- molecules with at least one nonbonded BCP: 84.0%
- bonded / nonbonded BCP edges: 3703 / 272 (93.2% / 6.84%)
- median BCP off-axis distance, all / bonded / nonbonded: 0.00465 / 0.00448 /
  0.15077 A
- fraction with off-axis <= 0.02 A, all / bonded / nonbonded: 91.57% / 98.22% /
  1.10%

## J2: true-support separator ladder

All edges:
- midpoint RMSE: 0.13324 A
- frozen proatomic RMSE: 0.04518 A
- frozen proatomic + one-shot powerfit RMSE: 0.04733 A
- QTAIM-target + one-shot powerfit ceiling RMSE: 0.01693 A

Bonded vs nonbonded split:
- bonded proatomic / ceiling RMSE: 0.04572 / 0.00623 A
- nonbonded proatomic / ceiling RMSE: 0.03715 / 0.06052 A
- heteronuclear proatomic better than midpoint: 99.73%
- clean connector-aligned heteronuclear subset (2437 edges, 99.9% bonded):
  ceiling RMSE 0.00602 A, realized fraction 1.000

## J3: candidate-supergraph recovery

Reference 5.0 A cutoff:
- raw recovered F1: 0.3391
- visible recovered F1: 0.8210
- bonded visible recovered F1: 0.99973
- nonbonded visible recovered F1: 0.2379
- heteronuclear visible recovered F1: 0.8909

Cutoff note:
- candidate coverage stays at 1.0 for 4.0 / 4.5 / 5.0 A on the full benchmark,
  so the cutoff sweep remains an inflation-stability story rather than a
  coverage-failure story.

## J4 overview

J4 is split into four synchronized pieces:

- **J4a** local theorem-to-code validation;
- **J4b** broad-dataset mask transfer and clearance ranking;
- **J4c** curated representability panel;
- **J4d** box-margin robustness.

### J4a: local theorem-to-code validation

- clipped analytic visibility matches `intersection_inside` exactly on all
  38,746 released faces;
- clipped analytic clearance matches `intersection_edge_min_dist` to machine
  precision on all 11,677 visible faces;
- maximum absolute clearance mismatch is 3.55e-15.

### J4b: mask transfer and clearance ranking

- J3 is the fixed-denominator recovery stage against the common 3975-edge
  QTAIM graph, whereas J4b scores realized-face diagnostics within each
  model's own archive.
- Realized truth pool in the released J4 archive: Voronoi 3973 overall / 270
  nonbonded, recovered powerfit 3975 overall / 272 nonbonded.

Raw vs visible graph agreement:
- Voronoi raw / visible F1: 0.3417 / 0.7964
- recovered powerfit raw / visible F1: 0.3391 / 0.8210

Clearance-only numerical cleanup:
- near-zero-clearance slivers removed: Voronoi 1, recovered powerfit 2
- visible-plus-cleanup recovered-powerfit F1: 0.8212

Clearance sweep:
- Voronoi F1 at 0.5 / 0.6 A: 0.9515 / 0.9701
- recovered powerfit F1 at 0.5 / 0.6 A: 0.9789 / 0.9813
- recovered powerfit nonbonded F1 at 0.5 A: 0.7416
- recovered powerfit heteronuclear F1 at 0.5 A: 0.9886

Visible-face clearance distributions:
- bonded faces are almost degenerate because bonded recovery is already
  essentially exact;
- nonbonded visible faces show the important split: for Voronoi the median
  clearance is 0.798 A on QTAIM-supported faces versus 0.360 A on surplus
  faces, and for recovered powerfit it is 0.678 A versus 0.228 A.

### J4c: curated representability panel

- methane is the screened-pair case: raw extra H--H faces disappear under
  visibility for both Voronoi and recovered powerfit;
- benzene is the raw-symmetry case: exact symmetry mainly changes raw
  overconnection, while visible graphs stay stable and the remaining powerfit
  extra face is a near-zero-clearance sliver;
- adamantane is the cage-like case: a small visible extra-face tail survives,
  but those extras have systematically smaller clearance than true visible
  edges.

### J4d: box-margin robustness

- all reported visible-F1, clearance@0.5-F1, and visible-nonbonded
  clearance-AP values are numerically identical across the 3 / 5 / 7 / 10 A
  margins;
- visible-nonbonded clearance AP stays at 0.707 for Voronoi and 0.830 for
  recovered powerfit;
- analytic margin-safe fraction on visible nonbonded faces is 1.000 for both
  models at every tested margin.

## Practical interpretation

- J1 confirms that the molecular benchmark is not topologically trivial and
  that pooled connector alignment is dominated by the bonded majority.
- J2 shows that the frozen proatomic local rule already closes most of the
  midpoint-to-ceiling gap on the full benchmark.
- J3 remains the main molecular quantitative result: from a generic excessive
  graph plus frozen local targets, the pipeline recovers essentially all bonded
  support after visibility masking.
- J4a shows that the clipped local formulas are exactly the diagnostics being
  computed on the released archive.
- J4b shows that most residual mismatch is concentrated in a proxy- and
  representability-limited nonbonded regime and can be ranked better by
  clearance than by simple distance or area.
- J4c explains what that residual tail looks like geometrically.
- J4d shows that the clipped-box robustness term does not drive the reported
  hard-subset decisions on this benchmark.
