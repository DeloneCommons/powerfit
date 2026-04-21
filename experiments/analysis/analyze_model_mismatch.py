#!/usr/bin/env python3
"""Aggregate and plot Experiment G structured model-mismatch outputs."""
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


def _save_figure(fig: plt.Figure, outpath: Path, *, dpi: int = 280) -> None:
    save_figure(
        fig,
        outpath,
        title=outpath.stem,
        png_dpi=dpi,
        save_pdf_sibling=(outpath.suffix.lower() == '.png'),
        facecolor='white',
        bbox_inches='tight',
    )


def _summary_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['geometry_family', 'dimension', 'n_sites', 'law_family', 'eta']
    return (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            clip_fraction_mean=('clip_fraction', 'mean'),
            measurement_rmse_mean=('measurement_rmse', 'mean'),
            measurement_rmse_q25=('measurement_rmse', lambda s: float(np.quantile(s, 0.25))),
            measurement_rmse_q75=('measurement_rmse', lambda s: float(np.quantile(s, 0.75))),
            midpoint_measurement_rmse_mean=('midpoint_measurement_rmse', 'mean'),
            midpoint_measurement_rmse_q25=('midpoint_measurement_rmse', lambda s: float(np.quantile(s, 0.25))),
            midpoint_measurement_rmse_q75=('midpoint_measurement_rmse', lambda s: float(np.quantile(s, 0.75))),
            measurement_rmse_gain_over_midpoint_mean=('measurement_rmse_gain_over_midpoint', 'mean'),
            projection_residual_rmse_mean=('projection_residual_rmse', 'mean'),
            projection_residual_rmse_q25=('projection_residual_rmse', lambda s: float(np.quantile(s, 0.25))),
            projection_residual_rmse_q75=('projection_residual_rmse', lambda s: float(np.quantile(s, 0.75))),
            midpoint_projection_residual_rmse_mean=('midpoint_projection_residual_rmse', 'mean'),
            cycle_rms_mean=('cycle_rms', 'mean'),
            realized_graph_f1_mean=('realized_graph_f1', 'mean'),
            realized_graph_f1_q25=('realized_graph_f1', lambda s: float(np.quantile(s, 0.25))),
            realized_graph_f1_q75=('realized_graph_f1', lambda s: float(np.quantile(s, 0.75))),
            midpoint_realized_graph_f1_mean=('midpoint_realized_graph_f1', 'mean'),
            midpoint_realized_graph_f1_q25=('midpoint_realized_graph_f1', lambda s: float(np.quantile(s, 0.25))),
            midpoint_realized_graph_f1_q75=('midpoint_realized_graph_f1', lambda s: float(np.quantile(s, 0.75))),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def _trend_frame(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['geometry_family', 'dimension', 'law_family', 'eta']
    return (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            clip_fraction_mean=('clip_fraction', 'mean'),
            clip_fraction_q25=('clip_fraction', lambda s: float(np.quantile(s, 0.25))),
            clip_fraction_q75=('clip_fraction', lambda s: float(np.quantile(s, 0.75))),
            measurement_rmse_mean=('measurement_rmse', 'mean'),
            measurement_rmse_q25=('measurement_rmse', lambda s: float(np.quantile(s, 0.25))),
            measurement_rmse_q75=('measurement_rmse', lambda s: float(np.quantile(s, 0.75))),
            midpoint_measurement_rmse_mean=('midpoint_measurement_rmse', 'mean'),
            midpoint_measurement_rmse_q25=('midpoint_measurement_rmse', lambda s: float(np.quantile(s, 0.25))),
            midpoint_measurement_rmse_q75=('midpoint_measurement_rmse', lambda s: float(np.quantile(s, 0.75))),
            measurement_rmse_gain_over_midpoint_mean=('measurement_rmse_gain_over_midpoint', 'mean'),
            projection_residual_rmse_mean=('projection_residual_rmse', 'mean'),
            projection_residual_rmse_q25=('projection_residual_rmse', lambda s: float(np.quantile(s, 0.25))),
            projection_residual_rmse_q75=('projection_residual_rmse', lambda s: float(np.quantile(s, 0.75))),
            realized_graph_f1_mean=('realized_graph_f1', 'mean'),
            realized_graph_f1_q25=('realized_graph_f1', lambda s: float(np.quantile(s, 0.25))),
            realized_graph_f1_q75=('realized_graph_f1', lambda s: float(np.quantile(s, 0.75))),
            midpoint_realized_graph_f1_mean=('midpoint_realized_graph_f1', 'mean'),
            midpoint_realized_graph_f1_q25=('midpoint_realized_graph_f1', lambda s: float(np.quantile(s, 0.25))),
            midpoint_realized_graph_f1_q75=('midpoint_realized_graph_f1', lambda s: float(np.quantile(s, 0.75))),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def _family_label(name: str) -> str:
    return {
        'hard_core_random': 'hard-core random',
        'perturbed_lattice': 'perturbed lattice',
        'exact_control': 'control',
        'type_cycle': 'type-cycle',
        'local_context': 'local-context',
    }.get(name, name)


def _panel_label(ax: plt.Axes, label: str, *, x: float = -0.13, y: float = 1.03) -> None:
    ax.text(x, y, label, transform=ax.transAxes, fontsize=12, fontweight='bold', va='bottom')


def _plot_trends(trends: pd.DataFrame, outpath: Path) -> None:
    metrics = [
        ('measurement_rmse', 'measurement RMSE'),
        ('projection_residual_rmse', 'projection residual RMSE'),
        ('realized_graph_f1', 'realized-graph F1'),
        ('clip_fraction', 'clipped-target fraction'),
    ]
    law_families = ['type_cycle', 'local_context']
    geometry_families = ['hard_core_random', 'perturbed_lattice']
    colors = {
        'hard_core_random': '#1f77b4',
        'perturbed_lattice': '#d62728',
    }
    markers = {2: 'o', 3: 's'}
    linestyles = {2: '-', 3: '--'}

    fig, axes = plt.subplots(2, 4, figsize=(16.0, 7.0), sharex='col', facecolor='white')
    panel_labels = ['(a)', '(b)', '(c)', '(d)', '(e)', '(f)', '(g)', '(h)']
    label_idx = 0
    legend_handles = {}

    f1_floor = float(max(0.84, trends['realized_graph_f1_q25'].min() - 0.02)) if not trends.empty else 0.84
    rmse_ceiling = float(trends['measurement_rmse_q75'].max() * 1.10) if not trends.empty else 0.4
    proj_ceiling = float(trends['projection_residual_rmse_q75'].max() * 1.15) if not trends.empty else 0.11
    clip_ceiling = float(max(0.05, trends['clip_fraction_q75'].max() * 1.12)) if not trends.empty else 0.7
    rmse_floor = -0.03 * rmse_ceiling
    proj_floor = -0.03 * proj_ceiling
    clip_floor = -0.03 * clip_ceiling

    for row, law_family in enumerate(law_families):
        row_data = trends[trends['law_family'] == law_family].copy()
        for col, (metric_root, title) in enumerate(metrics):
            ax = axes[row, col]
            mean_col = f'{metric_root}_mean'
            q25_col = f'{metric_root}_q25'
            q75_col = f'{metric_root}_q75'

            for geometry_family in geometry_families:
                for dim in [2, 3]:
                    sub = row_data[
                        (row_data['geometry_family'] == geometry_family)
                        & (row_data['dimension'] == dim)
                    ].sort_values('eta')
                    if sub.empty:
                        continue
                    x = sub['eta'].to_numpy(dtype=float)
                    y = sub[mean_col].to_numpy(dtype=float)
                    q25 = sub[q25_col].to_numpy(dtype=float)
                    q75 = sub[q75_col].to_numpy(dtype=float)
                    ax.fill_between(x, q25, q75, color=colors[geometry_family], alpha=0.12, linewidth=0.0)
                    handle = ax.plot(
                        x,
                        y,
                        marker=markers[dim],
                        linestyle=linestyles[dim],
                        linewidth=2.0,
                        markersize=5.4,
                        color=colors[geometry_family],
                        label=f"{_family_label(geometry_family)} | {dim}D",
                    )[0]
                    legend_handles.setdefault(f"{_family_label(geometry_family)} | {dim}D", handle)

            ax.grid(True, alpha=0.25, linewidth=0.6)
            ax.set_xlim(-0.01, 0.515)
            if row == 1:
                ax.set_xlabel('mismatch amplitude $\\eta$')
            if row == 0:
                ax.set_title(title)
            if col == 0:
                ax.set_ylabel(_family_label(law_family))
            else:
                ax.set_ylabel('')

            if metric_root == 'measurement_rmse':
                ax.set_ylim(rmse_floor, rmse_ceiling)
            elif metric_root == 'projection_residual_rmse':
                ax.set_ylim(proj_floor, proj_ceiling)
            elif metric_root == 'realized_graph_f1':
                ax.set_ylim(f1_floor, 1.005)
            elif metric_root == 'clip_fraction':
                ax.set_ylim(clip_floor, clip_ceiling)
                if law_family == 'local_context' and float(row_data[mean_col].max()) < 0.01:
                    ax.text(
                        0.52,
                        0.90,
                        'approximately zero\nacross sweep',
                        transform=ax.transAxes,
                        ha='center',
                        va='top',
                        fontsize=8.5,
                        color='#555555',
                    )

            _panel_label(ax, panel_labels[label_idx])
            label_idx += 1

    handles = [
        legend_handles[key]
        for key in [
            'hard-core random | 2D',
            'hard-core random | 3D',
            'perturbed lattice | 2D',
            'perturbed lattice | 3D',
        ]
        if key in legend_handles
    ]
    labels = [h.get_label() for h in handles]
    if handles:
        fig.legend(handles, labels, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0.0, 0.07, 1.0, 1.0))
    _save_figure(fig, outpath, dpi=280)
    plt.close(fig)


def _build_eta_table(summary: pd.DataFrame, outpath: Path, *, eta_value: float) -> None:
    sub = summary[np.isclose(summary['eta'], eta_value)].copy()
    sub = sub[sub['law_family'] != 'exact_control']
    if sub.empty:
        outpath.write_text('% no rows at requested eta\n', encoding='utf-8')
        return
    sub['geometry_family'] = sub['geometry_family'].map(_family_label)
    sub['law_family'] = sub['law_family'].map(_family_label)
    table = sub[
        [
            'geometry_family',
            'dimension',
            'n_sites',
            'law_family',
            'measurement_rmse_mean',
            'midpoint_measurement_rmse_mean',
            'measurement_rmse_gain_over_midpoint_mean',
            'projection_residual_rmse_mean',
            'realized_graph_f1_mean',
            'midpoint_realized_graph_f1_mean',
            'clip_fraction_mean',
            'runtime_sec_mean',
        ]
    ].rename(
        columns={
            'geometry_family': 'geometry',
            'dimension': 'dim',
            'n_sites': 'n',
            'law_family': 'law',
            'measurement_rmse_mean': 'fit_rmse',
            'midpoint_measurement_rmse_mean': 'midpoint_rmse',
            'measurement_rmse_gain_over_midpoint_mean': 'gain_over_midpoint',
            'projection_residual_rmse_mean': 'proj_rmse',
            'realized_graph_f1_mean': 'fit_graph_f1',
            'midpoint_realized_graph_f1_mean': 'midpoint_graph_f1',
            'clip_fraction_mean': 'clip',
            'runtime_sec_mean': 'time_s',
        }
    )
    outpath.write_text(table.to_latex(index=False, float_format='%.3e'), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/model_mismatch/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/model_mismatch/analysis'))
    parser.add_argument('--figure-path', type=Path, default=None)
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = _summary_frame(runs)
    trends = _trend_frame(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')
    trends.to_csv(args.output_dir / 'trend_summary.csv', index=False)
    trends.to_latex(args.output_dir / 'trend_summary.tex', index=False, float_format='%.3e')

    figure_path = args.figure_path or (args.output_dir / 'trend_figure.png')
    _plot_trends(trends, figure_path)
    _build_eta_table(summary, args.output_dir / 'moderate_eta_table.tex', eta_value=0.20)
    _build_eta_table(summary, args.output_dir / 'high_eta_table.tex', eta_value=0.50)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
