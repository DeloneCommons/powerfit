# G. Structured model-mismatch benchmark

| Piece | Path |
|---|---|
| Config | `experiments/configs/model_mismatch.yaml` |
| Generator / preprocessing | `experiments/generators/model_mismatch.py` |
| Runner | `experiments/runners/run_model_mismatch.py` |
| Analysis | `experiments/analysis/analyze_model_mismatch.py` |
| Results root | `results/model_mismatch` |

Benchmark design:
- exact realized-neighbour support reused from a control power diagram;
- geometry families: `hard_core_random`, `perturbed_lattice`;
- law families: `exact_control`, `type_cycle`, `local_context`;
- ordinary Voronoi midpoint baseline reported alongside the fitted surrogate.

Manuscript role:
- test how the fitted power-diagram surrogate behaves under structured non-power mismatch while the support graph is held fixed, and quantify the gain over the midpoint baseline plus the residual compatibility defect.
