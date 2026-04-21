# C. Missing data and sparsity

| Piece | Path |
|---|---|
| Config | `experiments/configs/missing_data.yaml` |
| Generator / preprocessing | `experiments/generators/missing_data.py` |
| Runner | `experiments/runners/run_missing_data.py` |
| Analysis | `experiments/analysis/analyze_missing_data.py` |
| Results root | `results/missing_data` |

Supplementary figure build:
- `experiments/configs/missing_data_manuscript.yaml`
- `experiments/analysis/plot_missing_data_manuscript.py`
- `results/missing_data_manuscript/`

Manuscript role:
- expose the identifiability transition induced by dropping measured edges.
