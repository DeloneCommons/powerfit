# Experiment J results

This directory stores the current outputs for the molecular QTAIM benchmark, the
main empirical branch of the paper.

## Read this directory in this order

1. `STATUS.md` — one-page synopsis of the frozen 100-system benchmark.
2. `J1_dataset_audit/` — topology prevalence and BCP projection quality.
3. `J2_true_support_ladder/` — separator-quality ladder on true QTAIM support.
4. `J3_candidate_recovery_refresh/` — recovery from a generic excessive
   candidate graph; this is the current J3 root used by manuscript tables.
5. `J4_local_diagnostic_validation/` — **J4a**, theorem-to-code validation of
   clipped visibility and clearance.
6. `J4_mask_transfer_refresh/` — **J4b**, broad-dataset transfer of visibility
   and clearance diagnostics; this is the current J4b root used by manuscript
   tables and figures.
7. `J4_box_margin_summary_refresh/` — **J4d**, robustness check for the
   padded-box clipping margin.
8. `J4_mask_transfer_margin3_refresh/`, `J4_mask_transfer_margin7_refresh/`, and
   `J4_mask_transfer_margin10_refresh/` — supporting J4d reruns.

The older plain `J3_candidate_recovery/`, `J4_mask_transfer/`, and
`J4_representability_panel/` roots are superseded branches and are not part of
this released paper artifact.

## J-stage crosswalk

| Stage | Directory | Role in manuscript |
|---|---|---|
| J1 | `J1_dataset_audit/` | explains topology complexity and bonded/nonbonded proxy quality |
| J2 | `J2_true_support_ladder/` | evaluates separator targets on true QTAIM support |
| J3 | `J3_candidate_recovery_refresh/` | tests support recovery from a generic excessive graph |
| J4a | `J4_local_diagnostic_validation/` | validates the clipped local formulas against tessellation outputs |
| J4b | `J4_mask_transfer_refresh/` | quantifies the broad-dataset visibility and clearance story |
| J4c | `data/qtaim_showcase/` + `results/qtaim_showcase_voronoi/` | supplies the representative-geometry cases drawn by `scripts/make_j4_geometry_cases.py` |
| J4d | `J4_box_margin_summary_refresh/` | shows that the reported J4 diagnostics are stable across box margins |

## Important J3/J4 interpretation note

J3 is the fixed-denominator support-recovery experiment against the full
3975-edge QTAIM graph. J4b and J4d answer a different question: conditional on
a face being realized by a given model, do visibility and clearance behave like
useful diagnostics? Their precision/recall/F1 summaries are therefore computed
within each model's realized-face archive. In the frozen archive this realized
truth pool is 3973 overall / 270 nonbonded for Voronoi and 3975 overall / 272
nonbonded for recovered powerfit.

## Common file roles

Most J-stage directories use the same pattern:

- `REPORT.md` — compact narrative summary
- `summary.json` or stage-specific summary CSVs — machine-readable aggregates
- `edge_level.csv` / `molecule_level.csv` / subset summaries — exported detail
  tables used by the manuscript tables and figures
