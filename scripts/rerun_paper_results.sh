#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
PYTHON_BIN=${PYTHON:-python}

run() {
  echo "[rerun] $*"
  "$@"
}

cd "$REPO_ROOT"

# Synthetic Experiments A--H.
run "$PYTHON_BIN" experiments/runners/run_exact_recovery.py
run "$PYTHON_BIN" experiments/analysis/analyze_exact_recovery.py

run "$PYTHON_BIN" experiments/runners/run_noise_robustness.py
run "$PYTHON_BIN" experiments/analysis/analyze_noise_robustness.py

run "$PYTHON_BIN" experiments/runners/run_missing_data.py
run "$PYTHON_BIN" experiments/analysis/analyze_missing_data.py
run "$PYTHON_BIN" experiments/runners/run_missing_data.py   --config experiments/configs/missing_data_manuscript.yaml   --output-dir results/missing_data_manuscript

run "$PYTHON_BIN" experiments/runners/run_infeasible_constraints.py
run "$PYTHON_BIN" experiments/analysis/analyze_infeasible_constraints.py

run "$PYTHON_BIN" experiments/runners/run_active_set.py
run "$PYTHON_BIN" experiments/analysis/analyze_active_set.py

run "$PYTHON_BIN" experiments/runners/run_periodic_cases.py
run "$PYTHON_BIN" experiments/analysis/analyze_periodic_cases.py

run "$PYTHON_BIN" experiments/runners/run_model_mismatch.py
run "$PYTHON_BIN" experiments/analysis/analyze_model_mismatch.py

run "$PYTHON_BIN" experiments/runners/run_supergraph_mismatch.py
run "$PYTHON_BIN" experiments/analysis/analyze_supergraph_mismatch.py

# Experiment J analyses from committed molecular data only.
run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_dataset_audit.py   data/qtaim_main/systems_final.csv   --require-all

run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_true_support_ladder.py   data/qtaim_main/systems_final.csv   --require-all

run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_candidate_recovery.py   data/qtaim_main/systems_final.csv   --require-all

run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_mask_transfer.py   data/qtaim_main/systems_final.csv   --j3-selected-csv results/qtaim_main/J3_candidate_recovery_refresh/selected_edge_level.csv   --box-margin 5   --output-dir results/qtaim_main/J4_mask_transfer_refresh   --require-all

run "$PYTHON_BIN" scripts/qtaim/validate_local_support_diagnostics.py   --edge-level-csv results/qtaim_main/J4_mask_transfer_refresh/edge_level.csv   --output-dir results/qtaim_main/J4_local_diagnostic_validation

run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_mask_transfer.py   data/qtaim_main/systems_final.csv   --j3-selected-csv results/qtaim_main/J3_candidate_recovery_refresh/selected_edge_level.csv   --box-margin 3   --output-dir results/qtaim_main/J4_mask_transfer_margin3_refresh   --require-all

run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_mask_transfer.py   data/qtaim_main/systems_final.csv   --j3-selected-csv results/qtaim_main/J3_candidate_recovery_refresh/selected_edge_level.csv   --box-margin 7   --output-dir results/qtaim_main/J4_mask_transfer_margin7_refresh   --require-all

run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_mask_transfer.py   data/qtaim_main/systems_final.csv   --j3-selected-csv results/qtaim_main/J3_candidate_recovery_refresh/selected_edge_level.csv   --box-margin 10   --output-dir results/qtaim_main/J4_mask_transfer_margin10_refresh   --require-all

run "$PYTHON_BIN" scripts/qtaim/analyze_qtaim_box_margin_sensitivity.py   results/qtaim_main/J4_mask_transfer_margin3_refresh   results/qtaim_main/J4_mask_transfer_refresh   results/qtaim_main/J4_mask_transfer_margin7_refresh   results/qtaim_main/J4_mask_transfer_margin10_refresh   --labels 3A 5A 7A 10A   --output-dir results/qtaim_main/J4_box_margin_summary_refresh

# Compile the reviewed manuscript from its tracked sources and figures.
# Rerun outputs are for comparison with the frozen evidence; they do not
# silently replace the reviewed figures or inline tables. Run in a disposable
# checkout: the commands above deliberately write new experimental outputs.
run bash scripts/build_manuscript_pdfs.sh
run "$PYTHON_BIN" scripts/check_repo_consistency.py --skip-frozen

echo "[rerun] completed paper-side rerun from committed data"
