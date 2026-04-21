#!/usr/bin/env python3
"""Build manuscript-style missing-data figures."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import matplotlib as mpl
mpl.rcParams['pdf.fonttype'] = 42
mpl.rcParams['ps.fonttype'] = 42
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from scripts._figure_io import save_figure_pair


def _save_figure(fig: plt.Figure, outpath: Path, *, dpi: int = 300) -> None:
    save_figure_pair(
        fig,
        png_path=outpath if outpath.suffix.lower() == '.png' else None,
        pdf_path=outpath.with_suffix('.pdf') if outpath.suffix.lower() == '.png' else outpath,
        title=outpath.stem,
        png_dpi=dpi,
        facecolor='white',
        bbox_inches='tight',
    )


def _copy_figure_pair(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    pdf_src = src.with_suffix('.pdf')
    if pdf_src.exists():
        shutil.copy2(pdf_src, dst.with_suffix('.pdf'))


def _quantile(q: float):
    def _inner(series: pd.Series) -> float:
        return float(series.quantile(q))

    return _inner


def aggregate_runs(runs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ['dimension', 'n_sites', 'keep_fraction_requested']
    return (
        runs.groupby(group_cols, dropna=False)
        .agg(
            runs=('seed', 'count'),
            connected_rate=('connected', 'mean'),
            recoverable_pair_fraction=('recoverable_pair_fraction', 'mean'),
            global_centered_weight_rmse_mean=('global_centered_weight_rmse', 'mean'),
            global_centered_weight_rmse_median=('global_centered_weight_rmse', 'median'),
            global_centered_weight_rmse_q25=('global_centered_weight_rmse', _quantile(0.25)),
            global_centered_weight_rmse_q75=('global_centered_weight_rmse', _quantile(0.75)),
            componentwise_aligned_weight_rmse_mean=('componentwise_aligned_weight_rmse', 'mean'),
            componentwise_aligned_weight_rmse_median=('componentwise_aligned_weight_rmse', 'median'),
            componentwise_aligned_weight_rmse_q25=('componentwise_aligned_weight_rmse', _quantile(0.25)),
            componentwise_aligned_weight_rmse_q75=('componentwise_aligned_weight_rmse', _quantile(0.75)),
            runtime_sec_mean=('runtime_sec', 'mean'),
        )
        .reset_index()
        .sort_values(group_cols)
    )


def _pivot(df: pd.DataFrame, dim: int, value: str) -> pd.DataFrame:
    sub = df[df['dimension'] == dim].copy()
    pivot = sub.pivot(index='n_sites', columns='keep_fraction_requested', values=value)
    return pivot.sort_index().sort_index(axis=1)


def _heatmap(
    ax: plt.Axes,
    pivot: pd.DataFrame,
    cmap: str,
    *,
    vmin=None,
    vmax=None,
    ylabel: bool = True,
    xlabel: bool = True,
) -> plt.Axes:
    arr = pivot.to_numpy(dtype=float)
    im = ax.imshow(arr, aspect='auto', origin='lower', cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_box_aspect(1.0)
    ax.set_xlabel('retention fraction' if xlabel else '')
    if ylabel:
        ax.set_ylabel('n sites')
    else:
        ax.set_ylabel('')
    xticks = list(range(0, len(pivot.columns), 2))
    if xticks and xticks[-1] != len(pivot.columns) - 1:
        xticks.append(len(pivot.columns) - 1)
    ax.set_xticks(xticks)
    ax.set_xticklabels([f'{pivot.columns[i]:.2f}' for i in xticks], rotation=45, ha='right', fontsize=7.8)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(v) for v in pivot.index], fontsize=7.8)
    ax.tick_params(length=0)
    return im


def _panel_label(ax: plt.Axes, label: str, x: float = -0.18, y: float = 1.02) -> None:
    ax.text(x, y, label, transform=ax.transAxes, fontsize=11.8, fontweight='bold', va='bottom')


def _set_log10_rmse_axis(ax: plt.Axes) -> None:
    tick_exponents = list(range(0, -16, -3))
    tick_values = [10.0 ** exponent for exponent in tick_exponents]
    ax.set_yscale('log')
    ax.set_ylim(3e-18, 5.0)
    ax.set_yticks(tick_values)
    ax.set_yticklabels([str(exponent) for exponent in tick_exponents])
    ax.set_ylabel(r'$\log_{10}(\mathrm{RMSE})$')


def _profile_rows(summary: pd.DataFrame, dim: int) -> tuple[pd.DataFrame, int]:
    sub = summary[summary['dimension'] == dim].copy()
    if sub.empty:
        return sub, 0
    n_max = int(sub['n_sites'].max())
    sub = sub[sub['n_sites'] == n_max].sort_values('keep_fraction_requested')
    return sub, n_max


def _clip_positive(series: pd.Series, *, floor: float = 1e-16) -> np.ndarray:
    return series.to_numpy(dtype=float).clip(min=floor)


def _plot_rmse_profile(ax: plt.Axes, sub: pd.DataFrame, *, ylabel: bool, title: str) -> None:
    x = sub['keep_fraction_requested'].to_numpy(dtype=float)

    comp_median = _clip_positive(sub['componentwise_aligned_weight_rmse_median'])
    comp_q25 = _clip_positive(sub['componentwise_aligned_weight_rmse_q25'])
    comp_q75 = _clip_positive(sub['componentwise_aligned_weight_rmse_q75'])
    global_median = _clip_positive(sub['global_centered_weight_rmse_median'])
    global_q25 = _clip_positive(sub['global_centered_weight_rmse_q25'])
    global_q75 = _clip_positive(sub['global_centered_weight_rmse_q75'])

    ax.fill_between(x, comp_q25, comp_q75, color='#1f77b4', alpha=0.15, linewidth=0.0)
    ax.fill_between(x, global_q25, global_q75, color='#d62728', alpha=0.15, linewidth=0.0)
    ax.plot(
        x,
        comp_median,
        marker='o',
        linewidth=2.0,
        markersize=5.5,
        label='componentwise aligned RMSE',
        color='#1f77b4',
    )
    ax.plot(
        x,
        global_median,
        marker='s',
        linewidth=2.0,
        markersize=5.5,
        label='global aligned RMSE',
        color='#d62728',
    )
    ax.set_xlim(0.08, 1.02)
    ax.set_xlabel('retention fraction')
    ax.set_title(title, fontsize=11)
    _set_log10_rmse_axis(ax)
    if ylabel:
        ax.legend(loc='upper left', frameon=False, fontsize=8.5)
    ax.grid(True, which='both', alpha=0.25, linewidth=0.6)


def _plot_connected_profile(ax: plt.Axes, sub: pd.DataFrame, *, ylabel: bool, title: str) -> None:
    x = sub['keep_fraction_requested'].to_numpy(dtype=float)
    connected_rate = sub['connected_rate'].to_numpy(dtype=float)
    ax.plot(
        x,
        connected_rate,
        marker='^',
        linewidth=2.1,
        markersize=6.0,
        color='#2ca02c',
        label='connected rate',
    )
    ax.set_xlim(0.08, 1.02)
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel('retention fraction')
    ax.set_title(title, fontsize=11)
    if ylabel:
        ax.set_ylabel('connected rate')
    ax.grid(True, which='major', alpha=0.25, linewidth=0.6)


def _plot_rmse_profile_combined(ax: plt.Axes, summary: pd.DataFrame) -> None:
    dim_styles = {
        2: dict(linestyle='-', marker='o', markerfacecolor=None, markeredgewidth=0.9),
        3: dict(linestyle=(0, (1.0, 1.6)), marker='s', markerfacecolor='white', markeredgewidth=1.2),
    }
    colors = {
        'componentwise_aligned_weight_rmse_median': '#1f77b4',
        'global_centered_weight_rmse_median': '#d62728',
    }
    for dim in (2, 3):
        sub, _ = _profile_rows(summary, dim)
        if sub.empty:
            continue
        x = sub['keep_fraction_requested'].to_numpy(dtype=float)
        style = dim_styles[dim]
        for column in ('componentwise_aligned_weight_rmse_median', 'global_centered_weight_rmse_median'):
            ax.plot(
                x,
                _clip_positive(sub[column]),
                color=colors[column],
                linewidth=2.0,
                markersize=5.0,
                marker=style['marker'],
                markerfacecolor=style['markerfacecolor'],
                markeredgecolor=colors[column],
                markeredgewidth=style['markeredgewidth'],
                linestyle=style['linestyle'],
                dash_capstyle='round',
            )
    ax.set_xlim(0.08, 1.02)
    ax.set_xlabel('retention fraction')
    _set_log10_rmse_axis(ax)
    ax.grid(True, which='both', alpha=0.25, linewidth=0.6)


def _plot_connected_profile_combined(ax: plt.Axes, summary: pd.DataFrame) -> None:
    styles = {
        2: dict(linestyle='-', marker='o', markerfacecolor=None, markeredgewidth=0.9),
        3: dict(linestyle=(0, (1.0, 1.6)), marker='s', markerfacecolor='white', markeredgewidth=1.2),
    }
    for dim in (2, 3):
        sub, _ = _profile_rows(summary, dim)
        if sub.empty:
            continue
        x = sub['keep_fraction_requested'].to_numpy(dtype=float)
        style = styles[dim]
        ax.plot(
            x,
            sub['connected_rate'].to_numpy(dtype=float),
            color='#2ca02c',
            linewidth=2.1,
            markersize=5.2,
            marker=style['marker'],
            markerfacecolor=style['markerfacecolor'],
            markeredgecolor='#2ca02c',
            markeredgewidth=style['markeredgewidth'],
            linestyle=style['linestyle'],
            dash_capstyle='round',
        )
    ax.set_xlim(0.08, 1.02)
    ax.set_ylim(-0.03, 1.03)
    ax.set_ylabel('connected rate')
    ax.set_xlabel('retention fraction')
    ax.grid(True, which='major', alpha=0.25, linewidth=0.6)


def build_transition_heatmap(summary: pd.DataFrame, outpath: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True, facecolor='white')
    dims = [2, 3]

    connected_pivots = {dim: _pivot(summary, dim, 'connected_rate') for dim in dims}
    rmse_pivots = {
        dim: _pivot(summary, dim, 'global_centered_weight_rmse_median').replace(0.0, np.nan)
        for dim in dims
    }

    for col, dim in enumerate(dims):
        im_top = _heatmap(
            axes[0, col],
            connected_pivots[dim],
            'managua',
            vmin=0.0,
            vmax=1.0,
        )
        rmse_log = np.log10(rmse_pivots[dim].fillna(1e-16).clip(lower=1e-16))
        im_bottom = _heatmap(
            axes[1, col],
            rmse_log,
            'vanimo',
            vmin=-16,
            vmax=0,
        )

    cbar_top = fig.colorbar(im_top, ax=axes[0, :], shrink=0.95)
    cbar_top.set_label('connected rate')
    cbar_bottom = fig.colorbar(im_bottom, ax=axes[1, :], shrink=0.95)
    cbar_bottom.set_label('log10 global aligned RMSE')
    _save_figure(fig, outpath, dpi=240)
    plt.close(fig)


def build_alignment_profile(summary: pd.DataFrame, outpath: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11.6, 6.6), constrained_layout=True, facecolor='white', sharex='col')
    for col, dim in enumerate([2, 3]):
        sub, n_max = _profile_rows(summary, dim)
        if sub.empty:
            continue
        _plot_rmse_profile(
            axes[0, col],
            sub,
            ylabel=(col == 0),
            title=f'{dim}D RMSE profile ($n={n_max}$)',
        )
        _plot_connected_profile(
            axes[1, col],
            sub,
            ylabel=(col == 0),
            title=f'{dim}D connected-rate profile ($n={n_max}$)',
        )
    _save_figure(fig, outpath, dpi=240)
    plt.close(fig)


def build_composite_figure(summary: pd.DataFrame, outpath: Path) -> None:
    fig = plt.figure(figsize=(12.0, 8.4), facecolor='white')
    gs = fig.add_gridspec(
        3,
        4,
        height_ratios=[0.96, 0.96, 0.11],
        hspace=0.22,
        wspace=0.28,
    )

    ax_a = fig.add_subplot(gs[0, 0:2])
    ax_b = fig.add_subplot(gs[0, 2:4], sharex=ax_a)
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1], sharey=ax_c)
    ax_e = fig.add_subplot(gs[1, 2])
    ax_f = fig.add_subplot(gs[1, 3], sharey=ax_e)
    cax_rmse = fig.add_subplot(gs[2, 0:2])
    cax_conn = fig.add_subplot(gs[2, 2:4])

    _plot_rmse_profile_combined(ax_a, summary)
    _plot_connected_profile_combined(ax_b, summary)

    connected_pivots = {dim: _pivot(summary, dim, 'connected_rate') for dim in [2, 3]}
    rmse_pivots = {
        dim: np.log10(
            _pivot(summary, dim, 'global_centered_weight_rmse_median')
            .replace(0.0, np.nan)
            .fillna(1e-16)
            .clip(lower=1e-16)
        )
        for dim in [2, 3]
    }

    im_rmse_2d = _heatmap(ax_c, rmse_pivots[2], 'managua', vmin=-16.0, vmax=0.0, ylabel=True, xlabel=True)
    im_rmse_3d = _heatmap(ax_d, rmse_pivots[3], 'managua', vmin=-16.0, vmax=0.0, ylabel=False, xlabel=True)
    im_conn_2d = _heatmap(ax_e, connected_pivots[2], 'vanimo', vmin=0.0, vmax=1.0, ylabel=False, xlabel=True)
    im_conn_3d = _heatmap(ax_f, connected_pivots[3], 'vanimo', vmin=0.0, vmax=1.0, ylabel=False, xlabel=True)

    fig.subplots_adjust(left=0.065, right=0.985, top=0.90, bottom=0.095)
    fig.canvas.draw()

    lineplot_height = ax_c.get_position().height
    heat_height_scale = 0.94
    heat_y_shift = 0.028
    new_heat_height = ax_c.get_position().height * heat_height_scale
    for ax in (ax_c, ax_d, ax_e, ax_f):
        pos = ax.get_position()
        ax.set_position([pos.x0, pos.y0 + heat_y_shift, pos.width, new_heat_height])

    colorbar_height_scale = 0.72
    for cax in (cax_rmse, cax_conn):
        pos = cax.get_position()
        new_height = pos.height * colorbar_height_scale
        new_y0 = pos.y0 + 0.5 * (pos.height - new_height) + 0.022
        cax.set_position([pos.x0, new_y0, pos.width, new_height])

    fig.canvas.draw()

    pos_c = ax_c.get_position()
    pos_d = ax_d.get_position()
    pos_e = ax_e.get_position()
    pos_f = ax_f.get_position()

    top_row_top = 0.887
    ax_a.set_position([pos_c.x0, top_row_top - lineplot_height, pos_d.x1 - pos_c.x0, lineplot_height])
    ax_b.set_position([pos_e.x0, top_row_top - lineplot_height, pos_f.x1 - pos_e.x0, lineplot_height])

    _panel_label(ax_a, '(a)', x=-0.08, y=1.03)
    _panel_label(ax_b, '(b)', x=-0.08, y=1.03)
    _panel_label(ax_c, '(c)', x=-0.16, y=1.03)
    _panel_label(ax_d, '(d)', x=-0.16, y=1.03)
    _panel_label(ax_e, '(e)', x=-0.16, y=1.03)
    _panel_label(ax_f, '(f)', x=-0.16, y=1.03)

    cbar_rmse = fig.colorbar(im_rmse_2d, cax=cax_rmse, orientation='horizontal')
    cbar_rmse.set_label('log10 global aligned RMSE')
    cbar_conn = fig.colorbar(im_conn_2d, cax=cax_conn, orientation='horizontal')
    cbar_conn.set_label('connected rate')

    legend_handles = [
        Line2D([0], [0], color='#1f77b4', linewidth=2.0),
        Line2D([0], [0], color='#d62728', linewidth=2.0),
        Line2D([0], [0], color='#2ca02c', linewidth=2.1),
        Line2D([0], [0], color='#444444', linewidth=2.0, marker='o', markersize=4.8, linestyle='-'),
        Line2D(
            [0], [0], color='#444444', linewidth=2.0, marker='s', markersize=4.8,
            markerfacecolor='white', markeredgecolor='#444444', markeredgewidth=1.1,
            linestyle=(0, (1.0, 1.6)), dash_capstyle='round'
        ),
    ]
    legend_labels = ['componentwise', 'global', 'connected rate', '2D', '3D']
    fig.legend(
        legend_handles,
        legend_labels,
        loc='upper center',
        bbox_to_anchor=(0.5, 0.976),
        ncol=5,
        frameon=False,
        fontsize=8.9,
        handlelength=2.4,
        columnspacing=1.25,
    )

    _save_figure(fig, outpath, dpi=300)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, default=Path('results/missing_data_manuscript/runs.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/missing_data_manuscript/manuscript_analysis'))
    parser.add_argument('--figure-path', type=Path, default=None)
    args = parser.parse_args()

    runs = pd.read_csv(args.runs)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = aggregate_runs(runs)
    summary.to_csv(args.output_dir / 'summary.csv', index=False)
    summary.to_latex(args.output_dir / 'summary.tex', index=False, float_format='%.3e')

    build_transition_heatmap(summary, args.output_dir / 'transition_heatmap.png')
    build_alignment_profile(summary, args.output_dir / 'alignment_profile.png')
    composite_output = args.output_dir / 'figure_C_missing_data_composite.png'
    build_composite_figure(summary, composite_output)
    if args.figure_path is not None and args.figure_path.resolve() != composite_output.resolve():
        _copy_figure_pair(composite_output, args.figure_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
