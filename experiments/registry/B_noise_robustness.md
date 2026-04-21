# B. Noise and contamination response

| Piece | Path |
|---|---|
| Config | `experiments/configs/noise_robustness.yaml` |
| Generator / preprocessing | `experiments/generators/noise_robustness.py` |
| Runner | `experiments/runners/run_noise_robustness.py` |
| Analysis | `experiments/analysis/analyze_noise_robustness.py` |
| Results root | `results/noise_robustness` |

Manuscript role:
- provide the dense-noise control study for the quadratic inverse fit on the correct realized-pair graph;
- provide the squared-vs-Huber comparison under sparse gross outliers on the same exact support;
- record both central trends and replicate spread for the main measurement, algebraic, and realization-aware diagnostics.
