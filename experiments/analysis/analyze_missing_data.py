#!/usr/bin/env python3
"""Aggregate and plot Experiment C outputs."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import matplotlib.pyplot as plt
import pandas as pd

from _figure_io import save_figure


PLOT_SPECS: list[tuple[str, str, str, bool]] = [
    ('connected_rate', 'connected rate', 'connected_rate', False),
    ('recoverable_pair_fraction_mean', 'recoverable-pair fraction', 'recoverable_pair_fraction', False),
    ('global_centered_weight_rmse_mean', 'global aligned weight RMSE', 'global_centered_weight_rmse', True),
    ('componentwise_aligned_weight_rmse_mean', 'componentwise aligned weight RMSE', 'componentwise_aligned_weight_rmse', True),
    ('all_pair_difference_rmse_mean', 'all-pair difference RMSE', 'all_pair_difference_rmse', True),
]


def _summary_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['dimension', 'n_sites', 'keep_fraction_requested']
    return (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            keep_fraction_actual_mean=('keep_fraction_actual', 'mean'),
            base_generation_attempts_mean=('base_generation_attempts', 'mean'),
            n_constraints_full_mean=('n_constraints_full', 'mean'),
            n_constraints_observed_mean=('n_constraints_observed', 'mean'),
            connected_rate=('connected', 'mean'),
            n_components_mean=('n_components', 'mean'),
            largest_component_fraction_mean=('largest_component_fraction', 'mean'),
            recoverable_pair_fraction_mean=('recoverable_pair_fraction', 'mean'),
            isolated_site_fraction_mean=('isolated_site_fraction', 'mean'),
            observed_separator_rmse_mean=('observed_separator_rmse', 'mean'),
            observed_separator_rmse_max=('observed_separator_rmse', 'max'),
            componentwise_aligned_weight_rmse_mean=('componentwise_aligned_weight_rmse', 'mean'),
            global_centered_weight_rmse_mean=('global_centered_weight_rmse', 'mean'),
            all_pair_difference_rmse_mean=('all_pair_difference_rmse', 'mean'),
            same_component_pair_difference_rmse_mean=('same_component_pair_difference_rmse', 'mean'),
            component_shift_std_mean=('component_shift_std', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def _curve_plot(df: pd.DataFrame, ycol: str, ylabel: str, outpath: Path, *, log_y: bool) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for (dim, n_sites), sub in df.groupby(['dimension', 'n_sites'], dropna=False):
        sub = sub.sort_values('keep_fraction_requested')
        label = f'{dim}D | n={n_sites}'
        ax.plot(sub['keep_fraction_requested'], sub[ycol], marker='o', label=label)
    ax.set_xlabel('edge-retention fraction')
    ax.set_ylabel(ylabel)
    if log_y:
        ax.set_yscale('log')
    ax.grid(True, which='both', alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/missing_data/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/missing_data/analysis'))
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = _summary_frame(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')

    for ycol, ylabel, stem, log_y in PLOT_SPECS:
        _curve_plot(summary, ycol, ylabel, args.output_dir / f'{stem}.pdf', log_y=log_y)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
