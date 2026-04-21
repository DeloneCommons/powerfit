# H. Structured misspecification under supergraph uncertainty

| Piece | Path |
|---|---|
| Config | `experiments/configs/supergraph_mismatch.yaml` |
| Generator / preprocessing | `experiments/generators/supergraph_mismatch.py` |
| Runner | `experiments/runners/run_supergraph_mismatch.py` |
| Analysis | `experiments/analysis/analyze_supergraph_mismatch.py` |
| Results root | `results/supergraph_mismatch` |

Benchmark design:
- start from the strict-supergraph construction used in Experiment E;
- assign structured non-power separator targets on **all** candidate pairs;
- use the harsher `type_cycle` mismatch family from Experiment G;
- compare one-shot fitting against realization-aware self-consistent refinement.

Manuscript role:
- test whether the support-selection workflow remains useful when both the support graph and the separator law are only approximately correct.
