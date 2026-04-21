"""Compare QTAIM separator positions against midpoint and proatomic baselines.

The script reads parsed QTAIM JSON records and a precomputed pair-law lookup,
projects BCPs to atom-atom connectors, and writes edge-, molecule-, and pair-
level summaries for the main dataset.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover
    tqdm = None

from _proatomic_pairlaw import PairLawLookup, load_lookup_csv, write_metadata_json


@dataclass(frozen=True)
class ManifestRow:
    system_key: str
    name: str
    group: str
    json_path: Path


def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw))


def _csv_path(base_dir: Path, raw: str) -> Path:
    candidate = Path(_expand(raw))
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def _pick_label(row: dict[str, str], default_stem: str, row_index: int) -> str:
    for key in ('system_key', 'system_id', 'name'):
        value = (row.get(key) or '').strip()
        if value:
            return value.replace(' ', '_')
    return default_stem or f'row_{row_index}'


def projection_fraction_and_offset(pi: np.ndarray, pj: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    d = pj - pi
    dd = float(np.dot(d, d))
    t = float(np.dot(x - pi, d) / dd)
    off = float(np.linalg.norm(np.cross(x - pi, d)) / math.sqrt(dd))
    return t, off


def rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values)))) if values.size else float('nan')


def mae(values: np.ndarray) -> float:
    return float(np.mean(np.abs(values))) if values.size else float('nan')


def load_manifest(manifest_csv: Path) -> list[ManifestRow]:
    base_dir = manifest_csv.parent
    with manifest_csv.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if 'json_path' not in fieldnames:
            raise ValueError('Manifest must contain json_path column')
        rows: list[ManifestRow] = []
        for idx, raw_row in enumerate(reader, start=2):
            if not any((value or '').strip() for value in raw_row.values()):
                continue
            json_path = _csv_path(base_dir, raw_row['json_path'].strip())
            label = _pick_label(raw_row, json_path.stem, idx)
            rows.append(
                ManifestRow(
                    system_key=label,
                    name=(raw_row.get('name') or '').strip() or label,
                    group=(raw_row.get('group') or '').strip() or '',
                    json_path=json_path,
                )
            )
    if not rows:
        raise ValueError(f'No data rows found in manifest: {manifest_csv}')
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Compare projected QTAIM BCP separator positions against a midpoint baseline and '
            'the proatomic pair-law lookup.'
        )
    )
    parser.add_argument('manifest_csv', help='Manifest with json_path plus optional labels.')
    parser.add_argument('--lookup-csv', default=None, help='Pair-law lookup CSV. Defaults to data/proatomic/pairlaw/separator_lookup.csv.')
    parser.add_argument('--output-dir', default=None, help='Directory for analysis outputs. Defaults to results/<manifest-stem>_pairlaw/.')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm progress bars.')
    return parser


def parse_args(argv: Iterable[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest_csv = Path(_expand(args.manifest_csv)).resolve()
    if not manifest_csv.is_file():
        parser.error(f'Manifest CSV not found: {manifest_csv}')
    repo_root = Path(__file__).resolve().parents[2]
    lookup_csv = Path(_expand(args.lookup_csv)).resolve() if args.lookup_csv else (repo_root / 'data' / 'proatomic' / 'pairlaw' / 'separator_lookup.csv').resolve()
    if not lookup_csv.is_file():
        parser.error(f'Pair-law lookup not found: {lookup_csv}')
    output_dir = Path(_expand(args.output_dir)).resolve() if args.output_dir else (repo_root / 'results' / f'{manifest_csv.stem}_pairlaw').resolve()
    return args, manifest_csv, lookup_csv, output_dir


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _threshold_metrics(edge_rows: list[dict], label: str, predicate) -> dict:
    subset = [row for row in edge_rows if predicate(row)]
    if not subset:
        return {
            'label': label,
            'n_edges': 0,
            'fraction_rmse_mid': float('nan'),
            'fraction_rmse_proatomic': float('nan'),
            'angstrom_rmse_mid': float('nan'),
            'angstrom_rmse_proatomic': float('nan'),
            'fraction_mae_mid': float('nan'),
            'fraction_mae_proatomic': float('nan'),
            'angstrom_mae_mid': float('nan'),
            'angstrom_mae_proatomic': float('nan'),
            'proatomic_better_fraction': float('nan'),
        }
    mid_frac = np.array([row['t_mid'] - row['t_obs'] for row in subset], dtype=float)
    pro_frac = np.array([row['t_proatomic'] - row['t_obs'] for row in subset], dtype=float)
    mid_ang = np.array([row['x_mid_angstrom'] - row['x_obs_angstrom'] for row in subset], dtype=float)
    pro_ang = np.array([row['x_proatomic_angstrom'] - row['x_obs_angstrom'] for row in subset], dtype=float)
    return {
        'label': label,
        'n_edges': int(len(subset)),
        'fraction_rmse_mid': rmse(mid_frac),
        'fraction_rmse_proatomic': rmse(pro_frac),
        'angstrom_rmse_mid': rmse(mid_ang),
        'angstrom_rmse_proatomic': rmse(pro_ang),
        'fraction_mae_mid': mae(mid_frac),
        'fraction_mae_proatomic': mae(pro_frac),
        'angstrom_mae_mid': mae(mid_ang),
        'angstrom_mae_proatomic': mae(pro_ang),
        'proatomic_better_fraction': float(np.mean(np.abs(pro_ang) < np.abs(mid_ang))),
    }


def main(argv: Iterable[str] | None = None) -> int:
    args, manifest_csv, lookup_csv, output_dir = parse_args(argv)
    manifest = load_manifest(manifest_csv)
    lookup = load_lookup_csv(lookup_csv)

    edge_rows: list[dict] = []
    molecule_rows: list[dict] = []

    manifest_iter = tqdm(manifest, desc='qtaim systems') if (tqdm is not None and not args.no_progress) else manifest
    for row in manifest_iter:
        obj = json.loads(row.json_path.read_text(encoding='utf-8'))
        positions = np.array([atom['position_angstrom'] for atom in obj['atoms']], dtype=float)
        cp_by_index = {cp['cp_index']: cp for cp in obj['critical_points']}
        local_rows: list[dict] = []
        for edge in obj['bcp_graph']:
            atom_i = int(edge['atom_i']) - 1
            atom_j = int(edge['atom_j']) - 1
            cp = cp_by_index[int(edge['cp_index'])]
            point_i = positions[atom_i]
            point_j = positions[atom_j]
            bcp = np.array(cp['position_angstrom'], dtype=float)
            bond_length = float(np.linalg.norm(point_j - point_i))
            t_obs, offset = projection_fraction_and_offset(point_i, point_j, bcp)
            element_i = obj['atoms'][atom_i]['element']
            element_j = obj['atoms'][atom_j]['element']
            prediction = lookup.predict(element_i, element_j, bond_length)
            x_obs = t_obs * bond_length
            x_mid = 0.5 * bond_length
            local_rows.append(
                {
                    'system_key': row.system_key,
                    'name': row.name,
                    'group': row.group,
                    'atom_i': atom_i + 1,
                    'atom_j': atom_j + 1,
                    'element_i': element_i,
                    'element_j': element_j,
                    'pair_type': '-'.join(sorted((element_i, element_j))),
                    'cp_index': int(edge['cp_index']),
                    'bond_length_angstrom': bond_length,
                    't_obs': t_obs,
                    'x_obs_angstrom': x_obs,
                    'offset_angstrom': offset,
                    'offset_over_length': (offset / bond_length),
                    't_mid': 0.5,
                    'x_mid_angstrom': x_mid,
                    't_proatomic': prediction.fraction_from_i,
                    'x_proatomic_angstrom': prediction.x_from_i_angstrom,
                    'rho_min_proatomic': prediction.rho_min,
                    'abs_err_mid_fraction': abs(0.5 - t_obs),
                    'abs_err_proatomic_fraction': abs(prediction.fraction_from_i - t_obs),
                    'abs_err_mid_angstrom': abs(x_mid - x_obs),
                    'abs_err_proatomic_angstrom': abs(prediction.x_from_i_angstrom - x_obs),
                }
            )
        edge_rows.extend(local_rows)
        mid_frac = np.array([r['t_mid'] - r['t_obs'] for r in local_rows], dtype=float)
        pro_frac = np.array([r['t_proatomic'] - r['t_obs'] for r in local_rows], dtype=float)
        mid_ang = np.array([r['x_mid_angstrom'] - r['x_obs_angstrom'] for r in local_rows], dtype=float)
        pro_ang = np.array([r['x_proatomic_angstrom'] - r['x_obs_angstrom'] for r in local_rows], dtype=float)
        molecule_rows.append(
            {
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'n_edges': len(local_rows),
                'fraction_rmse_mid': rmse(mid_frac),
                'fraction_rmse_proatomic': rmse(pro_frac),
                'fraction_mae_mid': mae(mid_frac),
                'fraction_mae_proatomic': mae(pro_frac),
                'angstrom_rmse_mid': rmse(mid_ang),
                'angstrom_rmse_proatomic': rmse(pro_ang),
                'angstrom_mae_mid': mae(mid_ang),
                'angstrom_mae_proatomic': mae(pro_ang),
                'mean_offset_angstrom': float(np.mean([r['offset_angstrom'] for r in local_rows])),
                'max_offset_angstrom': float(np.max([r['offset_angstrom'] for r in local_rows])),
                'proatomic_beats_mid': 'true' if rmse(pro_ang) < rmse(mid_ang) else 'false',
            }
        )

    pair_rows: list[dict] = []
    edge_rows_by_pair: dict[str, list[dict]] = {}
    for row in edge_rows:
        edge_rows_by_pair.setdefault(row['pair_type'], []).append(row)
    for pair_type in sorted(edge_rows_by_pair):
        subset = edge_rows_by_pair[pair_type]
        mid_frac = np.array([r['t_mid'] - r['t_obs'] for r in subset], dtype=float)
        pro_frac = np.array([r['t_proatomic'] - r['t_obs'] for r in subset], dtype=float)
        mid_ang = np.array([r['x_mid_angstrom'] - r['x_obs_angstrom'] for r in subset], dtype=float)
        pro_ang = np.array([r['x_proatomic_angstrom'] - r['x_obs_angstrom'] for r in subset], dtype=float)
        pair_rows.append(
            {
                'pair_type': pair_type,
                'n_edges': len(subset),
                'fraction_rmse_mid': rmse(mid_frac),
                'fraction_rmse_proatomic': rmse(pro_frac),
                'fraction_mae_mid': mae(mid_frac),
                'fraction_mae_proatomic': mae(pro_frac),
                'angstrom_rmse_mid': rmse(mid_ang),
                'angstrom_rmse_proatomic': rmse(pro_ang),
                'angstrom_mae_mid': mae(mid_ang),
                'angstrom_mae_proatomic': mae(pro_ang),
                'mean_offset_angstrom': float(np.mean([r['offset_angstrom'] for r in subset])),
                'max_offset_angstrom': float(np.max([r['offset_angstrom'] for r in subset])),
                'proatomic_better_fraction': float(np.mean([r['abs_err_proatomic_angstrom'] < r['abs_err_mid_angstrom'] for r in subset])),
            }
        )

    threshold_rows = [
        _threshold_metrics(edge_rows, 'all', lambda row: True),
        _threshold_metrics(edge_rows, 'offset<=0.02A', lambda row: row['offset_angstrom'] <= 0.02),
        _threshold_metrics(edge_rows, 'offset<=0.05A', lambda row: row['offset_angstrom'] <= 0.05),
        _threshold_metrics(edge_rows, 'offset<=0.10A', lambda row: row['offset_angstrom'] <= 0.10),
        _threshold_metrics(edge_rows, 'offset_over_length<=0.05', lambda row: row['offset_over_length'] <= 0.05),
        _threshold_metrics(edge_rows, 'offset_over_length<=0.10', lambda row: row['offset_over_length'] <= 0.10),
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    edge_path = output_dir / 'edge_level.csv'
    molecule_path = output_dir / 'molecule_level.csv'
    pair_path = output_dir / 'pair_type_summary.csv'
    threshold_path = output_dir / 'threshold_summary.csv'
    summary_json = output_dir / 'summary.json'
    report_md = output_dir / 'REPORT.md'

    _write_csv(edge_path, list(edge_rows[0].keys()), edge_rows)
    _write_csv(molecule_path, list(molecule_rows[0].keys()), molecule_rows)
    _write_csv(pair_path, list(pair_rows[0].keys()), pair_rows)
    _write_csv(threshold_path, list(threshold_rows[0].keys()), threshold_rows)

    overall = threshold_rows[0]
    summary_payload = {
        'dataset_manifest': str(manifest_csv),
        'lookup_csv': str(lookup_csv),
        'n_systems': int(len(molecule_rows)),
        'n_edges': int(len(edge_rows)),
        'overall': overall,
        'thresholds': threshold_rows,
        'median_molecule_improvement_factor_angstrom_rmse': float(
            np.median(
                [
                    row['angstrom_rmse_mid'] / row['angstrom_rmse_proatomic']
                    for row in molecule_rows
                    if row['angstrom_rmse_proatomic'] > 0.0
                ]
            )
        ),
        'median_offset_angstrom': float(np.median([row['offset_angstrom'] for row in edge_rows])),
        'p95_offset_angstrom': float(np.percentile([row['offset_angstrom'] for row in edge_rows], 95.0)),
        'max_offset_angstrom': float(np.max([row['offset_angstrom'] for row in edge_rows])),
    }
    write_metadata_json(summary_payload, summary_json)

    with report_md.open('w', encoding='utf-8') as handle:
        handle.write('# Proatomic pair-law analysis\n\n')
        handle.write(f'- Manifest: `{manifest_csv}`\n')
        handle.write(f'- Lookup: `{lookup_csv}`\n')
        handle.write(f'- Systems analyzed: **{len(molecule_rows)}**\n')
        handle.write(f'- QTAIM BCP-supported edges: **{len(edge_rows)}**\n\n')
        handle.write('## Overall\n\n')
        handle.write(f'- Midpoint fraction RMSE: **{overall["fraction_rmse_mid"]:.6f}**\n')
        handle.write(f'- Proatomic fraction RMSE: **{overall["fraction_rmse_proatomic"]:.6f}**\n')
        handle.write(f'- Midpoint separator RMSE (Å): **{overall["angstrom_rmse_mid"]:.6f}**\n')
        handle.write(f'- Proatomic separator RMSE (Å): **{overall["angstrom_rmse_proatomic"]:.6f}**\n')
        handle.write(f'- Fraction of edges where proatomic beats midpoint (Å error): **{overall["proatomic_better_fraction"]:.3f}**\n\n')
        handle.write('## Off-axis diagnostic\n\n')
        handle.write(f'- Median BCP-to-axis offset: **{summary_payload["median_offset_angstrom"]:.6f} Å**\n')
        handle.write(f'- 95th percentile offset: **{summary_payload["p95_offset_angstrom"]:.6f} Å**\n')
        handle.write(f'- Maximum offset: **{summary_payload["max_offset_angstrom"]:.6f} Å**\n\n')
        handle.write('## Outputs\n\n')
        handle.write('- `edge_level.csv`\n')
        handle.write('- `molecule_level.csv`\n')
        handle.write('- `pair_type_summary.csv`\n')
        handle.write('- `threshold_summary.csv`\n')
        handle.write('- `summary.json`\n')

    print(f'[pairlaw] wrote analysis to {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
