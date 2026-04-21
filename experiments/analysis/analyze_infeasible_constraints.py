#!/usr/bin/env python3
"""Aggregate and plot Experiment D outputs."""
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
    'exact_equalities',
    'narrow_intervals',
    'contradictory_equalities',
    'contradictory_intervals',
    'between_points_violation',
]


def _summary_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['scenario', 'dimension', 'n_sites']
    infeasible = ~runs['feasible_expected']
    feasible = runs['feasible_expected']

    def mean_on(mask: pd.Series, column: str) -> pd.DataFrame:
        return (
            runs.loc[mask, group_cols + [column]]
            .groupby(group_cols, dropna=False)[column]
            .mean()
            .rename(column)
            .reset_index()
        )

    summary = (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            feasible_expected_rate=('feasible_expected', 'mean'),
            feasible_detected_rate=('feasible_detected', 'mean'),
            detection_correct_rate=('detection_correct', 'mean'),
            support_cycle_length_mean=('support_cycle_length', 'mean'),
            support_n_nodes_mean=('support_n_nodes', 'mean'),
            support_target_min_mean=('support_target_min', 'mean'),
            support_target_max_mean=('support_target_max', 'mean'),
            generation_attempts_mean=('generation_attempts', 'mean'),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
    )
    for extra in [
        mean_on(infeasible, 'witness_term_count'),
        mean_on(infeasible, 'negative_cycle_margin'),
        mean_on(feasible, 'edge_difference_rmse_to_true'),
    ]:
        summary = summary.merge(extra, on=group_cols, how='left')
    summary['scenario'] = pd.Categorical(summary['scenario'], categories=SCENARIO_ORDER, ordered=True)
    return summary.sort_values(group_cols)


def _group_labels(df: pd.DataFrame) -> list[str]:
    groups = df[['dimension', 'n_sites']].drop_duplicates().sort_values(['dimension', 'n_sites'])
    return [f"{int(row.dimension)}D | n={int(row.n_sites)}" for row in groups.itertuples(index=False)]


def _bar_plot(
    df: pd.DataFrame,
    *,
    value_col: str,
    ylabel: str,
    outpath: Path,
    log_y: bool = False,
    only_infeasible: bool = False,
    only_feasible: bool = False,
) -> None:
    sub = df.copy()
    if only_infeasible:
        sub = sub[sub['feasible_expected_rate'] < 0.5]
    if only_feasible:
        sub = sub[sub['feasible_expected_rate'] >= 0.5]
    sub = sub.sort_values(['scenario', 'dimension', 'n_sites'])

    scenarios = [s for s in SCENARIO_ORDER if s in set(sub['scenario'].astype(str).tolist())]
    groups = sub[['dimension', 'n_sites']].drop_duplicates().sort_values(['dimension', 'n_sites'])
    labels = [f"{int(row.dimension)}D | n={int(row.n_sites)}" for row in groups.itertuples(index=False)]
    if not scenarios or not labels:
        return

    x = np.arange(len(scenarios), dtype=float)
    width = 0.8 / max(len(labels), 1)
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    for offset_idx, row in enumerate(groups.itertuples(index=False)):
        vals = []
        for scenario in scenarios:
            match = sub[
                (sub['scenario'].astype(str) == scenario)
                & (sub['dimension'] == int(row.dimension))
                & (sub['n_sites'] == int(row.n_sites))
            ]
            vals.append(float(match.iloc[0][value_col]) if not match.empty else np.nan)
        ax.bar(x + (offset_idx - 0.5 * (len(labels) - 1)) * width, vals, width=width, label=labels[offset_idx])
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=20, ha='right')
    ax.set_ylabel(ylabel)
    if log_y:
        ax.set_yscale('log')
    ax.grid(True, axis='y', alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/infeasible/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/infeasible/analysis'))
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = _summary_frame(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')

    _bar_plot(
        summary,
        value_col='detection_correct_rate',
        ylabel='detection correctness rate',
        outpath=args.output_dir / 'detection_correct_rate.pdf',
    )
    _bar_plot(
        summary,
        value_col='witness_term_count',
        ylabel='mean witness term count',
        outpath=args.output_dir / 'witness_term_count.pdf',
        only_infeasible=True,
    )
    _bar_plot(
        summary,
        value_col='edge_difference_rmse_to_true',
        ylabel='feasible edge-difference RMSE to truth',
        outpath=args.output_dir / 'edge_difference_rmse_to_true.pdf',
        log_y=True,
        only_feasible=True,
    )
    _bar_plot(
        summary,
        value_col='negative_cycle_margin',
        ylabel='mean negative-cycle margin',
        outpath=args.output_dir / 'negative_cycle_margin.pdf',
        only_infeasible=True,
        log_y=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
