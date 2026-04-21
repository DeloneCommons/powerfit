#!/usr/bin/env python3
"""Aggregate and plot exact-recovery benchmark outputs."""
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


def _make_curve_plot(df: pd.DataFrame, ycol: str, outpath: Path, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    for (dim, periodic, graph_variant), sub in df.groupby(['dimension', 'periodic', 'graph_variant']):
        sub = sub.sort_values('n_sites')
        label = f"{dim}D | {'periodic' if periodic else 'box'} | {graph_variant}"
        ax.plot(sub['n_sites'], sub[ycol], marker='o', label=label)
    ax.set_xlabel('number of sites')
    ax.set_ylabel(ylabel)
    ax.set_xscale('log', base=2)
    ax.set_yscale('log')
    ax.grid(True, which='both', alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, outpath, title=outpath.stem)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/exact_recovery/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/exact_recovery/analysis'))
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    aggregations: dict[str, tuple[str, str]] = {
        'runs': ('seed', 'count'),
        'separator_rmse_mean': ('separator_rmse', 'mean'),
        'separator_rmse_max': ('separator_rmse', 'max'),
        'edge_difference_rmse_mean': ('edge_difference_rmse', 'mean'),
        'centered_weight_rmse_mean': ('centered_weight_rmse', 'mean'),
        'realized_any_recall_mean': ('realized_any_recall', 'mean'),
        'runtime_sec_mean': ('runtime_sec', 'mean'),
    }
    optional = {
        'algebraic_residual_rmse_mean': 'algebraic_residual_rmse',
        'edge_weighted_rmse_mean': 'edge_weighted_rmse',
    }
    for outcol, incol in optional.items():
        if incol in runs.columns:
            aggregations[outcol] = (incol, 'mean')

    summary = (
        runs.groupby(['dimension', 'periodic', 'graph_variant', 'n_sites'], dropna=False)
        .agg(**aggregations)
        .reset_index()
        .sort_values(['dimension', 'periodic', 'graph_variant', 'n_sites'])
    )
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')

    _make_curve_plot(summary, 'separator_rmse_mean', args.output_dir / 'separator_rmse.pdf', 'mean separator RMSE')
    _make_curve_plot(summary, 'edge_difference_rmse_mean', args.output_dir / 'edge_difference_rmse.pdf', 'mean edge-difference RMSE')
    _make_curve_plot(summary, 'centered_weight_rmse_mean', args.output_dir / 'centered_weight_rmse.pdf', 'mean aligned weight RMSE')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
