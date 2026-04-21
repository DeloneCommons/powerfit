# Analysis

Post-processing scripts that turn archived outputs into manuscript tables and
figures live here.

Available scripts:
- `analyze_exact_recovery.py` — Experiment A summaries
- `analyze_noise_robustness.py` — Experiment B summaries
- `analyze_missing_data.py` — Experiment C summaries
- `plot_missing_data_manuscript.py` — manuscript figure build for Experiment C
- `analyze_infeasible_constraints.py` — Experiment D summaries
- `analyze_active_set.py` — Experiment E summaries
- `analyze_periodic_cases.py` — Experiment F summaries
- `analyze_model_mismatch.py` — manuscript figure build and summaries for Experiment G
- `analyze_supergraph_mismatch.py` — summaries for Experiment H
- `scripts/build_manuscript_tables.py` — manuscript-side table builder for the
  currently wired table fragments

The old independent-partition analysis scripts are historical Experiment I
material and are not part of the released paper artifact.

Environment note:
- LaTeX-table export uses `pandas.to_latex(...)`, so `jinja2` is a required
  dependency of the paper-side environment.


Deterministic figure-output note:
- the current Matplotlib plot writers in this directory route figure output through `scripts/_figure_io.py`;
- in the same locked Python environment recorded under `environments/`, the generated PDF/PNG files are expected to be byte-identical across rebuilds;
- outside that locked environment, visual equivalence remains the relevant check.

The dedicated verification helper `python scripts/check_figure_binary_constancy.py`
uses `analyze_exact_recovery.py` as the representative analysis-side case, while
`--suite manuscript` skips the heavier analysis/QTAIM checks and only reruns the
four manuscript-facing generators.
