#!/usr/bin/env python3
"""Build the historical v1.0.0 J4b precision--recall transition figure.

The archived J4b analysis writes the numeric summaries under
``results/qtaim_main/J4_mask_transfer_refresh``.  This script does not rerun the
molecular benchmark.  It only redraws the manuscript-facing figure from the
archived ``mask_summary.csv`` and ``clearance_sweep.csv`` tables.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from _figure_io import save_figure_pair


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASK_SUMMARY = REPO_ROOT / 'results' / 'qtaim_main' / 'J4_mask_transfer_refresh' / 'mask_summary.csv'
DEFAULT_CLEARANCE_SWEEP = REPO_ROOT / 'results' / 'qtaim_main' / 'J4_mask_transfer_refresh' / 'clearance_sweep.csv'
DEFAULT_OUTPUT_PDF = REPO_ROOT / 'build' / 'legacy' / 'figures' / 'figure_J4_mask_transfer.pdf'
DEFAULT_OUTPUT_PNG = REPO_ROOT / 'build' / 'legacy' / 'figures' / 'figure_J4_mask_transfer.png'

MODEL_LABELS = {
    'voronoi': 'Voronoi',
    'recovered_powerfit': 'rec. powerfit',
}
SUBSET_LABELS = {
    'all': 'all faces',
    'nonbonded': 'nonbonded faces',
}
STAGE_MARKERS = {
    'raw': 'o',
    'visible': 's',
    'clearance_0p50': 'D',
}
STAGE_LABELS = {
    'raw': 'raw',
    'visible': 'visible',
    'clearance_0p50': r'visible + clearance $\geq 0.50$ $\AA$',
}
TRAJECTORIES = [
    ('voronoi', 'all', 'C0', '-'),
    ('recovered_powerfit', 'all', 'C1', '-'),
    ('voronoi', 'nonbonded', 'C0', (0, (2.0, 1.6))),
    ('recovered_powerfit', 'nonbonded', 'C1', (0, (2.0, 1.6))),
]


@dataclass(frozen=True)
class MetricPoint:
    precision: float
    recall: float
    f1: float


def _float(row: dict[str, str], name: str) -> float:
    return float(row[name])


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _find_mask(rows: list[dict[str, str]], *, model: str, subset: str, mask: str) -> MetricPoint:
    for row in rows:
        if row['model'] == model and row['subset'] == subset and row['mask'] == mask:
            return MetricPoint(
                precision=_float(row, 'precision'),
                recall=_float(row, 'recall'),
                f1=_float(row, 'f1'),
            )
    raise KeyError(f'Missing J4 mask row: model={model}, subset={subset}, mask={mask}')


def _find_clearance(
    rows: list[dict[str, str]], *, model: str, subset: str, threshold: float
) -> MetricPoint:
    for row in rows:
        if row['model'] != model or row['subset'] != subset:
            continue
        if abs(float(row['clearance_threshold_angstrom']) - threshold) < 1.0e-9:
            return MetricPoint(
                precision=_float(row, 'precision'),
                recall=_float(row, 'recall'),
                f1=_float(row, 'f1'),
            )
    raise KeyError(f'Missing J4 clearance row: model={model}, subset={subset}, threshold={threshold}')


def _trajectory_points(
    mask_rows: list[dict[str, str]],
    sweep_rows: list[dict[str, str]],
    *,
    model: str,
    subset: str,
    threshold: float,
) -> list[tuple[str, MetricPoint]]:
    return [
        ('raw', _find_mask(mask_rows, model=model, subset=subset, mask='raw')),
        ('visible', _find_mask(mask_rows, model=model, subset=subset, mask='visible')),
        (
            'clearance_0p50',
            _find_clearance(sweep_rows, model=model, subset=subset, threshold=threshold),
        ),
    ]


def _style_legend_title(legend: plt.Legend) -> None:
    legend.get_title().set_fontweight('bold')


def build_figure(
    *,
    mask_summary_csv: Path,
    clearance_sweep_csv: Path,
    output_pdf: Path,
    output_png: Path,
    threshold: float = 0.50,
) -> None:
    mask_rows = _read_rows(mask_summary_csv)
    sweep_rows = _read_rows(clearance_sweep_csv)

    fig, (ax, legend_ax) = plt.subplots(
        nrows=2,
        figsize=(6.2, 4.55),
        layout='constrained',
        gridspec_kw={'height_ratios': [1.0, 0.27], 'hspace': 0.08},
    )
    legend_ax.axis('off')

    color_handles = [
        Line2D([0], [0], color=color, linewidth=1.55, label=MODEL_LABELS[model])
        for model, color in (('voronoi', 'C0'), ('recovered_powerfit', 'C1'))
    ]
    subset_handles = [
        Line2D([0], [0], color='0.25', linestyle=linestyle, linewidth=1.55, label=SUBSET_LABELS[subset])
        for subset, linestyle in (('all', '-'), ('nonbonded', (0, (2.0, 1.6))))
    ]

    for model, subset, color, linestyle in TRAJECTORIES:
        points = _trajectory_points(mask_rows, sweep_rows, model=model, subset=subset, threshold=threshold)
        recalls = [point.recall for _, point in points]
        precisions = [point.precision for _, point in points]
        ax.plot(
            precisions,
            recalls,
            color=color,
            linestyle=linestyle,
            linewidth=1.45,
            alpha=0.95,
        )
        for stage, point in points:
            ax.scatter(
                [point.precision],
                [point.recall],
                marker=STAGE_MARKERS[stage],
                s=42,
                color=color,
                edgecolor='black',
                linewidth=0.45,
                zorder=5,
            )

    ax.set_xlabel('archive-conditioned precision')
    ax.set_ylabel('archive-conditioned recall', labelpad=9.0)
    ax.set_xlim(0.0, 1.02)
    ax.set_ylim(0.76, 1.01)
    ax.grid(True, alpha=0.22, linewidth=0.5)

    color_legend = legend_ax.legend(
        handles=color_handles,
        title='model',
        loc='upper left',
        bbox_to_anchor=(0.00, 0.94),
        frameon=False,
        fontsize=8.0,
        title_fontsize=8.0,
        handlelength=2.4,
        handletextpad=0.7,
        borderaxespad=0.0,
        labelspacing=0.45,
    )
    _style_legend_title(color_legend)
    legend_ax.add_artist(color_legend)

    subset_legend = legend_ax.legend(
        handles=subset_handles,
        title='subset',
        loc='upper left',
        bbox_to_anchor=(0.31, 0.94),
        frameon=False,
        fontsize=8.0,
        title_fontsize=8.0,
        handlelength=2.4,
        handletextpad=0.7,
        borderaxespad=0.0,
        labelspacing=0.45,
    )
    _style_legend_title(subset_legend)
    legend_ax.add_artist(subset_legend)

    stage_handles = [
        Line2D(
            [0],
            [0],
            marker=STAGE_MARKERS[name],
            color='none',
            markerfacecolor='white',
            markeredgecolor='black',
            markersize=5.9,
            label=label,
        )
        for name, label in STAGE_LABELS.items()
    ]
    stage_legend = legend_ax.legend(
        handles=stage_handles,
        title='stage',
        loc='upper left',
        bbox_to_anchor=(0.64, 0.94),
        frameon=False,
        fontsize=7.85,
        title_fontsize=8.0,
        handletextpad=0.7,
        borderaxespad=0.0,
        labelspacing=0.45,
    )
    _style_legend_title(stage_legend)

    save_figure_pair(
        fig,
        png_path=output_png,
        pdf_path=output_pdf,
        title=output_pdf.stem,
        png_dpi=300,
        bbox_inches='tight',
        pad_inches=0.02,
    )
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mask-summary-csv', type=Path, default=DEFAULT_MASK_SUMMARY)
    parser.add_argument('--clearance-sweep-csv', type=Path, default=DEFAULT_CLEARANCE_SWEEP)
    parser.add_argument('--output-pdf', type=Path, default=DEFAULT_OUTPUT_PDF)
    parser.add_argument('--output-png', type=Path, default=DEFAULT_OUTPUT_PNG)
    parser.add_argument('--threshold', type=float, default=0.50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_figure(
        mask_summary_csv=args.mask_summary_csv,
        clearance_sweep_csv=args.clearance_sweep_csv,
        output_pdf=args.output_pdf,
        output_png=args.output_png,
        threshold=args.threshold,
    )
    print(f'Wrote {args.output_pdf}')
    print(f'Wrote {args.output_png}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
