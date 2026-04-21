#!/usr/bin/env python3
"""Aggregate and plot Experiment B outputs."""
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


PLOT_METRICS: list[tuple[str, str, str, str, str]] = [
    (
        'clean_separator_rmse_mean',
        'clean_separator_rmse_q25',
        'clean_separator_rmse_q75',
        'clean separator RMSE',
        'clean_separator_rmse',
    ),
    (
        'edge_difference_rmse_mean',
        'edge_difference_rmse_q25',
        'edge_difference_rmse_q75',
        'edge-difference RMSE',
        'edge_difference_rmse',
    ),
    (
        'algebraic_residual_rmse_mean',
        'algebraic_residual_rmse_q25',
        'algebraic_residual_rmse_q75',
        'algebraic residual RMSE',
        'algebraic_residual_rmse',
    ),
    (
        'realized_any_recall_mean',
        'realized_any_recall_q25',
        'realized_any_recall_q75',
        'realized-pair recall',
        'realized_any_recall',
    ),
]


def _summary_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['dimension', 'n_sites', 'noise_family', 'noise_level', 'outlier_fraction', 'method']

    def _q(prob: float):
        return lambda s: float(pd.Series(s).quantile(prob))

    aggregations: dict[str, tuple[str, str]] = {
        'runs': ('seed', 'count'),
        'sigma': ('sigma', 'first'),
        'outlier_amplitude': ('outlier_amplitude', 'max'),
        'clean_separator_rmse_mean': ('clean_separator_rmse', 'mean'),
        'clean_separator_rmse_q25': ('clean_separator_rmse', _q(0.25)),
        'clean_separator_rmse_q75': ('clean_separator_rmse', _q(0.75)),
        'clean_separator_rmse_max': ('clean_separator_rmse', 'max'),
        'clean_separator_mae_mean': ('clean_separator_mae', 'mean'),
        'noisy_separator_rmse_mean': ('noisy_separator_rmse', 'mean'),
        'edge_difference_rmse_mean': ('edge_difference_rmse', 'mean'),
        'edge_difference_rmse_q25': ('edge_difference_rmse', _q(0.25)),
        'edge_difference_rmse_q75': ('edge_difference_rmse', _q(0.75)),
        'centered_weight_rmse_mean': ('centered_weight_rmse', 'mean'),
        'algebraic_inconsistency_mean': ('algebraic_inconsistency', 'mean'),
        'algebraic_residual_rmse_mean': ('algebraic_residual_rmse', 'mean'),
        'algebraic_residual_rmse_q25': ('algebraic_residual_rmse', _q(0.25)),
        'algebraic_residual_rmse_q75': ('algebraic_residual_rmse', _q(0.75)),
        'realized_any_recall_mean': ('realized_any_recall', 'mean'),
        'realized_any_recall_q25': ('realized_any_recall', _q(0.25)),
        'realized_any_recall_q75': ('realized_any_recall', _q(0.75)),
        'status_optimal_rate': ('status', lambda s: float(np.mean(pd.Series(s) == 'optimal'))),
        'converged_rate': ('converged', 'mean'),
        'runtime_sec_mean': ('runtime_sec', 'mean'),
        'runtime_sec_q25': ('runtime_sec', _q(0.25)),
        'runtime_sec_q75': ('runtime_sec', _q(0.75)),
    }
    optional = {
        'edge_weighted_rmse_mean': 'edge_weighted_rmse',
        'objective_total_mean': 'objective_total',
        'objective_mismatch_mean': 'objective_mismatch',
        'objective_penalties_mean': 'objective_penalties',
        'objective_regularization_mean': 'objective_regularization',
        'hard_max_violation_mean': 'hard_max_violation',
    }
    for outcol, incol in optional.items():
        if incol in runs.columns:
            aggregations[outcol] = (incol, 'mean')
    if 'hard_constraints_satisfied' in runs.columns:
        aggregations['hard_constraints_satisfied_mean'] = ('hard_constraints_satisfied', 'mean')

    summary = runs.groupby(group_cols, dropna=False).agg(**aggregations).reset_index()
    family_order = {'gaussian': 0, 'laplace': 1, 'outlier': 2}
    method_order = {'squared': 0, 'huber': 1}
    return (
        summary.assign(
            _family_order=summary['noise_family'].map(family_order).fillna(99),
            _method_order=summary['method'].map(method_order).fillna(99),
        )
        .sort_values(['dimension', 'n_sites', '_family_order', 'outlier_fraction', 'noise_level', '_method_order'])
        .drop(columns=['_family_order', '_method_order'])
        .reset_index(drop=True)
    )


def _family_axis(sub: pd.DataFrame) -> tuple[str, str, bool]:
    family = str(sub['noise_family'].iloc[0])
    if family != 'outlier':
        return 'noise_level', 'noise level', True
    if sub['outlier_fraction'].nunique(dropna=False) > 1 and sub['outlier_amplitude'].nunique(dropna=False) <= 1:
        return 'outlier_fraction', 'outlier fraction', False
    return 'noise_level', 'outlier amplitude', True


def _series_cols(sub: pd.DataFrame, xcol: str) -> list[str]:
    cols = ['dimension', 'method']
    if xcol == 'outlier_fraction' and sub['outlier_amplitude'].nunique(dropna=False) > 1:
        cols.append('outlier_amplitude')
    if xcol == 'noise_level' and sub['noise_family'].iloc[0] == 'outlier' and sub['outlier_fraction'].nunique(dropna=False) > 1:
        cols.append('outlier_fraction')
    return cols


def _series_label(keys: tuple, cols: list[str]) -> str:
    pieces: list[str] = []
    for col, value in zip(cols, keys, strict=True):
        if col == 'dimension':
            pieces.append(f'{int(value)}D')
        elif col == 'method':
            pieces.append(str(value))
        elif col == 'outlier_fraction':
            pieces.append(f'frac={float(value):.2f}')
        elif col == 'outlier_amplitude':
            pieces.append(f'amp={float(value):.3f}')
        else:
            pieces.append(f'{col}={value}')
    return ' | '.join(pieces)


def _family_plot(
    summary: pd.DataFrame,
    family: str,
    *,
    mean_col: str,
    q25_col: str,
    q75_col: str,
    ylabel: str,
    outpath: Path,
) -> None:
    sub = summary[summary['noise_family'] == family].copy()
    if sub.empty:
        return

    xcol, xlabel, log_x = _family_axis(sub)
    group_cols = _series_cols(sub, xcol)

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for keys, grp in sub.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        grp = grp.sort_values(xcol)
        x = grp[xcol].to_numpy(dtype=float)
        y = grp[mean_col].to_numpy(dtype=float)
        q25 = grp[q25_col].to_numpy(dtype=float)
        q75 = grp[q75_col].to_numpy(dtype=float)
        line, = ax.plot(x, y, marker='o', label=_series_label(keys, group_cols))
        ax.fill_between(x, q25, q75, alpha=0.15, color=line.get_color())

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if log_x:
        ax.set_xscale('log')
    if mean_col != 'realized_any_recall_mean':
        ax.set_yscale('log')
    ax.grid(True, which='both', alpha=0.3)
    ax.set_title(family)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/noise_robustness/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/noise_robustness/analysis'))
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = _summary_frame(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')

    families = list(summary['noise_family'].drop_duplicates())
    for family in families:
        for mean_col, q25_col, q75_col, ylabel, stem in PLOT_METRICS:
            _family_plot(
                summary,
                family,
                mean_col=mean_col,
                q25_col=q25_col,
                q75_col=q75_col,
                ylabel=ylabel,
                outpath=args.output_dir / f'{stem}_{family}.pdf',
            )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
