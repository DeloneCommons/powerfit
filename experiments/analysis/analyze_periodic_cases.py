#!/usr/bin/env python3
"""Aggregate and plot Experiment F outputs."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _figure_io import save_figure


SCENARIO_ORDER = [
    'correct_images',
    'noisy_correct_images',
    'wrong_images_authoritative',
    'nearest_image_inference',
    'realized_shift_refinement',
]

SWEEP_SCENARIOS = [
    'wrong_images_authoritative',
    'nearest_image_inference',
    'realized_shift_refinement',
]


def _summary_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['scenario', 'dimension', 'n_sites', 'corruption_fraction']

    def _q(prob: float):
        return lambda s: float(pd.Series(s).quantile(prob))

    agg_map: dict[str, tuple[str, str]] = {
        'runs': ('seed', 'count'),
        'actual_corruption_fraction_mean': ('actual_corruption_fraction', 'mean'),
        'measurement_noise_sigma_mean': ('measurement_noise_sigma', 'mean'),
        'n_constraints_mean': ('n_constraints', 'mean'),
        'n_corrupted_rows_mean': ('n_corrupted_rows', 'mean'),
        'image_choice_accuracy_mean': ('image_choice_accuracy', 'mean'),
        'image_choice_accuracy_q25': ('image_choice_accuracy', _q(0.25)),
        'image_choice_accuracy_q75': ('image_choice_accuracy', _q(0.75)),
        'image_choice_accuracy_min': ('image_choice_accuracy', 'min'),
        'mean_shift_l1_distance_mean': ('mean_shift_l1_distance', 'mean'),
        'clean_separator_rmse_mean': ('clean_separator_rmse', 'mean'),
        'clean_separator_rmse_q25': ('clean_separator_rmse', _q(0.25)),
        'clean_separator_rmse_q75': ('clean_separator_rmse', _q(0.75)),
        'clean_separator_rmse_max': ('clean_separator_rmse', 'max'),
        'observed_separator_rmse_mean': ('observed_separator_rmse', 'mean'),
        'pair_difference_rmse_mean': ('pair_difference_rmse', 'mean'),
        'pair_difference_rmse_q25': ('pair_difference_rmse', _q(0.25)),
        'pair_difference_rmse_q75': ('pair_difference_rmse', _q(0.75)),
        'realized_same_shift_rate_mean': ('realized_same_shift_rate', 'mean'),
        'realized_other_shift_rate_mean': ('realized_other_shift_rate', 'mean'),
        'realized_other_shift_rate_q25': ('realized_other_shift_rate', _q(0.25)),
        'realized_other_shift_rate_q75': ('realized_other_shift_rate', _q(0.75)),
        'realized_any_rate_mean': ('realized_any_rate', 'mean'),
        'unrealized_rate_mean': ('unrealized_rate', 'mean'),
        'unaccounted_pair_count_mean': ('unaccounted_pair_count', 'mean'),
        'status_optimal_rate': ('status', lambda s: float(np.mean(pd.Series(s) == 'optimal'))),
        'converged_rate': ('converged', 'mean'),
        'runtime_sec_mean': ('runtime_sec', 'mean'),
        'runtime_sec_q25': ('runtime_sec', _q(0.25)),
        'runtime_sec_q75': ('runtime_sec', _q(0.75)),
    }
    optional = {
        'shift_refinement_iterations_mean': 'shift_refinement_iterations',
        'shift_refinement_converged_rate': 'shift_refinement_converged',
        'shift_rows_reassigned_total_mean': 'shift_rows_reassigned_total',
        'shift_rows_reassigned_last_mean': 'shift_rows_reassigned_last',
        'unique_realized_rows_last_mean': 'unique_realized_rows_last',
        'ambiguous_realized_rows_last_mean': 'ambiguous_realized_rows_last',
        'unrealized_rows_last_mean': 'unrealized_rows_last',
        'initial_image_choice_accuracy_mean': 'initial_image_choice_accuracy',
        'initial_realized_other_shift_rate_mean': 'initial_realized_other_shift_rate',
        'initial_clean_separator_rmse_mean': 'initial_clean_separator_rmse',
    }
    for outcol, incol in optional.items():
        if incol in runs.columns:
            agg_map[outcol] = (incol, 'mean')
    summary = runs.groupby(group_cols, dropna=False, observed=True).agg(**agg_map).reset_index()
    summary['scenario'] = pd.Categorical(summary['scenario'], categories=SCENARIO_ORDER, ordered=True)
    return summary.sort_values(['dimension', 'n_sites', 'corruption_fraction', 'scenario']).reset_index(drop=True)


def _scenario_label(scenario: str) -> str:
    return scenario.replace('_', ' ')


def _sweep_plot(
    summary: pd.DataFrame,
    *,
    value_col: str,
    q25_col: str,
    q75_col: str,
    ylabel: str,
    outpath: Path,
    log_y: bool = False,
) -> None:
    sub = summary[summary['scenario'].isin(SWEEP_SCENARIOS)].copy()
    if sub.empty:
        return

    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    for (dimension, scenario), grp in sub.groupby(['dimension', 'scenario'], dropna=False, observed=True):
        grp = grp.sort_values('corruption_fraction')
        x = grp['corruption_fraction'].to_numpy(dtype=float)
        y = grp[value_col].to_numpy(dtype=float)
        q25 = grp[q25_col].to_numpy(dtype=float)
        q75 = grp[q75_col].to_numpy(dtype=float)
        label = f'{int(dimension)}D | {_scenario_label(str(scenario))}'
        line, = ax.plot(x, y, marker='o', label=label)
        ax.fill_between(x, q25, q75, alpha=0.15, color=line.get_color())

    ax.set_xlabel('authoritative wrong-image corruption fraction')
    ax.set_ylabel(ylabel)
    if log_y:
        ax.set_yscale('log')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def _refinement_plot(summary: pd.DataFrame, outpath: Path) -> None:
    sub = summary[summary['scenario'] == 'realized_shift_refinement'].copy()
    if sub.empty or 'shift_refinement_iterations_mean' not in sub.columns:
        return

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for dimension, grp in sub.groupby('dimension', dropna=False, observed=True):
        grp = grp.sort_values('corruption_fraction')
        ax.plot(
            grp['corruption_fraction'].to_numpy(dtype=float),
            grp['shift_refinement_iterations_mean'].to_numpy(dtype=float),
            marker='o',
            label=f'{int(dimension)}D',
        )
    ax.set_xlabel('authoritative wrong-image corruption fraction')
    ax.set_ylabel('mean refinement iterations')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/periodic/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/periodic/analysis'))
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = _summary_frame(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')

    _sweep_plot(
        summary,
        value_col='image_choice_accuracy_mean',
        q25_col='image_choice_accuracy_q25',
        q75_col='image_choice_accuracy_q75',
        ylabel='image-choice accuracy',
        outpath=args.output_dir / 'image_choice_accuracy_sweep.pdf',
    )
    _sweep_plot(
        summary,
        value_col='realized_other_shift_rate_mean',
        q25_col='realized_other_shift_rate_q25',
        q75_col='realized_other_shift_rate_q75',
        ylabel='realized-other-shift rate',
        outpath=args.output_dir / 'realized_other_shift_rate_sweep.pdf',
    )
    _sweep_plot(
        summary,
        value_col='clean_separator_rmse_mean',
        q25_col='clean_separator_rmse_q25',
        q75_col='clean_separator_rmse_q75',
        ylabel='clean-separator RMSE',
        outpath=args.output_dir / 'clean_separator_rmse_sweep.pdf',
        log_y=True,
    )
    _sweep_plot(
        summary,
        value_col='pair_difference_rmse_mean',
        q25_col='pair_difference_rmse_q25',
        q75_col='pair_difference_rmse_q75',
        ylabel='pair-difference RMSE',
        outpath=args.output_dir / 'pair_difference_rmse_sweep.pdf',
        log_y=True,
    )
    _refinement_plot(summary, args.output_dir / 'shift_refinement_iterations_sweep.pdf')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
