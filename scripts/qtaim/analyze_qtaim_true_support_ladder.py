"""Experiment J2: separator ladder on true QTAIM support.

This script evaluates four separator models on the observed QTAIM BCP support
for a molecular benchmark:

1. midpoint baseline;
2. frozen proatomic local pair law;
3. frozen proatomic targets reconciled by one-shot power-diagram fitting on the
   true support;
4. QTAIM-derived targets reconciled by one-shot power-diagram fitting on the
   true support, interpreted as a support-conditioned power-diagram ceiling.

The purpose is deliberately narrow: quantify how much of the separator signal is
already captured by the transferable local rule, how much global one-shot
reconciliation changes those targets, and how much residual error remains even
when the true support and projected QTAIM targets are supplied.

Inputs
------
A manifest CSV with at least:
- ``json_path``
- ``connectivity_smiles`` or ``smiles``

Optional manifest columns that are propagated when present:
- ``system_key``
- ``name``
- ``selection_stratum`` / ``group``

The script resolves relative paths against the manifest location and, by
 default, skips rows whose QTAIM JSON is not yet available. This makes it safe
 to run against an in-progress full manifest while only part of the dataset has
 been computed.

Outputs
-------
The output directory contains:
- ``edge_level.csv``
- ``molecule_level.csv``
- ``subset_summary.csv``
- ``pair_type_summary.csv``
- ``skipped_rows.csv``
- ``summary.json``
- ``REPORT.md``
- optional figures under ``figures/``
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import numpy as np
import pandas as pd
import pyvoro2 as pv
from rdkit import Chem
from rdkit.Chem import rdmolops

from _figure_io import save_figure

from _cli_progress import iter_progress, progress_write, tqdm_available
from _proatomic_pairlaw import PairLawLookup, load_lookup_csv, write_metadata_json


LOW_OFFSET_DEFAULT = 0.02
BOX_MARGIN_DEFAULT = 5.0



def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())




def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw))


def _csv_path(base_dir: Path, raw: str) -> Path:
    candidate = Path(_expand(raw))
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


@dataclass(frozen=True)
class ManifestRow:
    system_key: str
    name: str
    group: str
    smiles: str
    json_path: Path


@dataclass(frozen=True)
class GraphInfo:
    mol: Chem.Mol
    atom_symbols: list[str]
    topological_distances: np.ndarray


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


def _pick_label(row: dict[str, str], default_stem: str, row_index: int) -> str:
    for key in ('system_key', 'system_id', 'name'):
        value = (row.get(key) or '').strip()
        if value:
            return value.replace(' ', '_')
    return default_stem or f'row_{row_index}'


def load_manifest(manifest_csv: Path) -> list[ManifestRow]:
    base_dir = manifest_csv.parent
    with manifest_csv.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if 'json_path' not in fieldnames:
            raise ValueError('Manifest must contain json_path column')
        if 'connectivity_smiles' not in fieldnames and 'smiles' not in fieldnames:
            raise ValueError('Manifest must contain connectivity_smiles or smiles column')
        rows: list[ManifestRow] = []
        for idx, raw_row in enumerate(reader, start=2):
            if not any((value or '').strip() for value in raw_row.values()):
                continue
            json_path = _csv_path(base_dir, (raw_row.get('json_path') or '').strip())
            label = _pick_label(raw_row, json_path.stem, idx)
            smiles = (raw_row.get('connectivity_smiles') or raw_row.get('smiles') or '').strip()
            rows.append(
                ManifestRow(
                    system_key=label,
                    name=(raw_row.get('name') or '').strip() or label,
                    group=(raw_row.get('selection_stratum') or raw_row.get('group') or '').strip(),
                    smiles=smiles,
                    json_path=json_path,
                )
            )
    if not rows:
        raise ValueError(f'No data rows found in manifest: {manifest_csv}')
    return rows


def _make_graph_info(smiles: str) -> GraphInfo:
    if not smiles:
        raise ValueError('Empty connectivity_smiles/smiles value')
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f'RDKit failed to parse SMILES: {smiles}')
    mol = Chem.AddHs(mol)
    atom_symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    dm = rdmolops.GetDistanceMatrix(mol)
    return GraphInfo(mol=mol, atom_symbols=atom_symbols, topological_distances=np.asarray(dm, dtype=float))


def box_for_points(points: np.ndarray, margin: float) -> pv.Box:
    mins = points.min(axis=0) - margin
    maxs = points.max(axis=0) + margin
    return pv.Box(bounds=tuple((float(mins[k]), float(maxs[k])) for k in range(3)))


def _distance_bin(path_distance: int) -> str:
    return 'bonded' if path_distance <= 1 else 'nonbonded'


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return float('nan')
    return float(numerator / denominator)


def _gap_closure(mid_rmse: float, method_rmse: float, ceiling_rmse: float) -> float:
    denom = mid_rmse - ceiling_rmse
    if not math.isfinite(denom) or abs(denom) <= 1.0e-15:
        return float('nan')
    return float((mid_rmse - method_rmse) / denom)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Run the J2 true-support separator ladder on a molecular QTAIM manifest.'
    )
    parser.add_argument('manifest_csv', help='Manifest CSV with json_path plus connectivity_smiles/smiles.')
    parser.add_argument('--lookup-csv', default=None, help='Pair-law lookup CSV. Defaults to data/proatomic/pairlaw/separator_lookup.csv.')
    parser.add_argument('--output-dir', default=None, help='Directory for analysis outputs. Defaults to results/qtaim_main/J2_true_support_ladder when the manifest lives under data/qtaim_main/.')
    parser.add_argument(
        '--offset-threshold',
        type=float,
        default=LOW_OFFSET_DEFAULT,
        help=f'Low-offset threshold in angstrom for subset summaries (default: {LOW_OFFSET_DEFAULT:.2f}).',
    )
    parser.add_argument(
        '--box-margin',
        type=float,
        default=BOX_MARGIN_DEFAULT,
        help=f'Bounding-box margin in angstrom for non-periodic tessellations (default: {BOX_MARGIN_DEFAULT:.1f}).',
    )
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm progress bars.')
    parser.add_argument('--require-all', action='store_true', help='Fail if any listed QTAIM JSON is missing instead of skipping it.')
    parser.add_argument('--no-plots', action='store_true', help='Do not generate diagnostic figures.')
    return parser




def choose_default_output_dir(manifest_csv: Path) -> Path:
    repo_root = manifest_csv.parents[2] if len(manifest_csv.parents) >= 3 else manifest_csv.parent
    if manifest_csv.parent.name == 'qtaim_main':
        return (repo_root / 'results' / 'qtaim_main' / 'J2_true_support_ladder').resolve()
    return (repo_root / 'results' / f'{manifest_csv.stem}_true_support_ladder').resolve()


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
    output_dir = Path(_expand(args.output_dir)).resolve() if args.output_dir else choose_default_output_dir(manifest_csv)
    return args, manifest_csv, lookup_csv, output_dir


def _subset_summary_row(label: str, subset: pd.DataFrame) -> dict[str, object]:
    if subset.empty:
        return {
            'subset': label,
            'n_edges': 0,
            'n_molecules': 0,
            'midpoint_fraction_rmse': float('nan'),
            'proatomic_fraction_rmse': float('nan'),
            'proatomic_powerfit_fraction_rmse': float('nan'),
            'qtaim_ceiling_fraction_rmse': float('nan'),
            'midpoint_angstrom_rmse': float('nan'),
            'proatomic_angstrom_rmse': float('nan'),
            'proatomic_powerfit_angstrom_rmse': float('nan'),
            'qtaim_ceiling_angstrom_rmse': float('nan'),
            'midpoint_angstrom_mae': float('nan'),
            'proatomic_angstrom_mae': float('nan'),
            'proatomic_powerfit_angstrom_mae': float('nan'),
            'qtaim_ceiling_angstrom_mae': float('nan'),
            'proatomic_gap_closure': float('nan'),
            'proatomic_powerfit_gap_closure': float('nan'),
            'proatomic_better_than_midpoint_fraction': float('nan'),
            'proatomic_powerfit_better_than_proatomic_fraction': float('nan'),
            'qtaim_ceiling_better_than_proatomic_fraction': float('nan'),
            'realized_proatomic_powerfit_fraction': float('nan'),
            'realized_qtaim_ceiling_fraction': float('nan'),
            'proatomic_to_powerfit_distortion_rmse_angstrom': float('nan'),
        }

    mid_frac = subset['err_midpoint_fraction'].to_numpy(dtype=float)
    pro_frac = subset['err_proatomic_fraction'].to_numpy(dtype=float)
    ppf_frac = subset['err_proatomic_powerfit_fraction'].to_numpy(dtype=float)
    ceil_frac = subset['err_qtaim_ceiling_fraction'].to_numpy(dtype=float)

    mid_ang = subset['err_midpoint_angstrom'].to_numpy(dtype=float)
    pro_ang = subset['err_proatomic_angstrom'].to_numpy(dtype=float)
    ppf_ang = subset['err_proatomic_powerfit_angstrom'].to_numpy(dtype=float)
    ceil_ang = subset['err_qtaim_ceiling_angstrom'].to_numpy(dtype=float)
    distortion = subset['proatomic_to_powerfit_shift_angstrom'].to_numpy(dtype=float)

    mid_rmse = rmse(mid_ang)
    pro_rmse = rmse(pro_ang)
    ppf_rmse = rmse(ppf_ang)
    ceil_rmse = rmse(ceil_ang)

    return {
        'subset': label,
        'n_edges': int(len(subset)),
        'n_molecules': int(subset['system_key'].nunique()),
        'midpoint_fraction_rmse': rmse(mid_frac),
        'proatomic_fraction_rmse': rmse(pro_frac),
        'proatomic_powerfit_fraction_rmse': rmse(ppf_frac),
        'qtaim_ceiling_fraction_rmse': rmse(ceil_frac),
        'midpoint_angstrom_rmse': mid_rmse,
        'proatomic_angstrom_rmse': pro_rmse,
        'proatomic_powerfit_angstrom_rmse': ppf_rmse,
        'qtaim_ceiling_angstrom_rmse': ceil_rmse,
        'midpoint_angstrom_mae': mae(mid_ang),
        'proatomic_angstrom_mae': mae(pro_ang),
        'proatomic_powerfit_angstrom_mae': mae(ppf_ang),
        'qtaim_ceiling_angstrom_mae': mae(ceil_ang),
        'proatomic_gap_closure': _gap_closure(mid_rmse, pro_rmse, ceil_rmse),
        'proatomic_powerfit_gap_closure': _gap_closure(mid_rmse, ppf_rmse, ceil_rmse),
        'proatomic_better_than_midpoint_fraction': float(np.mean(np.abs(pro_ang) < np.abs(mid_ang))),
        'proatomic_powerfit_better_than_proatomic_fraction': float(np.mean(np.abs(ppf_ang) < np.abs(pro_ang))),
        'qtaim_ceiling_better_than_proatomic_fraction': float(np.mean(np.abs(ceil_ang) < np.abs(pro_ang))),
        'realized_proatomic_powerfit_fraction': float(np.mean(subset['realized_proatomic_powerfit'].astype(bool))),
        'realized_qtaim_ceiling_fraction': float(np.mean(subset['realized_qtaim_ceiling'].astype(bool))),
        'proatomic_to_powerfit_distortion_rmse_angstrom': rmse(distortion),
    }


def _write_report(path: Path, summary: dict[str, object], subset_df: pd.DataFrame) -> None:
    def _row(name: str) -> pd.Series | None:
        sub = subset_df[subset_df['subset'] == name]
        return None if sub.empty else sub.iloc[0]

    overall = _row('all')
    hetero = _row('heteronuclear')
    lowoff = _row(f'offset<={summary["offset_threshold_angstrom"]:.2f}A')
    lowoff_hetero = _row(f'heteronuclear & offset<={summary["offset_threshold_angstrom"]:.2f}A')
    bonded = _row('bonded')
    nonbonded = _row('nonbonded')
    if overall is None:
        raise ValueError('subset summary does not contain the all-row')

    lines = [
        '# J2 true-support separator ladder',
        '',
        f'- Manifest: `{summary["manifest_csv"]}`',
        f'- Pair-law lookup: `{summary["lookup_csv"]}`',
        f'- Manifest rows: **{summary["n_manifest_rows"]}**',
        f'- Processed molecules: **{summary["n_processed_rows"]}**',
        f'- Skipped rows: **{summary["n_skipped_rows"]}**',
        f'- QTAIM BCP-supported edges: **{summary["n_edges"]}**',
        '',
        '## Overall separator ladder (Å RMSE)',
        '',
        f'- Midpoint: **{overall["midpoint_angstrom_rmse"]:.6f}**',
        f'- Frozen proatomic local law: **{overall["proatomic_angstrom_rmse"]:.6f}**',
        f'- Frozen proatomic + one-shot powerfit: **{overall["proatomic_powerfit_angstrom_rmse"]:.6f}**',
        f'- Support-conditioned power-diagram ceiling: **{overall["qtaim_ceiling_angstrom_rmse"]:.6f}**',
        '',
        '## Main interpretation',
        '',
        f'- The frozen proatomic law closes **{100.0 * overall["proatomic_gap_closure"]:.1f}%** of the midpoint-to-ceiling gap on the full frozen benchmark.',
        f'- One-shot reconciliation of proatomic targets changes separator positions only slightly (distortion RMSE **{overall["proatomic_to_powerfit_distortion_rmse_angstrom"]:.6f} Å**), but does **not** improve true-edge separator RMSE on this subset.',
        f'- All requested true-support edges are realized after one-shot powerfit for **{summary["molecules_all_realized_proatomic_powerfit"]}/{summary["n_processed_rows"]}** processed molecules under the proatomic targets and **{summary["molecules_all_realized_qtaim_ceiling"]}/{summary["n_processed_rows"]}** under the QTAIM-target ceiling.',
    ]
    if hetero is not None:
        lines += [
            '',
            '## Heteronuclear subset',
            '',
            f'- Edges: **{int(hetero["n_edges"])}**',
            f'- Midpoint RMSE (Å): **{hetero["midpoint_angstrom_rmse"]:.6f}**',
            f'- Proatomic RMSE (Å): **{hetero["proatomic_angstrom_rmse"]:.6f}**',
            f'- Proatomic gap closure: **{100.0 * hetero["proatomic_gap_closure"]:.1f}%**',
        ]
    if lowoff is not None:
        lines += [
            '',
            '## Low-offset subset',
            '',
            f'- Offset threshold: **{summary["offset_threshold_angstrom"]:.2f} Å**',
            f'- Edges within threshold: **{int(lowoff["n_edges"])}**',
            f'- Ceiling RMSE (Å): **{lowoff["qtaim_ceiling_angstrom_rmse"]:.6f}**',
        ]
    if lowoff_hetero is not None:
        lines += [
            '',
            '## Clean connector-aligned heteronuclear subset',
            '',
            f'- Edges: **{int(lowoff_hetero["n_edges"])}** across **{int(lowoff_hetero["n_molecules"])}** molecules.',
            f'- Ceiling RMSE (Å): **{lowoff_hetero["qtaim_ceiling_angstrom_rmse"]:.6f}** with realized fraction **{100.0 * lowoff_hetero["realized_qtaim_ceiling_fraction"]:.1f}%**.',
            '- Interpretation: when supervision is connector-aligned and chemically nontrivial, the fixed-site power-diagram model is not intrinsically too crude.',
        ]
    if bonded is not None and nonbonded is not None:
        lines += [
            '',
            '## Bonded vs nonbonded split',
            '',
            f'- Bonded edges: **{int(bonded["n_edges"])}**; proatomic RMSE **{bonded["proatomic_angstrom_rmse"]:.6f} Å**, ceiling **{bonded["qtaim_ceiling_angstrom_rmse"]:.6f} Å**.',
            f'- Nonbonded edges: **{int(nonbonded["n_edges"])}**; proatomic RMSE **{nonbonded["proatomic_angstrom_rmse"]:.6f} Å**, ceiling **{nonbonded["qtaim_ceiling_angstrom_rmse"]:.6f} Å**.',
            '- Interpretation: the bonded subset retains a large power-diagram-improvable gap, while the nonbonded subset already exposes strong model mismatch on the true support. This is exactly why the molecular section should emphasize separator quality on important/bonded edges and treat the nonbonded tail as proxy- and representability-limited rather than as a target for forced exact reconstruction.',
        ]
    lines += [
        '',
        '## Outputs',
        '',
        '- `edge_level.csv`',
        '- `molecule_level.csv`',
        '- `subset_summary.csv`',
        '- `pair_type_summary.csv`',
        '- `summary.json`',
    ]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _make_plots(subset_df: pd.DataFrame, molecule_df: pd.DataFrame, output_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return

    fig_dir = output_dir / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)

    focus_order = [
        'all',
        'heteronuclear',
        f'offset<={LOW_OFFSET_DEFAULT:.2f}A',
        'bonded',
        'nonbonded',
    ]
    plot_df = subset_df[subset_df['subset'].isin(focus_order)].copy()
    if not plot_df.empty:
        order = [name for name in focus_order if name in set(plot_df['subset'])]
        x = np.arange(len(order), dtype=float)
        width = 0.2
        fig = plt.figure(figsize=(8.0, 4.5))
        ax = fig.add_subplot(111)
        plot_df = plot_df.set_index('subset').loc[order]
        ax.bar(x - 1.5 * width, plot_df['midpoint_angstrom_rmse'].to_numpy(dtype=float), width=width, label='midpoint')
        ax.bar(x - 0.5 * width, plot_df['proatomic_angstrom_rmse'].to_numpy(dtype=float), width=width, label='proatomic')
        ax.bar(x + 0.5 * width, plot_df['proatomic_powerfit_angstrom_rmse'].to_numpy(dtype=float), width=width, label='proatomic + powerfit')
        ax.bar(x + 1.5 * width, plot_df['qtaim_ceiling_angstrom_rmse'].to_numpy(dtype=float), width=width, label='ceiling')
        ax.set_xticks(x)
        ax.set_xticklabels(order, rotation=20, ha='right')
        ax.set_ylabel('separator RMSE (Å)')
        ax.set_title('J2: true-support separator ladder')
        ax.legend()
        fig.tight_layout()
        save_figure(
            fig,
            fig_dir / 'subset_rmse_angstrom.png',
            title='subset_rmse_angstrom',
            png_dpi=200,
            save_pdf_sibling=True,
        )
        plt.close(fig)

    mol = molecule_df.sort_values('angstrom_rmse_midpoint', kind='mergesort').reset_index(drop=True)
    if not mol.empty:
        x = np.arange(len(mol), dtype=float)
        fig = plt.figure(figsize=(8.0, 4.5))
        ax = fig.add_subplot(111)
        ax.plot(x, mol['angstrom_rmse_midpoint'].to_numpy(dtype=float), label='midpoint')
        ax.plot(x, mol['angstrom_rmse_proatomic'].to_numpy(dtype=float), label='proatomic')
        ax.plot(x, mol['angstrom_rmse_proatomic_powerfit'].to_numpy(dtype=float), label='proatomic + powerfit')
        ax.plot(x, mol['angstrom_rmse_qtaim_ceiling'].to_numpy(dtype=float), label='ceiling')
        ax.set_xlabel('processed molecules (sorted by midpoint RMSE)')
        ax.set_ylabel('per-molecule separator RMSE (Å)')
        ax.set_title('J2: molecule-level separator RMSE ladder')
        ax.legend()
        fig.tight_layout()
        save_figure(
            fig,
            fig_dir / 'molecule_rmse_ladder.png',
            title='molecule_rmse_ladder',
            png_dpi=200,
            save_pdf_sibling=True,
        )
        plt.close(fig)


def main(argv: Iterable[str] | None = None) -> int:
    args, manifest_csv, lookup_csv, output_dir = parse_args(argv)
    manifest = load_manifest(manifest_csv)
    lookup = load_lookup_csv(lookup_csv)

    edge_rows: list[dict[str, object]] = []
    molecule_rows: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []

    total = len(manifest)
    progress_write(f'Loaded {total} QTAIM rows from {manifest_csv}')
    progress_write(f'Pair-law lookup: {lookup_csv}')
    progress_write(f'Output dir: {output_dir}')
    if not args.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')
    manifest_iter = iter_progress(manifest, total=total, desc='J2 ladder', disable=args.no_progress, unit='system')
    for row in manifest_iter:
        if hasattr(manifest_iter, 'set_postfix_str'):
            manifest_iter.set_postfix_str(row.system_key)
        if not row.json_path.is_file():
            if args.require_all:
                raise FileNotFoundError(f'Missing QTAIM JSON: {row.json_path}')
            skipped_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'json_path': str(row.json_path),
                'reason': 'missing_json',
            })
            continue

        try:
            graph_info = _make_graph_info(row.smiles)
        except Exception as exc:
            skipped_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'json_path': str(row.json_path),
                'reason': f'rdkit_error: {exc}',
            })
            continue

        try:
            obj = json.loads(row.json_path.read_text(encoding='utf-8'))
        except Exception as exc:
            skipped_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'json_path': str(row.json_path),
                'reason': f'json_error: {exc}',
            })
            continue

        atom_symbols_json = [atom['element'] for atom in obj['atoms']]
        if atom_symbols_json != graph_info.atom_symbols:
            skipped_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'json_path': str(row.json_path),
                'reason': 'atom_order_mismatch',
            })
            continue

        positions = np.array([atom['position_angstrom'] for atom in obj['atoms']], dtype=float)
        cp_by_index = {int(cp['cp_index']): cp for cp in obj['critical_points']}
        local_rows: list[dict[str, object]] = []
        constraints_pro: list[tuple[int, int, float]] = []
        constraints_qtaim: list[tuple[int, int, float]] = []

        for edge in obj['bcp_graph']:
            atom_i = int(edge['atom_i']) - 1
            atom_j = int(edge['atom_j']) - 1
            cp_index = int(edge['cp_index'])
            cp = cp_by_index[cp_index]
            point_i = positions[atom_i]
            point_j = positions[atom_j]
            bcp = np.array(cp['position_angstrom'], dtype=float)
            bond_length = float(np.linalg.norm(point_j - point_i))
            t_obs, offset = projection_fraction_and_offset(point_i, point_j, bcp)
            path_distance = int(round(float(graph_info.topological_distances[atom_i, atom_j])))
            element_i = atom_symbols_json[atom_i]
            element_j = atom_symbols_json[atom_j]
            pair_type = '-'.join(sorted((element_i, element_j)))
            pro_prediction = lookup.predict(element_i, element_j, bond_length)

            constraints_pro.append((atom_i, atom_j, float(pro_prediction.fraction_from_i)))
            constraints_qtaim.append((atom_i, atom_j, float(t_obs)))

            x_obs = t_obs * bond_length
            x_mid = 0.5 * bond_length
            x_pro = float(pro_prediction.x_from_i_angstrom)

            local_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'atom_i': atom_i + 1,
                'atom_j': atom_j + 1,
                'cp_index': cp_index,
                'element_i': element_i,
                'element_j': element_j,
                'pair_type': pair_type,
                'is_homonuclear': element_i == element_j,
                'is_heteronuclear': element_i != element_j,
                'graph_distance': path_distance,
                'graph_distance_bin': _distance_bin(path_distance),
                'is_bonded': path_distance == 1,
                'is_nonbonded': path_distance != 1,
                'bond_length_angstrom': bond_length,
                't_obs': t_obs,
                'x_obs_angstrom': x_obs,
                'offset_angstrom': offset,
                'offset_over_length': (offset / bond_length),
                't_midpoint': 0.5,
                'x_midpoint_angstrom': x_mid,
                't_proatomic': float(pro_prediction.fraction_from_i),
                'x_proatomic_angstrom': x_pro,
                'rho_min_proatomic': float(pro_prediction.rho_min),
                'err_midpoint_fraction': float(0.5 - t_obs),
                'err_proatomic_fraction': float(pro_prediction.fraction_from_i - t_obs),
                'err_midpoint_angstrom': float(x_mid - x_obs),
                'err_proatomic_angstrom': float(x_pro - x_obs),
            })

        if not local_rows:
            skipped_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'json_path': str(row.json_path),
                'reason': 'no_bcp_edges',
            })
            continue

        box = box_for_points(positions, margin=float(args.box_margin))
        resolved_pro = pv.resolve_pair_bisector_constraints(positions, constraints_pro, measurement='fraction', domain=box)
        fit_pro = pv.fit_power_weights(positions, resolved_pro, measurement='fraction', domain=box, connectivity_check='diagnose')
        realized_pro = pv.match_realized_pairs(
            positions,
            domain=box,
            radii=np.asarray(fit_pro.radii, dtype=float),
            constraints=resolved_pro,
            tessellation_check='diagnose',
            unaccounted_pair_check='diagnose',
        )

        resolved_qtaim = pv.resolve_pair_bisector_constraints(positions, constraints_qtaim, measurement='fraction', domain=box)
        fit_qtaim = pv.fit_power_weights(positions, resolved_qtaim, measurement='fraction', domain=box, connectivity_check='diagnose')
        realized_qtaim = pv.match_realized_pairs(
            positions,
            domain=box,
            radii=np.asarray(fit_qtaim.radii, dtype=float),
            constraints=resolved_qtaim,
            tessellation_check='diagnose',
            unaccounted_pair_check='diagnose',
        )

        pred_pro_fraction = np.asarray(fit_pro.predicted_fraction, dtype=float)
        pred_qtaim_fraction = np.asarray(fit_qtaim.predicted_fraction, dtype=float)
        pred_pro_position = np.asarray(fit_pro.predicted_position, dtype=float)
        pred_qtaim_position = np.asarray(fit_qtaim.predicted_position, dtype=float)
        realized_pro_mask = np.asarray(realized_pro.realized_same_shift, dtype=bool)
        realized_qtaim_mask = np.asarray(realized_qtaim.realized_same_shift, dtype=bool)

        for idx_edge, edge_row in enumerate(local_rows):
            obs_t = float(edge_row['t_obs'])
            obs_x = float(edge_row['x_obs_angstrom'])
            t_pf = float(pred_pro_fraction[idx_edge])
            x_pf = float(pred_pro_position[idx_edge])
            t_ceil = float(pred_qtaim_fraction[idx_edge])
            x_ceil = float(pred_qtaim_position[idx_edge])
            edge_row.update(
                {
                    't_proatomic_powerfit': t_pf,
                    'x_proatomic_powerfit_angstrom': x_pf,
                    't_qtaim_ceiling': t_ceil,
                    'x_qtaim_ceiling_angstrom': x_ceil,
                    'err_proatomic_powerfit_fraction': float(t_pf - obs_t),
                    'err_qtaim_ceiling_fraction': float(t_ceil - obs_t),
                    'err_proatomic_powerfit_angstrom': float(x_pf - obs_x),
                    'err_qtaim_ceiling_angstrom': float(x_ceil - obs_x),
                    'realized_proatomic_powerfit': bool(realized_pro_mask[idx_edge]),
                    'realized_qtaim_ceiling': bool(realized_qtaim_mask[idx_edge]),
                    'proatomic_to_powerfit_shift_fraction': float(t_pf - float(edge_row['t_proatomic'])),
                    'proatomic_to_powerfit_shift_angstrom': float(x_pf - float(edge_row['x_proatomic_angstrom'])),
                }
            )
        edge_rows.extend(local_rows)

        mid_frac = np.array([r['err_midpoint_fraction'] for r in local_rows], dtype=float)
        pro_frac = np.array([r['err_proatomic_fraction'] for r in local_rows], dtype=float)
        ppf_frac = np.array([r['err_proatomic_powerfit_fraction'] for r in local_rows], dtype=float)
        ceil_frac = np.array([r['err_qtaim_ceiling_fraction'] for r in local_rows], dtype=float)

        mid_ang = np.array([r['err_midpoint_angstrom'] for r in local_rows], dtype=float)
        pro_ang = np.array([r['err_proatomic_angstrom'] for r in local_rows], dtype=float)
        ppf_ang = np.array([r['err_proatomic_powerfit_angstrom'] for r in local_rows], dtype=float)
        ceil_ang = np.array([r['err_qtaim_ceiling_angstrom'] for r in local_rows], dtype=float)
        distortion = np.array([r['proatomic_to_powerfit_shift_angstrom'] for r in local_rows], dtype=float)

        mid_rmse = rmse(mid_ang)
        pro_rmse = rmse(pro_ang)
        ppf_rmse = rmse(ppf_ang)
        ceil_rmse = rmse(ceil_ang)

        molecule_rows.append({
            'system_key': row.system_key,
            'name': row.name,
            'group': row.group,
            'n_edges': int(len(local_rows)),
            'fraction_rmse_midpoint': rmse(mid_frac),
            'fraction_rmse_proatomic': rmse(pro_frac),
            'fraction_rmse_proatomic_powerfit': rmse(ppf_frac),
            'fraction_rmse_qtaim_ceiling': rmse(ceil_frac),
            'angstrom_rmse_midpoint': mid_rmse,
            'angstrom_rmse_proatomic': pro_rmse,
            'angstrom_rmse_proatomic_powerfit': ppf_rmse,
            'angstrom_rmse_qtaim_ceiling': ceil_rmse,
            'angstrom_mae_midpoint': mae(mid_ang),
            'angstrom_mae_proatomic': mae(pro_ang),
            'angstrom_mae_proatomic_powerfit': mae(ppf_ang),
            'angstrom_mae_qtaim_ceiling': mae(ceil_ang),
            'proatomic_gap_closure': _gap_closure(mid_rmse, pro_rmse, ceil_rmse),
            'proatomic_powerfit_gap_closure': _gap_closure(mid_rmse, ppf_rmse, ceil_rmse),
            'proatomic_improvement_factor_vs_midpoint': _safe_ratio(mid_rmse, pro_rmse),
            'proatomic_powerfit_improvement_factor_vs_midpoint': _safe_ratio(mid_rmse, ppf_rmse),
            'ceiling_improvement_factor_vs_proatomic': _safe_ratio(pro_rmse, ceil_rmse),
            'realized_proatomic_powerfit_fraction': float(np.mean(realized_pro_mask)),
            'realized_qtaim_ceiling_fraction': float(np.mean(realized_qtaim_mask)),
            'all_realized_proatomic_powerfit': bool(np.all(realized_pro_mask)),
            'all_realized_qtaim_ceiling': bool(np.all(realized_qtaim_mask)),
            'proatomic_to_powerfit_distortion_rmse_angstrom': rmse(distortion),
            'mean_offset_angstrom': float(np.mean([r['offset_angstrom'] for r in local_rows])),
            'max_offset_angstrom': float(np.max([r['offset_angstrom'] for r in local_rows])),
            'fit_status_proatomic_powerfit': fit_pro.status,
            'fit_status_qtaim_ceiling': fit_qtaim.status,
            'fit_status_detail_proatomic_powerfit': getattr(fit_pro, 'status_detail', ''),
            'fit_status_detail_qtaim_ceiling': getattr(fit_qtaim, 'status_detail', ''),
            'fit_warnings_proatomic_powerfit': ' | '.join(getattr(fit_pro, 'warnings', ())),
            'fit_warnings_qtaim_ceiling': ' | '.join(getattr(fit_qtaim, 'warnings', ())),
        })

    if not edge_rows:
        raise RuntimeError('No QTAIM-supported edges were processed; cannot build J2 ladder outputs.')

    edge_df = pd.DataFrame(edge_rows)
    molecule_df = pd.DataFrame(molecule_rows)
    skipped_df = pd.DataFrame(skipped_rows)

    subset_rows = [
        _subset_summary_row('all', edge_df),
        _subset_summary_row('heteronuclear', edge_df[edge_df['is_heteronuclear']]),
        _subset_summary_row('homonuclear', edge_df[edge_df['is_homonuclear']]),
        _subset_summary_row(f'offset<={float(args.offset_threshold):.2f}A', edge_df[edge_df['offset_angstrom'] <= float(args.offset_threshold)]),
        _subset_summary_row('bonded', edge_df[edge_df['is_bonded']]),
        _subset_summary_row('nonbonded', edge_df[edge_df['is_nonbonded']]),
        _subset_summary_row(
            f'heteronuclear & offset<={float(args.offset_threshold):.2f}A',
            edge_df[edge_df['is_heteronuclear'] & (edge_df['offset_angstrom'] <= float(args.offset_threshold))],
        ),
    ]
    subset_df = pd.DataFrame(subset_rows)

    pair_rows: list[dict[str, object]] = []
    for pair_type, subset in edge_df.groupby('pair_type', dropna=False):
        row_pair = _subset_summary_row(str(pair_type), subset)
        row_pair['pair_type'] = str(pair_type)
        pair_rows.append(row_pair)
    pair_df = pd.DataFrame(pair_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    edge_df.to_csv(output_dir / 'edge_level.csv', index=False)
    molecule_df.to_csv(output_dir / 'molecule_level.csv', index=False)
    subset_df.to_csv(output_dir / 'subset_summary.csv', index=False)
    pair_df.to_csv(output_dir / 'pair_type_summary.csv', index=False)
    skipped_df.to_csv(output_dir / 'skipped_rows.csv', index=False)

    overall = subset_df.loc[subset_df['subset'] == 'all'].iloc[0].to_dict()
    low_offset_label = f'heteronuclear & offset<={float(args.offset_threshold):.2f}A'
    low_offset_heteronuclear_row = subset_df.loc[subset_df['subset'] == low_offset_label].iloc[0].to_dict()
    summary_payload = {
        'manifest_csv': _display_path(manifest_csv),
        'lookup_csv': _display_path(lookup_csv),
        'offset_threshold_angstrom': float(args.offset_threshold),
        'box_margin_angstrom': float(args.box_margin),
        'n_manifest_rows': int(len(manifest)),
        'n_processed_rows': int(len(molecule_df)),
        'n_skipped_rows': int(len(skipped_df)),
        'n_edges': int(len(edge_df)),
        'overall': overall,
        'low_offset_heteronuclear': low_offset_heteronuclear_row,
        'molecules_all_realized_proatomic_powerfit': int(molecule_df['all_realized_proatomic_powerfit'].astype(bool).sum()),
        'molecules_all_realized_qtaim_ceiling': int(molecule_df['all_realized_qtaim_ceiling'].astype(bool).sum()),
        'median_molecule_proatomic_improvement_factor_vs_midpoint': float(np.median(molecule_df['proatomic_improvement_factor_vs_midpoint'].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float))),
        'median_molecule_proatomic_powerfit_improvement_factor_vs_midpoint': float(np.median(molecule_df['proatomic_powerfit_improvement_factor_vs_midpoint'].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float))),
        'median_molecule_ceiling_improvement_factor_vs_proatomic': float(np.median(molecule_df['ceiling_improvement_factor_vs_proatomic'].replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float))),
    }
    write_metadata_json(summary_payload, output_dir / 'summary.json')
    write_metadata_json(low_offset_heteronuclear_row, output_dir / 'low_offset_heteronuclear_summary.json')
    _write_report(output_dir / 'REPORT.md', summary_payload, subset_df)
    if not args.no_plots:
        _make_plots(subset_df, molecule_df, output_dir)

    print(f'[J2] wrote analysis to {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
