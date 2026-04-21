#!/usr/bin/env python3
"""Aggregate and plot Experiment E outputs."""
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


METHOD_ORDER = ['one_shot_fit', 'self_consistent_refinement']


def _summary_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['method', 'candidate_graph', 'dimension', 'n_sites']
    return (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            candidate_parameter_mean=('candidate_parameter', 'mean'),
            true_pair_count_mean=('true_pair_count', 'mean'),
            candidate_pair_count_mean=('candidate_pair_count', 'mean'),
            extra_pair_count_mean=('extra_pair_count', 'mean'),
            candidate_pair_precision_mean=('candidate_pair_precision', 'mean'),
            candidate_pair_f1_mean=('candidate_pair_f1', 'mean'),
            selected_pair_count_mean=('selected_pair_count', 'mean'),
            selected_pair_precision_mean=('selected_pair_precision', 'mean'),
            selected_pair_recall_mean=('selected_pair_recall', 'mean'),
            selected_pair_f1_mean=('selected_pair_f1', 'mean'),
            true_realized_separator_rmse_mean=('true_realized_separator_rmse', 'mean'),
            true_realized_separator_rmse_max=('true_realized_separator_rmse', 'max'),
            all_candidate_separator_rmse_mean=('all_candidate_separator_rmse', 'mean'),
            false_positive_count_mean=('false_positive_count', 'mean'),
            false_negative_count_mean=('false_negative_count', 'mean'),
            realized_selected_fraction_mean=('realized_selected_fraction', 'mean'),
            convergence_rate=('converged', 'mean'),
            cycle_detected_rate=('cycle_detected', 'mean'),
            outer_iterations_mean=('outer_iterations', 'mean'),
            marginal_count_mean=('marginal_count', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def _group_key(df: pd.DataFrame) -> pd.Series:
    return df.apply(
        lambda row: f"{row['candidate_graph']} | {int(row['dimension'])}D | n={int(row['n_sites'])}",
        axis=1,
    )


def _grouped_bar_plot(
    summary: pd.DataFrame,
    *,
    value_col: str,
    ylabel: str,
    outpath: Path,
    log_y: bool = False,
    methods: list[str] | None = None,
) -> None:
    sub = summary.copy()
    if methods is not None:
        sub = sub[sub['method'].isin(methods)]
    if sub.empty:
        return
    sub['group_key'] = _group_key(sub)
    group_order = (
        sub[['candidate_graph', 'dimension', 'n_sites', 'group_key']]
        .drop_duplicates()
        .sort_values(['candidate_graph', 'dimension', 'n_sites'])['group_key']
        .tolist()
    )
    method_order = [m for m in METHOD_ORDER if m in set(sub['method'].tolist())]
    x = np.arange(len(group_order), dtype=float)
    width = 0.8 / max(len(method_order), 1)

    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    for idx, method in enumerate(method_order):
        vals = []
        for key in group_order:
            match = sub[(sub['group_key'] == key) & (sub['method'] == method)]
            vals.append(float(match.iloc[0][value_col]) if not match.empty else np.nan)
        ax.bar(x + (idx - 0.5 * (len(method_order) - 1)) * width, vals, width=width, label=method)
    ax.set_xticks(x)
    ax.set_xticklabels(group_order, rotation=20, ha='right')
    ax.set_ylabel(ylabel)
    if log_y:
        ax.set_yscale('log')
    ax.grid(True, axis='y', alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def _outer_iter_plot(summary: pd.DataFrame, outpath: Path) -> None:
    sub = summary[summary['method'] == 'self_consistent_refinement'].copy()
    if sub.empty:
        return
    sub['group_key'] = _group_key(sub)
    sub = sub.sort_values(['candidate_graph', 'dimension', 'n_sites'])
    x = np.arange(len(sub), dtype=float)
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    ax.bar(x, sub['outer_iterations_mean'])
    ax.set_xticks(x)
    ax.set_xticklabels(sub['group_key'], rotation=20, ha='right')
    ax.set_ylabel('mean outer iterations')
    ax.grid(True, axis='y', alpha=0.3)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/active_set/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/active_set/analysis'))
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = _summary_frame(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')

    _grouped_bar_plot(
        summary,
        value_col='selected_pair_f1_mean',
        ylabel='selected-pair F1',
        outpath=args.output_dir / 'selected_pair_f1.pdf',
    )
    _grouped_bar_plot(
        summary,
        value_col='selected_pair_precision_mean',
        ylabel='selected-pair precision',
        outpath=args.output_dir / 'selected_pair_precision.pdf',
    )
    _grouped_bar_plot(
        summary,
        value_col='true_realized_separator_rmse_mean',
        ylabel='true-realized separator RMSE',
        outpath=args.output_dir / 'true_realized_separator_rmse.pdf',
        log_y=True,
    )
    _outer_iter_plot(summary, args.output_dir / 'outer_iterations.pdf')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
