# J. Molecular QTAIM benchmark

Experiment J is the main empirical branch of the manuscript. In the frozen
artifact it is easiest to read as a staged ladder: J1 audit, J2 true-support
separator ladder, J3 candidate-graph recovery, and J4a--J4d diagnostics.

## Stage crosswalk

| Stage | Primary script or helper | Results root | Role |
|---|---|---|---|
| J1 | `scripts/qtaim/analyze_qtaim_dataset_audit.py` | `results/qtaim_main/J1_dataset_audit/` | topology prevalence and proxy-quality audit |
| J2 | `scripts/qtaim/analyze_qtaim_true_support_ladder.py` | `results/qtaim_main/J2_true_support_ladder/` | separator-quality ladder on true support |
| J3 | `scripts/qtaim/analyze_qtaim_candidate_recovery.py` | `results/qtaim_main/J3_candidate_recovery_refresh/` | recovery from a generic excessive graph |
| J4a | `scripts/qtaim/validate_local_support_diagnostics.py` | `results/qtaim_main/J4_local_diagnostic_validation/` | theorem-to-code validation of clipped visibility and clearance |
| J4b | `scripts/qtaim/analyze_qtaim_mask_transfer.py` | `results/qtaim_main/J4_mask_transfer_refresh/` | broad-dataset transfer of visibility and clearance diagnostics |
| J4c | `scripts/make_j4_geometry_cases.py` | `data/qtaim_showcase/` + `results/qtaim_showcase_voronoi/` | representative geometry cases used by the manuscript figure |
| J4d | `scripts/qtaim/analyze_qtaim_box_margin_sensitivity.py` | `results/qtaim_main/J4_box_margin_summary_refresh/` | padded-box robustness summary across multiple J4b reruns |

## Companion helpers and inputs

| Piece | Path |
|---|---|
| Frozen experiment-J defaults | `experiments/configs/qtaim_molecular.yaml` |
| Existing local separator analysis | `scripts/qtaim/analyze_qtaim_proatomic.py` |
| Existing showcase Voronoi/powerfit comparison | `scripts/qtaim/compare_qtaim_voronoi.py` |
| Local analytic formulas used by J4a/J4b | `scripts/qtaim/local_support.py` |
| Main manifest | `data/qtaim_main/systems_final.csv` |
| Acyclic-only manifest | `data/qtaim_main/systems_final_acyclic.csv` |
| Cyclic-only manifest | `data/qtaim_main/systems_final_cyclic.csv` |
| Experiment-J results guide | `results/qtaim_main/README.md` |

## Current status

- the molecular benchmark is complete at 100/100 systems;
- current manuscript-facing J3/J4 roots use the synchronized `*_refresh` result
  branches;
- the 5.0 A candidate graph remains the reference excessive graph, while 4.0
  and 4.5 A remain deliberate undercoverage ablations;
- J3 is the fixed-denominator recovery stage against the common 3975-edge
  QTAIM graph, whereas J4b and J4d score diagnostics within each model's
  realized-face archive;
- J4a validates the clipped local formulas directly on the released edge-level
  archive, J4b carries the quantitative transfer story, J4c carries the
  representative-geometry figure, and J4d confirms box-margin stability.

Historical J3/J4 roots and the old representability-panel analysis are not part
of this released paper artifact.
