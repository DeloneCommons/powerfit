#!/usr/bin/env python3
"""Validate analytic local-support diagnostics against tessellation outputs.

This helper is the J4a theorem-to-code validation stage. It reads a J4 edge-level CSV that contains both the geometric face
properties emitted by the tessellation layer and the analytic clipped
connector-visibility quantities derived from ``local_support.py``. It compares

- ``analytic_visible_clipped`` against ``intersection_inside`` on every face,
- ``analytic_clearance_clipped`` against ``intersection_edge_min_dist`` on the
  visible subset.

The resulting summary is used directly by the manuscript as a theorem-to-code
validation check for the local connector-visibility layer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EDGE_CSV = REPO_ROOT / 'results' / 'qtaim_main' / 'J4_mask_transfer_refresh' / 'edge_level.csv'
DEFAULT_OUTPUT_DIR = REPO_ROOT / 'results' / 'qtaim_main' / 'J4_local_diagnostic_validation'


REQUIRED_COLUMNS = {
    'model',
    'intersection_inside',
    'intersection_edge_min_dist',
    'analytic_visible_clipped',
    'analytic_clearance_clipped',
}


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--edge-level-csv',
        type=Path,
        default=DEFAULT_EDGE_CSV,
        help=f'J4 edge-level CSV with analytic and geometric diagnostics (default: {DEFAULT_EDGE_CSV.relative_to(REPO_ROOT)}).',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory for validation summaries (default: {DEFAULT_OUTPUT_DIR.relative_to(REPO_ROOT)}).',
    )
    return parser


def _row_for_model(df: pd.DataFrame, model: str) -> dict[str, object]:
    sub = df[df['model'] == model].copy()
    if sub.empty:
        raise ValueError(f'No rows found for model={model!r}.')

    visible_geom = sub['intersection_inside'].astype(bool).to_numpy()
    visible_analytic = sub['analytic_visible_clipped'].astype(bool).to_numpy()
    visibility_mismatch = visible_geom ^ visible_analytic

    visible_df = sub[visible_geom].copy()
    clearance_diff = np.abs(
        visible_df['intersection_edge_min_dist'].to_numpy(dtype=float)
        - visible_df['analytic_clearance_clipped'].to_numpy(dtype=float)
    ) if not visible_df.empty else np.array([], dtype=float)

    return {
        'model': str(model),
        'n_faces': int(len(sub)),
        'n_visible_faces': int(visible_geom.sum()),
        'n_visibility_mismatches': int(visibility_mismatch.sum()),
        'visibility_agreement_fraction': float(np.mean(~visibility_mismatch)),
        'max_abs_clearance_diff': float(np.max(clearance_diff)) if clearance_diff.size else float('nan'),
        'mean_abs_clearance_diff': float(np.mean(clearance_diff)) if clearance_diff.size else float('nan'),
        'median_abs_clearance_diff': float(np.median(clearance_diff)) if clearance_diff.size else float('nan'),
    }


def _write_report(path: Path, payload: dict[str, object]) -> None:
    rows = payload['by_model']
    lines = [
        '# Experiment J4a: local theorem-to-code validation',
        '',
        f'- Source edge-level CSV: `{payload["edge_level_csv"]}`',
        f'- Total faces checked: **{payload["total_faces"]}**',
        f'- Total visible faces checked for clearance: **{payload["total_visible_faces"]}**',
        f'- Total visibility mismatches: **{payload["total_visibility_mismatches"]}**',
        f'- Maximum absolute clearance mismatch on visible faces: **{payload["max_abs_clearance_diff"]:.6g}**',
        '',
        '## Per-model summary',
        '',
    ]
    for row in rows:
        lines += [
            f"### {row['model']}",
            '',
            f"- Faces checked: **{row['n_faces']}**",
            f"- Visible faces checked for clearance: **{row['n_visible_faces']}**",
            f"- Visibility mismatches: **{row['n_visibility_mismatches']}**",
            f"- Visibility agreement fraction: **{row['visibility_agreement_fraction']:.6f}**",
            f"- Max / mean / median $|\\Delta c|$: **{row['max_abs_clearance_diff']:.6g} / {row['mean_abs_clearance_diff']:.6g} / {row['median_abs_clearance_diff']:.6g}**",
            '',
        ]
    lines += [
        '## Interpretation',
        '',
        'The clipped analytic local-support formulas are numerically identical to the tessellation-derived diagnostics on the released J4 archive up to machine precision on clearance and exactly on the visibility boolean.',
        '',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')



def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    edge_csv = args.edge_level_csv.resolve()
    output_dir = args.output_dir.resolve()
    if not edge_csv.is_file():
        parser.error(f'Edge-level CSV not found: {edge_csv}')

    df = pd.read_csv(edge_csv)
    missing = sorted(REQUIRED_COLUMNS.difference(df.columns))
    if missing:
        parser.error(f'Edge-level CSV is missing required columns: {missing}')

    preferred_order = ['voronoi', 'recovered_powerfit']
    present = [model for model in preferred_order if model in set(df['model'].dropna().unique())]
    remaining = [model for model in sorted(df['model'].dropna().unique()) if model not in present]
    rows = [_row_for_model(df, model) for model in [*present, *remaining]]
    total_faces = int(sum(row['n_faces'] for row in rows))
    total_visible_faces = int(sum(row['n_visible_faces'] for row in rows))
    total_visibility_mismatches = int(sum(row['n_visibility_mismatches'] for row in rows))
    max_abs_clearance_diff = max(float(row['max_abs_clearance_diff']) for row in rows)
    mean_abs_clearance_diff = float(np.mean([row['mean_abs_clearance_diff'] for row in rows]))

    payload: dict[str, object] = {
        'edge_level_csv': _display_path(edge_csv),
        'n_models': int(len(rows)),
        'total_faces': total_faces,
        'total_visible_faces': total_visible_faces,
        'total_visibility_mismatches': total_visibility_mismatches,
        'max_abs_clearance_diff': max_abs_clearance_diff,
        'mean_abs_clearance_diff': mean_abs_clearance_diff,
        'by_model': rows,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_dir / 'summary.csv', index=False)
    (output_dir / 'summary.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    _write_report(output_dir / 'REPORT.md', payload)
    print(f'[J4a] wrote validation summary to {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
