"""Summarize the J4d box-margin robustness sweep.

This script does not rerun the tessellation analysis itself. Instead, it reads a
collection of existing ``analyze_qtaim_mask_transfer.py`` output directories,
extracts a few key metrics, and writes a compact comparison table.

Typical usage is:

    python scripts/qtaim/analyze_qtaim_box_margin_sensitivity.py \
        results/qtaim_main/J4_mask_transfer_margin3 \
        results/qtaim_main/J4_mask_transfer_margin5 \
        results/qtaim_main/J4_mask_transfer_margin7 \
        --labels 3A 5A 7A
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]

SUBSETS = ('all', 'nonbonded')
MODELS = ('voronoi', 'recovered_powerfit')


def _binary_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=bool)
    y_pred = np.asarray(y_pred, dtype=bool)
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum((~y_true) & y_pred))
    fn = int(np.sum(y_true & (~y_pred)))
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return float(2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0


def _average_precision(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    positives = int(y_true.sum())
    if positives == 0:
        return float('nan')
    order = np.argsort(-y_score, kind='mergesort')
    y = y_true[order]
    tp = np.cumsum(y)
    fp = np.cumsum(1 - y)
    precision = tp / np.maximum(tp + fp, 1)
    return float((precision * y).sum() / positives)


def _extract_label(path: Path) -> str:
    name = path.name
    if 'margin' in name.lower():
        return name.replace('_', ' ')
    return name


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _metric_rows(label: str, run_dir: Path) -> list[dict[str, object]]:
    edge_path = run_dir / 'edge_level.csv'
    if not edge_path.exists():
        raise FileNotFoundError(f'missing edge_level.csv in {run_dir}')
    edge = pd.read_csv(edge_path)
    rows: list[dict[str, object]] = []
    for model in MODELS:
        model_df = edge[edge['model'] == model].copy()
        for subset in SUBSETS:
            subset_mask = np.ones(len(model_df), dtype=bool) if subset == 'all' else model_df['is_nonbonded'].astype(bool).to_numpy()
            y = model_df['is_qtaim_edge'].astype(bool).to_numpy()
            pred_visible = model_df['keep_visible'].astype(bool).to_numpy()
            pred_thr = model_df['keep_visible_non_sliver'].astype(bool).to_numpy() & (model_df['intersection_edge_min_dist'].astype(float).to_numpy() >= 0.5)
            rows.append(
                {
                    'label': label,
                    'run_dir': _display_path(run_dir),
                    'model': model,
                    'subset': subset,
                    'visible_f1': _binary_f1(y[subset_mask], pred_visible[subset_mask]),
                    'visible_clearance05_f1': _binary_f1(y[subset_mask], pred_thr[subset_mask]),
                }
            )
        hard = model_df[model_df['keep_visible'].astype(bool) & model_df['is_nonbonded'].astype(bool)].copy()
        y_hard = hard['is_qtaim_edge'].astype(int).to_numpy()
        rows.append(
            {
                'label': label,
                'run_dir': _display_path(run_dir),
                'model': model,
                'subset': 'visible_nonbonded_ranking',
                'clearance_ap': _average_precision(y_hard, hard['intersection_edge_min_dist'].astype(float).to_numpy()),
                'distance_ap': _average_precision(y_hard, -hard['bond_length_angstrom'].astype(float).to_numpy()),
                'margin_safe_fraction': float(hard['analytic_margin_safe'].astype(bool).mean()) if 'analytic_margin_safe' in hard.columns else float('nan'),
            }
        )
    return rows


def build_report(df: pd.DataFrame) -> str:
    lines = [
        '# Experiment J4d: box-margin robustness summary',
        '',
        'This report compares precomputed J4b mask-transfer runs produced at different padded-box margins.',
        (
            "Like J4b itself, the reported F1 and ranking scores are "
            "computed within each model's realized-face archive; "
            'fixed-denominator support recovery against the common QTAIM '
            'graph is reported separately in J3.'
        ),
        'The table is intended to answer a narrow question: do the visible-graph and clearance diagnostics change materially as the clipping box is enlarged?',
        '',
    ]
    for label in df['label'].drop_duplicates():
        sub = df[df['label'] == label]
        lines.append(f'## {label}')
        for model in MODELS:
            vis_all = sub[(sub['model'] == model) & (sub['subset'] == 'all')].iloc[0]
            vis_nb = sub[(sub['model'] == model) & (sub['subset'] == 'nonbonded')].iloc[0]
            rank = sub[(sub['model'] == model) & (sub['subset'] == 'visible_nonbonded_ranking')].iloc[0]
            lines.append(
                f'- {model}: visible F1 (all/nonbonded) = '
                f'**{vis_all["visible_f1"]:.3f} / {vis_nb["visible_f1"]:.3f}**; '
                f'clearance@0.50 F1 (all/nonbonded) = '
                f'**{vis_all["visible_clearance05_f1"]:.3f} / {vis_nb["visible_clearance05_f1"]:.3f}**; '
                f'visible-nonbonded clearance AP = **{rank["clearance_ap"]:.3f}**; '
                f'short-distance AP = **{rank["distance_ap"]:.3f}**; '
                f'margin-safe fraction = **{rank["margin_safe_fraction"]:.3f}**.'
            )
        lines.append('')
    return '\n'.join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dirs', nargs='+', help='One or more J4 mask-transfer output directories.')
    parser.add_argument('--labels', nargs='*', default=None, help='Optional labels matching the provided directories.')
    parser.add_argument('--output-dir', default='results/qtaim_main/J4_box_margin_summary', help='Directory for the summary CSV and report.')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dirs = [Path(raw).resolve() for raw in args.run_dirs]
    labels = list(args.labels or [])
    if labels and len(labels) != len(run_dirs):
        raise ValueError('--labels must match the number of run directories when provided')
    if not labels:
        labels = [_extract_label(path) for path in run_dirs]
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for label, run_dir in zip(labels, run_dirs, strict=True):
        rows.extend(_metric_rows(label, run_dir))
    df = pd.DataFrame.from_records(rows)
    df.to_csv(output_dir / 'summary.csv', index=False)
    (output_dir / 'REPORT.md').write_text(build_report(df), encoding='utf-8')

    meta = {
        'n_runs': int(len(run_dirs)),
        'run_dirs': [_display_path(path) for path in run_dirs],
        'labels': labels,
    }
    (output_dir / 'summary.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(f'Wrote J4d box-margin summary to {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
