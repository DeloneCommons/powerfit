"""Compare QTAIM support graphs against Voronoi and one-shot powerfit models.

This analysis script reads parsed QTAIM JSON records, measures graph agreement
and separator-position diagnostics, and writes CSV summaries for the showcase or
main dataset. Console progress reporting does not alter any saved analysis
artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pyvoro2 as pv

from _cli_progress import iter_progress, progress_write, tqdm_available


def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw))


def _csv_path(base_dir: Path, raw: str) -> Path:
    candidate = Path(_expand(raw))
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def undirected(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def f1(pairs_pred, pairs_true):
    pred = set(pairs_pred)
    true = set(pairs_true)
    tp = len(pred & true)
    fp = len(pred - true)
    fn = len(true - pred)
    prec = tp / len(pred) if pred else float('nan')
    rec = tp / len(true) if true else float('nan')
    f1_value = (
        2 * prec * rec / (prec + rec)
        if pred and true and (prec + rec) > 0
        else (1.0 if not pred and not true else 0.0)
    )
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': prec, 'recall': rec, 'f1': f1_value}


def projection_fraction_and_offset(pi, pj, x):
    d = pj - pi
    dd = float(np.dot(d, d))
    t = float(np.dot(x - pi, d) / dd)
    off = float(np.linalg.norm(np.cross(x - pi, d)) / math.sqrt(dd))
    return t, off


def box_for_points(points, margin: float):
    mins = points.min(axis=0) - margin
    maxs = points.max(axis=0) + margin
    return pv.Box(bounds=tuple((float(mins[k]), float(maxs[k])) for k in range(3)))


def compute_cells(points, box, radii=None):
    mode = 'power' if radii is not None else 'standard'
    cells, diag = pv.compute(
        points,
        domain=box,
        mode=mode,
        radii=radii,
        return_vertices=True,
        return_faces=True,
        return_adjacency=False,
        return_diagnostics=True,
        tessellation_check='diagnose',
    )
    pv.annotate_face_properties(cells, domain=box, diagnostics=diag)
    return cells, diag


def extract_edges(cells):
    rows = []
    seen = set()
    for c in cells:
        i = int(c['id'])
        for f in c.get('faces', []):
            j = int(f.get('adjacent_cell', -1))
            if j < 0:
                continue
            key = undirected(i, j)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                'i': key[0],
                'j': key[1],
                'intersection_inside': bool(f.get('intersection_inside', False)),
                'intersection_edge_min_dist': float(f.get('intersection_edge_min_dist', float('nan'))),
                'intersection_centroid_dist': float(f.get('intersection_centroid_dist', float('nan'))),
                'area': float(f.get('area', float('nan'))),
                'intersection': list(map(float, f.get('intersection', [float('nan')] * 3))),
                'centroid': list(map(float, f.get('centroid', [float('nan')] * 3))),
                'normal': list(map(float, f.get('normal', [float('nan')] * 3))),
            })
    return rows


def _pick_label(row: dict[str, str], default_stem: str, row_index: int) -> str:
    value = row.get('system_key', '').strip()
    if value:
        return value
    value = row.get('system_id', '').strip()
    if value:
        return value
    value = row.get('name', '').strip()
    if value:
        return value.replace(' ', '_')
    return default_stem or f'row_{row_index}'


def load_manifest(manifest_csv: Path) -> pd.DataFrame:
    base_dir = manifest_csv.parent
    with manifest_csv.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if 'json_path' not in fieldnames:
            raise ValueError('Manifest must contain json_path column')
        rows = []
        for idx, raw_row in enumerate(reader, start=2):
            if not any((value or '').strip() for value in raw_row.values()):
                continue
            json_path = _csv_path(base_dir, raw_row['json_path'].strip())
            label = _pick_label(raw_row, json_path.stem, idx)
            rows.append({
                'system_key': label,
                'name': (raw_row.get('name') or '').strip() or label,
                'group': (raw_row.get('group') or '').strip() or '',
                'is_idealized': str(raw_row.get('is_idealized', '')).strip().lower() in {'true', '1', 'yes'},
                'json_path': json_path,
            })
    if not rows:
        raise ValueError(f'No rows found in manifest: {manifest_csv}')
    return pd.DataFrame(rows)


def choose_default_output_dir(manifest_csv: Path) -> Path:
    repo_root = manifest_csv.parents[2] if len(manifest_csv.parents) >= 3 else manifest_csv.parent
    candidate = repo_root / 'results' / f'{manifest_csv.parent.name}_voronoi'
    if candidate.parent.exists():
        return candidate
    return manifest_csv.parent / 'voronoi_analysis'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Compare QTAIM BCP support graphs against ordinary Voronoi and one-shot powerfit.'
    )
    parser.add_argument('manifest_csv', help='Manifest containing json_path plus optional labels.')
    parser.add_argument('--output-dir', help='Directory for CSV outputs. Defaults to results/<dataset>_voronoi when possible.')
    parser.add_argument('--margin', type=float, default=5.0, help='Bounding-box margin in angstrom (default: 5.0).')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm/text progress output.')
    return parser


def parse_args(argv: Iterable[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest_csv = Path(_expand(args.manifest_csv)).resolve()
    if not manifest_csv.is_file():
        parser.error(f'Manifest CSV not found: {manifest_csv}')
    output_dir = Path(_expand(args.output_dir)).resolve() if args.output_dir else choose_default_output_dir(manifest_csv)
    return manifest_csv, output_dir, float(args.margin), bool(args.no_progress)


def load_system(row):
    with open(row['json_path'], 'r', encoding='utf-8') as handle:
        obj = json.load(handle)
    points = np.array([a['position_angstrom'] for a in obj['atoms']], dtype=float)
    cp_by_idx = {cp['cp_index']: cp for cp in obj['critical_points']}
    q_edges = []
    proj_rows = []
    for edge in obj['bcp_graph']:
        i = edge['atom_i'] - 1
        j = edge['atom_j'] - 1
        q_edges.append(undirected(i, j))
        cp = cp_by_idx[edge['cp_index']]
        bcp = np.array(cp['position_angstrom'], dtype=float)
        t, off = projection_fraction_and_offset(points[i], points[j], bcp)
        proj_rows.append({
            'system_name': row['name'],
            'system_key': row['system_key'],
            'group': row['group'],
            'is_idealized': bool(row['is_idealized']),
            'atom_i': i,
            'atom_j': j,
            'pair': f'{i + 1}-{j + 1}',
            'cp_index': int(edge['cp_index']),
            'fraction_obs': t,
            'offset_angstrom': off,
            'bond_length_angstrom': float(np.linalg.norm(points[j] - points[i])),
            'offset_over_length': off / float(np.linalg.norm(points[j] - points[i])),
        })
    return obj, points, sorted(set(q_edges)), proj_rows


def main(argv: Iterable[str] | None = None) -> int:
    manifest_csv, output_dir, margin, no_progress = parse_args(argv)
    systems = load_manifest(manifest_csv)

    all_proj_rows = []
    summary_rows = []
    edge_diag_rows = []
    power_diag_rows = []
    pair_diff_rows = []

    system_rows = systems.to_dict(orient='records')
    total = len(system_rows)
    progress_write(f'Loaded {total} QTAIM systems from {manifest_csv}')
    progress_write(f'Voronoi comparison margin: {margin:.3f} Å; output dir: {output_dir}')
    if not no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')

    row_iter = iter_progress(system_rows, total=total, desc='voronoi compare', disable=no_progress, unit='system')
    for index, row in enumerate(row_iter, start=1):
        if hasattr(row_iter, 'set_postfix_str'):
            row_iter.set_postfix_str(row['system_key'])
        prefix = f"[{index}/{total}] {row['system_key']}"
        progress_write(f'{prefix} -> start')
        obj, points, q_edges, proj_rows = load_system(row)
        all_proj_rows.extend(proj_rows)
        box = box_for_points(points, margin=margin)

        cells_std, _diag_std = compute_cells(points, box, radii=None)
        std_edges = extract_edges(cells_std)
        std_raw = [undirected(r['i'], r['j']) for r in std_edges]
        std_vis = [undirected(r['i'], r['j']) for r in std_edges if r['intersection_inside']]
        metrics_std_raw = f1(std_raw, q_edges)
        metrics_std_vis = f1(std_vis, q_edges)

        midpoint_abs_err = [abs(pr['fraction_obs'] - 0.5) for pr in proj_rows]
        midpoint_rmse = (
            float(np.sqrt(np.mean([(pr['fraction_obs'] - 0.5) ** 2 for pr in proj_rows])))
            if proj_rows else float('nan')
        )
        midpoint_mae = float(np.mean(midpoint_abs_err)) if proj_rows else float('nan')

        cons_list = [(pr['atom_i'], pr['atom_j'], pr['fraction_obs']) for pr in proj_rows]
        constraints = pv.resolve_pair_bisector_constraints(points, cons_list, measurement='fraction', domain=box)
        fit = pv.fit_power_weights(points, constraints, measurement='fraction', domain=box, connectivity_check='diagnose')
        realized = pv.match_realized_pairs(
            points,
            domain=box,
            radii=fit.radii,
            constraints=constraints,
            return_boundary_measure=True,
            return_tessellation_diagnostics=True,
            tessellation_check='diagnose',
            unaccounted_pair_check='diagnose',
        )
        cells_pow, _diag_pow = compute_cells(points, box, radii=fit.radii)
        pow_edges = extract_edges(cells_pow)
        pow_raw = [undirected(r['i'], r['j']) for r in pow_edges]
        pow_vis = [undirected(r['i'], r['j']) for r in pow_edges if r['intersection_inside']]
        metrics_pow_raw = f1(pow_raw, q_edges)
        metrics_pow_vis = f1(pow_vis, q_edges)
        fit_pred = list(map(float, np.asarray(fit.predicted_fraction).tolist()))
        fit_rmse = (
            float(np.sqrt(np.mean([(a - b) ** 2 for a, b in zip(fit_pred, [pr['fraction_obs'] for pr in proj_rows])])))
            if proj_rows else float('nan')
        )
        fit_mae = (
            float(np.mean([abs(a - b) for a, b in zip(fit_pred, [pr['fraction_obs'] for pr in proj_rows])]))
            if proj_rows else float('nan')
        )

        summary_rows.append({
            'system_key': row['system_key'],
            'name': row['name'],
            'group': row['group'],
            'is_idealized': bool(row['is_idealized']),
            'n_atoms': len(points),
            'n_qtaim_bcp': len(q_edges),
            'n_qtaim_rcp': int(obj['counts']['rcp']),
            'n_qtaim_ccp': int(obj['counts']['ccp']),
            'vor_raw_edges': len(std_raw),
            'vor_visible_edges': len(std_vis),
            'pow_raw_edges': len(pow_raw),
            'pow_visible_edges': len(pow_vis),
            'vor_raw_precision': metrics_std_raw['precision'],
            'vor_raw_recall': metrics_std_raw['recall'],
            'vor_raw_f1': metrics_std_raw['f1'],
            'vor_visible_precision': metrics_std_vis['precision'],
            'vor_visible_recall': metrics_std_vis['recall'],
            'vor_visible_f1': metrics_std_vis['f1'],
            'pow_raw_precision': metrics_pow_raw['precision'],
            'pow_raw_recall': metrics_pow_raw['recall'],
            'pow_raw_f1': metrics_pow_raw['f1'],
            'pow_visible_precision': metrics_pow_vis['precision'],
            'pow_visible_recall': metrics_pow_vis['recall'],
            'pow_visible_f1': metrics_pow_vis['f1'],
            'midpoint_fraction_mae': midpoint_mae,
            'midpoint_fraction_rmse': midpoint_rmse,
            'powerfit_fraction_mae': fit_mae,
            'powerfit_fraction_rmse': fit_rmse,
            'realized_requested_pairs': int(np.sum(realized.realized)),
            'n_requested_pairs': len(q_edges),
            'all_requested_realized': bool(np.all(realized.realized)),
            'mean_bcp_offset': float(np.mean([pr['offset_angstrom'] for pr in proj_rows])) if proj_rows else float('nan'),
            'max_bcp_offset': float(np.max([pr['offset_angstrom'] for pr in proj_rows])) if proj_rows else float('nan'),
        })

        for r in std_edges:
            pair = undirected(r['i'], r['j'])
            edge_diag_rows.append({
                'system_key': row['system_key'],
                'model': 'voronoi',
                'i': pair[0],
                'j': pair[1],
                'pair': f'{pair[0] + 1}-{pair[1] + 1}',
                'is_qtaim_edge': pair in q_edges,
                'intersection_inside': r['intersection_inside'],
                'intersection_edge_min_dist': r['intersection_edge_min_dist'],
                'area': r['area'],
            })
        for r in pow_edges:
            pair = undirected(r['i'], r['j'])
            power_diag_rows.append({
                'system_key': row['system_key'],
                'model': 'powerfit',
                'i': pair[0],
                'j': pair[1],
                'pair': f'{pair[0] + 1}-{pair[1] + 1}',
                'is_qtaim_edge': pair in q_edges,
                'intersection_inside': r['intersection_inside'],
                'intersection_edge_min_dist': r['intersection_edge_min_dist'],
                'area': r['area'],
            })

    summary_df = pd.DataFrame(summary_rows)
    edge_df = pd.DataFrame(edge_diag_rows)
    power_df = pd.DataFrame(power_diag_rows)
    proj_df = pd.DataFrame(all_proj_rows)

    if {'benzene_sym', 'benzene_broken'}.issubset(set(summary_df['system_key'])):
        pairs = [('benzene', ['benzene_sym', 'benzene_broken'])]
    else:
        pairs = []
    if {'adamantane_sym', 'adamantane_broken'}.issubset(set(summary_df['system_key'])):
        pairs.append(('adamantane', ['adamantane_sym', 'adamantane_broken']))

    for scaffold, keys in pairs:
        for model_name, df in [('voronoi', edge_df), ('powerfit', power_df)]:
            pair_sets = {}
            vis_sets = {}
            for key in keys:
                sub = df[df.system_key == key]
                pair_sets[key] = set(map(tuple, sub[['i', 'j']].values.tolist()))
                vis_sets[key] = set(map(tuple, sub[sub.intersection_inside][['i', 'j']].values.tolist()))
            a, b = keys
            pair_diff_rows.append({'scaffold': scaffold, 'model': model_name, 'kind': 'raw_only_in_first', 'pairs': sorted(pair_sets[a] - pair_sets[b])})
            pair_diff_rows.append({'scaffold': scaffold, 'model': model_name, 'kind': 'raw_only_in_second', 'pairs': sorted(pair_sets[b] - pair_sets[a])})
            pair_diff_rows.append({'scaffold': scaffold, 'model': model_name, 'kind': 'visible_only_in_first', 'pairs': sorted(vis_sets[a] - vis_sets[b])})
            pair_diff_rows.append({'scaffold': scaffold, 'model': model_name, 'kind': 'visible_only_in_second', 'pairs': sorted(vis_sets[b] - vis_sets[a])})

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output_dir / 'summary.csv', index=False)
    edge_df.to_csv(output_dir / 'voronoi_edges.csv', index=False)
    power_df.to_csv(output_dir / 'powerfit_edges.csv', index=False)
    proj_df.to_csv(output_dir / 'bcp_projection.csv', index=False)
    pd.DataFrame(pair_diff_rows).to_csv(output_dir / 'symmetry_breaking_diffs.csv', index=False)

    progress_write(f'Wrote comparison outputs to {output_dir}')
    progress_write(summary_df.to_string(index=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
