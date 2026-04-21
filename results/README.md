# Results

Archived benchmark outputs used to build the manuscript figures and tables live
here. These files are part of the frozen paper artifact, not a scratch
workspace.

## Read this directory in this order

1. [qtaim_main/README.md](qtaim_main/README.md) — Experiment J, the main
   molecular benchmark branch.
2. The synthetic result roots listed below for Experiments A--H.
3. `qtaim_showcase_voronoi/` — fixed showcase comparisons used by the J4
   geometry figure.

## Result roots by manuscript label

| Label | Results root | Purpose |
|---|---|---|
| A | `exact_recovery/` | exact synthetic recovery control |
| B | `noise_robustness/` | noise and contamination robustness |
| C | `missing_data/` | identifiability under row loss |
| C (figure) | `missing_data_manuscript/` | dense sweep used only for the manuscript figure |
| D | `infeasible/` | hard equality/interval feasibility stress |
| E | `active_set/` | supergraph inputs and active-set refinement |
| F | `periodic/` | periodic wrong-image stress tests |
| G | `model_mismatch/` | structured mismatch under correct support |
| H | `supergraph_mismatch/` | structured mismatch under support uncertainty |
| J | `qtaim_main/` | molecular QTAIM benchmark |

## Conventions

- Each current experiment family owns one result root.
- Archived primary outputs use generic filenames such as `runs.csv`,
  `summary.csv`, and `metadata.json`.
- Analysis subdirectories are kept only when they contain manuscript-facing
  derived artifacts.
- Historical side studies and superseded branches are not part of the canonical
  result read path for this released paper artifact.
