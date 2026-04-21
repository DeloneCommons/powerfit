# F. Periodic wrong-image stress tests

| Piece | Path |
|---|---|
| Config | `experiments/configs/periodic.yaml` |
| Generator / preprocessing | `experiments/generators/periodic_cases.py` |
| Runner | `experiments/runners/run_periodic_cases.py` |
| Analysis | `experiments/analysis/analyze_periodic_cases.py` |
| Results root | `results/periodic` |

Manuscript role:
- isolate the ambiguity created by periodic image selection and show how it differs from ordinary measurement noise;
- sweep multiple authoritative wrong-image corruption fractions rather than a single stress point;
- track both wrong-image diagnostics and the repair quality of nearest-image inference and realized-shift refinement.
