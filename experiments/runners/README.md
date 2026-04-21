# Runners

Experiment entry points live here.

Each runner consumes a config file from `../configs/` and writes outputs under
`../../results/`.

Available runners:
- `run_exact_recovery.py` — Experiment A
- `run_noise_robustness.py` — Experiment B
- `run_missing_data.py` — Experiment C
- `run_infeasible_constraints.py` — Experiment D
- `run_active_set.py` — Experiment E
- `run_periodic_cases.py` — Experiment F
- `run_model_mismatch.py` — Experiment G
- `run_supergraph_mismatch.py` — Experiment H

Experiment J does not use a runner in this directory; its molecular workflow is
documented in `scripts/qtaim/README.md`.
