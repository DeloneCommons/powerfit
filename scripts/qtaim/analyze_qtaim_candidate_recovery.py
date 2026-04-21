"""Experiment J3: support recovery from generic excessive candidate graphs.

This script evaluates whether a frozen local proatomic separator law, combined
with one-shot power-diagram fitting, can recover useful QTAIM support starting
from a simple distance-cutoff candidate graph.

The primary intent is *not* to optimize a chemistry rule. The 5.0 Å cutoff is
interpreted as the domain-informed excessive support graph for the current
H/C/N/O/F/S/Cl molecular benchmark, while smaller cutoffs (default 4.5 Å and
4.0 Å) act as deliberate undercoverage ablations. The analysis reports how
candidate coverage, recovered-support precision/recall, and matched-edge
separator quality change with the cutoff.

Inputs
------
A manifest CSV with at least:
- ``json_path``
- ``connectivity_smiles`` or ``smiles``

Optional manifest columns propagated when present:
- ``system_key``
- ``name``
- ``selection_stratum`` / ``group``

Rows whose QTAIM JSON is not yet available are skipped by default so the script
can be run on an in-progress full manifest.

Outputs
-------
The output directory contains:
- ``molecule_level.csv``
- ``subset_summary.csv``
- ``qtaim_edge_level.csv``
- ``candidate_edge_level.csv``
- ``selected_edge_level.csv``
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
from _proatomic_pairlaw import load_lookup_csv, write_metadata_json
from local_support import analyze_pair_local_support


CUTS_DEFAULT = (4.0, 4.5, 5.0)
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


def undirected(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def box_for_points(points: np.ndarray, margin: float) -> pv.Box:
    mins = points.min(axis=0) - margin
    maxs = points.max(axis=0) + margin
    return pv.Box(bounds=tuple((float(mins[k]), float(maxs[k])) for k in range(3)))


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


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return float('nan')
    return float(numerator / denominator)


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


def _distance_bin(path_distance: int) -> str:
    return 'bonded' if path_distance <= 1 else 'nonbonded'


def _fraction_from_weights(points: np.ndarray, weights: np.ndarray, i: int, j: int) -> float:
    d = points[j] - points[i]
    dd = float(np.dot(d, d))
    if dd <= 0.0:
        return float('nan')
    return float(0.5 * (1.0 + (float(weights[i]) - float(weights[j])) / dd))


def _position_from_weights(points: np.ndarray, weights: np.ndarray, i: int, j: int) -> float:
    t = _fraction_from_weights(points, weights, i, j)
    length = float(np.linalg.norm(points[j] - points[i]))
    return float(t * length)


def _extract_face_rows(cells: list[dict]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()
    for cell in cells:
        i = int(cell['id'])
        for face in cell.get('faces', []):
            j = int(face.get('adjacent_cell', -1))
            if j < 0:
                continue
            key = undirected(i, j)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    'pair': key,
                    'intersection_inside': bool(face.get('intersection_inside', False)),
                    'intersection_edge_min_dist': float(face.get('intersection_edge_min_dist', float('nan'))),
                    'intersection_centroid_dist': float(face.get('intersection_centroid_dist', float('nan'))),
                    'area': float(face.get('area', float('nan'))),
                    'intersection': list(map(float, face.get('intersection', [float('nan')] * 3))),
                    'centroid': list(map(float, face.get('centroid', [float('nan')] * 3))),
                    'normal': list(map(float, face.get('normal', [float('nan')] * 3))),
                }
            )
    return rows


def _compute_cells(points: np.ndarray, box: pv.Box, radii: np.ndarray):
    cells, diagnostics = pv.compute(
        points,
        domain=box,
        mode='power',
        radii=radii,
        return_vertices=True,
        return_faces=True,
        return_adjacency=False,
        return_diagnostics=True,
        tessellation_check='diagnose',
    )
    pv.annotate_face_properties(cells, domain=box, diagnostics=diagnostics)
    return cells, diagnostics


def _analytic_fields(points: np.ndarray, weights: np.ndarray, box: pv.Box, pair: tuple[int, int]) -> dict[str, object]:
    diag = analyze_pair_local_support(points, weights, pair[0], pair[1], bounds=np.asarray(box.bounds, dtype=float))
    return {
        'analytic_t_recovered': float(diag.t_connector),
        'analytic_sigma': float(diag.sigma),
        'analytic_clearance_unclipped': float(diag.unclipped_clearance),
        'analytic_box_clearance': float(diag.box_clearance),
        'analytic_clearance_clipped': float(diag.clipped_clearance),
        'analytic_visible_unclipped': bool(diag.analytic_visible_unclipped),
        'analytic_visible_clipped': bool(diag.analytic_visible_clipped),
        'analytic_margin_safe': bool(diag.analytic_margin_safe),
    }


def _f1(pred: set[tuple[int, int]], true: set[tuple[int, int]]) -> dict[str, float]:
    tp = len(pred & true)
    fp = len(pred - true)
    fn = len(true - pred)
    precision = tp / len(pred) if pred else float('nan')
    recall = tp / len(true) if true else float('nan')
    f1_value = 2.0 * precision * recall / (precision + recall) if pred and true and (precision + recall) > 0.0 else (1.0 if not pred and not true else 0.0)
    return {
        'tp': float(tp),
        'fp': float(fp),
        'fn': float(fn),
        'precision': float(precision),
        'recall': float(recall),
        'f1': float(f1_value),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Run the J3 candidate-recovery analysis on a molecular QTAIM manifest.'
    )
    parser.add_argument('manifest_csv', help='Manifest CSV with json_path plus connectivity_smiles/smiles.')
    parser.add_argument('--lookup-csv', default=None, help='Pair-law lookup CSV. Defaults to data/proatomic/pairlaw/separator_lookup.csv.')
    parser.add_argument('--output-dir', default=None, help='Directory for analysis outputs. Defaults to results/qtaim_main/J3_candidate_recovery_refresh when the manifest lives under data/qtaim_main/.')
    parser.add_argument('--cutoffs', nargs='+', type=float, default=list(CUTS_DEFAULT), help=f'Candidate distance cutoffs in angstrom (default: {", ".join(f"{x:.1f}" for x in CUTS_DEFAULT)}).')
    parser.add_argument('--box-margin', type=float, default=BOX_MARGIN_DEFAULT, help=f'Bounding-box margin in angstrom for non-periodic tessellations (default: {BOX_MARGIN_DEFAULT:.1f}).')
    parser.add_argument('--offset-threshold', type=float, default=LOW_OFFSET_DEFAULT, help=f'Low-offset threshold in angstrom for secondary summaries (default: {LOW_OFFSET_DEFAULT:.2f}).')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm progress bars.')
    parser.add_argument('--require-all', action='store_true', help='Fail if any listed QTAIM JSON is missing instead of skipping it.')
    parser.add_argument('--no-plots', action='store_true', help='Do not generate diagnostic figures.')
    return parser


def choose_default_output_dir(manifest_csv: Path) -> Path:
    repo_root = manifest_csv.parents[2] if len(manifest_csv.parents) >= 3 else manifest_csv.parent
    if manifest_csv.parent.name == 'qtaim_main':
        return (repo_root / 'results' / 'qtaim_main' / 'J3_candidate_recovery_refresh').resolve()
    return (repo_root / 'results' / f'{manifest_csv.stem}_candidate_recovery').resolve()


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
    cutoffs = tuple(sorted({float(x) for x in args.cutoffs}))
    if not cutoffs:
        parser.error('At least one cutoff must be provided.')
    return args, manifest_csv, lookup_csv, output_dir, cutoffs


def _empty_subset_row(cutoff: float, subset: str) -> dict[str, object]:
    return {
        'cutoff_angstrom': float(cutoff),
        'subset': subset,
        'n_molecules': 0,
        'n_true_edges': 0,
        'n_candidate_edges': 0,
        'n_candidate_true_edges': 0,
        'n_recovered_edges_raw': 0,
        'n_recovered_edges_visible': 0,
        'candidate_inflation_factor': float('nan'),
        'candidate_coverage': float('nan'),
        'candidate_precision': float('nan'),
        'candidate_f1': float('nan'),
        'recovered_precision_raw': float('nan'),
        'recovered_recall_raw': float('nan'),
        'recovered_f1_raw': float('nan'),
        'conditional_recall_raw': float('nan'),
        'recovered_precision_visible': float('nan'),
        'recovered_recall_visible': float('nan'),
        'recovered_f1_visible': float('nan'),
        'conditional_recall_visible': float('nan'),
        'recovered_true_edge_separator_rmse_angstrom': float('nan'),
        'recovered_true_edge_separator_mae_angstrom': float('nan'),
        'recovered_true_edge_separator_rmse_fraction': float('nan'),
        'recovered_visible_true_edge_separator_rmse_angstrom': float('nan'),
        'recovered_visible_true_edge_separator_mae_angstrom': float('nan'),
        'extra_edge_rate_raw': float('nan'),
        'extra_edge_rate_visible': float('nan'),
        'mean_unaccounted_pair_count': float('nan'),
        'mean_candidate_fit_status_optimal': float('nan'),
        'all_true_edges_covered_fraction': float('nan'),
        'all_true_edges_recovered_raw_fraction': float('nan'),
        'all_true_edges_recovered_visible_fraction': float('nan'),
    }


def _subset_summary(cutoff: float, subset_name: str, q_df: pd.DataFrame, candidate_df: pd.DataFrame, mol_df: pd.DataFrame, selected_df: pd.DataFrame) -> dict[str, object]:
    true_pairs = {(str(r.system_key), int(r.atom_i), int(r.atom_j)) for r in q_df.itertuples(index=False)}
    candidate_pairs = {(str(r.system_key), int(r.atom_i), int(r.atom_j)) for r in candidate_df.itertuples(index=False)}
    candidate_true = candidate_pairs & true_pairs
    selected_raw = {(str(r.system_key), int(r.atom_i), int(r.atom_j)) for r in selected_df.itertuples(index=False)}
    selected_visible = {(str(r.system_key), int(r.atom_i), int(r.atom_j)) for r in selected_df[selected_df['intersection_inside']].itertuples(index=False)}

    if not true_pairs:
        return _empty_subset_row(cutoff, subset_name)

    raw_metrics = _f1(selected_raw, true_pairs)
    vis_metrics = _f1(selected_visible, true_pairs)

    candidate_precision = _safe_ratio(len(candidate_true), len(candidate_pairs))
    candidate_coverage = _safe_ratio(len(candidate_true), len(true_pairs))
    candidate_f1 = (
        2.0 * candidate_precision * candidate_coverage / (candidate_precision + candidate_coverage)
        if math.isfinite(candidate_precision) and math.isfinite(candidate_coverage) and (candidate_precision + candidate_coverage) > 0.0
        else float('nan')
    )

    raw_true_mask = selected_df['is_qtaim_edge'].astype(bool).to_numpy(dtype=bool)
    vis_true_mask = (selected_df['is_qtaim_edge'].astype(bool) & selected_df['intersection_inside'].astype(bool)).to_numpy(dtype=bool)

    raw_ang = selected_df.loc[raw_true_mask, 'err_recovered_angstrom'].to_numpy(dtype=float)
    raw_frac = selected_df.loc[raw_true_mask, 'err_recovered_fraction'].to_numpy(dtype=float)
    vis_ang = selected_df.loc[vis_true_mask, 'err_recovered_angstrom'].to_numpy(dtype=float)

    return {
        'cutoff_angstrom': float(cutoff),
        'subset': subset_name,
        'n_molecules': int(q_df['system_key'].nunique()),
        'n_true_edges': int(len(true_pairs)),
        'n_candidate_edges': int(len(candidate_pairs)),
        'n_candidate_true_edges': int(len(candidate_true)),
        'n_recovered_edges_raw': int(len(selected_raw)),
        'n_recovered_edges_visible': int(len(selected_visible)),
        'candidate_inflation_factor': _safe_ratio(len(candidate_pairs), len(true_pairs)),
        'candidate_coverage': candidate_coverage,
        'candidate_precision': candidate_precision,
        'candidate_f1': candidate_f1,
        'recovered_precision_raw': raw_metrics['precision'],
        'recovered_recall_raw': raw_metrics['recall'],
        'recovered_f1_raw': raw_metrics['f1'],
        'conditional_recall_raw': _safe_ratio(len(selected_raw & candidate_true), len(candidate_true)),
        'recovered_precision_visible': vis_metrics['precision'],
        'recovered_recall_visible': vis_metrics['recall'],
        'recovered_f1_visible': vis_metrics['f1'],
        'conditional_recall_visible': _safe_ratio(len(selected_visible & candidate_true), len(candidate_true)),
        'recovered_true_edge_separator_rmse_angstrom': rmse(raw_ang),
        'recovered_true_edge_separator_mae_angstrom': mae(raw_ang),
        'recovered_true_edge_separator_rmse_fraction': rmse(raw_frac),
        'recovered_visible_true_edge_separator_rmse_angstrom': rmse(vis_ang),
        'recovered_visible_true_edge_separator_mae_angstrom': mae(vis_ang),
        'extra_edge_rate_raw': _safe_ratio(len(selected_raw - true_pairs), len(selected_raw)) if selected_raw else float('nan'),
        'extra_edge_rate_visible': _safe_ratio(len(selected_visible - true_pairs), len(selected_visible)) if selected_visible else float('nan'),
        'mean_unaccounted_pair_count': float(mol_df['unaccounted_pair_count'].mean()) if not mol_df.empty else float('nan'),
        'mean_candidate_fit_status_optimal': float(np.mean(mol_df['fit_status'].astype(str) == 'optimal')) if not mol_df.empty else float('nan'),
        'all_true_edges_covered_fraction': float(np.mean(mol_df['all_true_edges_in_candidate'].astype(bool))) if not mol_df.empty else float('nan'),
        'all_true_edges_recovered_raw_fraction': float(np.mean(mol_df['all_true_edges_recovered_raw'].astype(bool))) if not mol_df.empty else float('nan'),
        'all_true_edges_recovered_visible_fraction': float(np.mean(mol_df['all_true_edges_recovered_visible'].astype(bool))) if not mol_df.empty else float('nan'),
    }


def _write_report(path: Path, summary: dict[str, object], subset_df: pd.DataFrame) -> None:
    lines = [
        '# J3 candidate-graph recovery',
        '',
        f'- Manifest: `{summary["manifest_csv"]}`',
        f'- Pair-law lookup: `{summary["lookup_csv"]}`',
        f'- Manifest rows: **{summary["n_manifest_rows"]}**',
        f'- Processed molecules: **{summary["n_processed_rows"]}**',
        f'- Skipped rows: **{summary["n_skipped_rows"]}**',
        f'- Candidate cutoffs (Å): **{", ".join(f"{x:.1f}" for x in summary["cutoffs_angstrom"])}**',
        '',
        '## Overall summary by cutoff',
        '',
    ]
    for cutoff in summary['cutoffs_angstrom']:
        sub = subset_df[(subset_df['cutoff_angstrom'] == float(cutoff)) & (subset_df['subset'] == 'all')]
        if sub.empty:
            continue
        row = sub.iloc[0]
        lines += [
            f'### {float(cutoff):.1f} Å',
            '',
            f'- Candidate inflation factor: **{row["candidate_inflation_factor"]:.3f}**',
            f'- Candidate coverage: **{100.0 * row["candidate_coverage"]:.2f}%**',
            f'- Recovered support precision / recall / F1 (raw): **{row["recovered_precision_raw"]:.3f} / {row["recovered_recall_raw"]:.3f} / {row["recovered_f1_raw"]:.3f}**',
            f'- Conditional recall (raw): **{row["conditional_recall_raw"]:.3f}**',
            f'- Recovered support precision / recall / F1 (visible): **{row["recovered_precision_visible"]:.3f} / {row["recovered_recall_visible"]:.3f} / {row["recovered_f1_visible"]:.3f}**',
            f'- Matched true-edge separator RMSE (raw / visible): **{row["recovered_true_edge_separator_rmse_angstrom"]:.6f} / {row["recovered_visible_true_edge_separator_rmse_angstrom"]:.6f} Å**',
            f'- Extra-edge rate (raw / visible): **{row["extra_edge_rate_raw"]:.3f} / {row["extra_edge_rate_visible"]:.3f}**',
            '',
        ]
    bonded_ref = subset_df[(subset_df['cutoff_angstrom'] == float(summary['reference_cutoff_angstrom'])) & (subset_df['subset'] == 'bonded')]
    nonbonded_ref = subset_df[(subset_df['cutoff_angstrom'] == float(summary['reference_cutoff_angstrom'])) & (subset_df['subset'] == 'nonbonded')]
    if not bonded_ref.empty and not nonbonded_ref.empty:
        b = bonded_ref.iloc[0]
        nb = nonbonded_ref.iloc[0]
        lines += [
            '## Bonded vs nonbonded at the reference cutoff',
            '',
            f'- Bonded: recall(raw) **{b["recovered_recall_raw"]:.3f}**, RMSE(raw) **{b["recovered_true_edge_separator_rmse_angstrom"]:.6f} Å**.',
            f'- Nonbonded: recall(raw) **{nb["recovered_recall_raw"]:.3f}**, RMSE(raw) **{nb["recovered_true_edge_separator_rmse_angstrom"]:.6f} Å**.',
            '- Interpretation: separator quality on recovered bonded edges is the main practical signal; nonbonded tails remain a harder regime where graph exactness is less meaningful and representability limitations matter more.',
            '',
        ]
    if summary['cutoffs_angstrom']:
        ref = subset_df[(subset_df['cutoff_angstrom'] == float(min(summary['cutoffs_angstrom']))) & (subset_df['subset'] == 'all')]
        if not ref.empty and float(ref.iloc[0]['candidate_coverage']) == 1.0:
            lines += [
                '## Full-benchmark takeaway',
                '',
                f'- On the full frozen benchmark, even the smallest tested cutoff (**{float(min(summary["cutoffs_angstrom"])):.1f} Å**) already covers all observed QTAIM-supported pairs.',
                '- The practical effect of enlarging the cutoff is therefore mainly to inflate the candidate graph, not to improve recall.',
                '- The most informative graph-quality metric on this subset is the visible recovered support, not the raw realized support.',
                '',
            ]
    lines += [
        '## Outputs',
        '',
        '- `molecule_level.csv`',
        '- `subset_summary.csv`',
        '- `qtaim_edge_level.csv`',
        '- `candidate_edge_level.csv`',
        '- `selected_edge_level.csv`',
        '- `summary.json`',
    ]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _make_plots(subset_df: pd.DataFrame, output_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return

    fig_dir = output_dir / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)

    overall = subset_df[subset_df['subset'] == 'all'].sort_values('cutoff_angstrom')
    if not overall.empty:
        x = overall['cutoff_angstrom'].to_numpy(dtype=float)

        fig = plt.figure(figsize=(8.0, 4.5))
        ax = fig.add_subplot(111)
        ax.plot(x, overall['candidate_coverage'].to_numpy(dtype=float), marker='o', label='candidate coverage')
        ax.plot(x, overall['recovered_recall_raw'].to_numpy(dtype=float), marker='o', label='recovered recall (raw)')
        ax.plot(x, overall['conditional_recall_raw'].to_numpy(dtype=float), marker='o', label='conditional recall (raw)')
        ax.plot(x, overall['recovered_precision_raw'].to_numpy(dtype=float), marker='o', label='recovered precision (raw)')
        ax.set_xlabel('candidate cutoff (Å)')
        ax.set_ylabel('fraction')
        ax.set_title('J3: support recoverability vs cutoff')
        ax.set_ylim(0.0, 1.05)
        ax.legend()
        fig.tight_layout()
        save_figure(
            fig,
            fig_dir / 'support_recoverability_vs_cutoff.png',
            title='support_recoverability_vs_cutoff',
            png_dpi=200,
            save_pdf_sibling=True,
        )
        plt.close(fig)

        fig = plt.figure(figsize=(8.0, 4.5))
        ax = fig.add_subplot(111)
        ax.plot(x, overall['recovered_true_edge_separator_rmse_angstrom'].to_numpy(dtype=float), marker='o', label='raw recovered true-edge RMSE')
        ax.plot(x, overall['recovered_visible_true_edge_separator_rmse_angstrom'].to_numpy(dtype=float), marker='o', label='visible recovered true-edge RMSE')
        ax.set_xlabel('candidate cutoff (Å)')
        ax.set_ylabel('separator RMSE (Å)')
        ax.set_title('J3: separator quality on recovered true edges')
        ax.legend()
        fig.tight_layout()
        save_figure(
            fig,
            fig_dir / 'recovered_true_edge_rmse_vs_cutoff.png',
            title='recovered_true_edge_rmse_vs_cutoff',
            png_dpi=200,
            save_pdf_sibling=True,
        )
        plt.close(fig)


def main(argv: Iterable[str] | None = None) -> int:
    args, manifest_csv, lookup_csv, output_dir, cutoffs = parse_args(argv)
    manifest = load_manifest(manifest_csv)
    lookup = load_lookup_csv(lookup_csv)

    qtaim_edge_rows: list[dict[str, object]] = []
    candidate_edge_rows: list[dict[str, object]] = []
    selected_edge_rows: list[dict[str, object]] = []
    molecule_rows: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []

    total = len(manifest)
    progress_write(f'Loaded {total} QTAIM rows from {manifest_csv}')
    progress_write(f'Pair-law lookup: {lookup_csv}')
    progress_write(f'Cutoffs: {", ".join(f"{x:.1f}" for x in cutoffs)} Å; output dir: {output_dir}')
    if not args.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')

    manifest_iter = iter_progress(manifest, total=total, desc='J3 recovery', disable=args.no_progress, unit='system')
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
        qtaim_pairs: set[tuple[int, int]] = set()
        qtaim_obs: dict[tuple[int, int], dict[str, object]] = {}
        for edge in obj['bcp_graph']:
            atom_i = int(edge['atom_i']) - 1
            atom_j = int(edge['atom_j']) - 1
            pair = undirected(atom_i, atom_j)
            cp = cp_by_index[int(edge['cp_index'])]
            point_i = positions[pair[0]]
            point_j = positions[pair[1]]
            bcp = np.array(cp['position_angstrom'], dtype=float)
            t_obs, offset = projection_fraction_and_offset(point_i, point_j, bcp)
            bond_length = float(np.linalg.norm(point_j - point_i))
            path_distance = int(round(float(graph_info.topological_distances[pair[0], pair[1]])))
            element_i = atom_symbols_json[pair[0]]
            element_j = atom_symbols_json[pair[1]]
            qtaim_pairs.add(pair)
            qtaim_obs[pair] = {
                'cp_index': int(edge['cp_index']),
                't_obs': float(t_obs),
                'x_obs_angstrom': float(t_obs * bond_length),
                'offset_angstrom': float(offset),
                'offset_over_length': float(offset / bond_length),
                'bond_length_angstrom': bond_length,
                'graph_distance': path_distance,
                'graph_distance_bin': _distance_bin(path_distance),
                'is_bonded': path_distance == 1,
                'is_nonbonded': path_distance != 1,
                'element_i': element_i,
                'element_j': element_j,
                'pair_type': '-'.join(sorted((element_i, element_j))),
                'is_homonuclear': element_i == element_j,
                'is_heteronuclear': element_i != element_j,
            }

        if not qtaim_pairs:
            skipped_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'json_path': str(row.json_path),
                'reason': 'no_bcp_edges',
            })
            continue

        n_atoms = len(atom_symbols_json)
        all_pair_dist = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=2)
        box = box_for_points(positions, margin=float(args.box_margin))

        for cutoff in cutoffs:
            candidate_pairs: list[tuple[int, int]] = []
            candidate_constraints: list[tuple[int, int, float]] = []
            for i in range(n_atoms):
                for j in range(i + 1, n_atoms):
                    dij = float(all_pair_dist[i, j])
                    if dij > float(cutoff):
                        continue
                    pair = (i, j)
                    pred = lookup.predict(atom_symbols_json[i], atom_symbols_json[j], dij)
                    candidate_pairs.append(pair)
                    candidate_constraints.append((i, j, float(pred.fraction_from_i)))

            candidate_pair_set = set(candidate_pairs)
            candidate_true_set = qtaim_pairs & candidate_pair_set
            candidate_false_set = candidate_pair_set - qtaim_pairs

            local_candidate_rows: list[dict[str, object]] = []
            for pair in sorted(candidate_pair_set):
                i, j = pair
                dij = float(all_pair_dist[i, j])
                path_distance = int(round(float(graph_info.topological_distances[i, j])))
                local_candidate_rows.append(
                    {
                        'system_key': row.system_key,
                        'name': row.name,
                        'group': row.group,
                        'cutoff_angstrom': float(cutoff),
                        'atom_i': i + 1,
                        'atom_j': j + 1,
                        'pair_key': f'{i + 1}-{j + 1}',
                        'element_i': atom_symbols_json[i],
                        'element_j': atom_symbols_json[j],
                        'pair_type': '-'.join(sorted((atom_symbols_json[i], atom_symbols_json[j]))),
                        'graph_distance': path_distance,
                        'graph_distance_bin': _distance_bin(path_distance),
                        'is_bonded': path_distance == 1,
                        'is_nonbonded': path_distance != 1,
                        'bond_length_angstrom': dij,
                        'is_qtaim_edge': pair in qtaim_pairs,
                    }
                )

            local_q_rows: list[dict[str, object]] = []
            for pair in sorted(qtaim_pairs):
                obs = qtaim_obs[pair]
                pred = lookup.predict(obs['element_i'], obs['element_j'], float(obs['bond_length_angstrom']))
                local_q_rows.append(
                    {
                        'system_key': row.system_key,
                        'name': row.name,
                        'group': row.group,
                        'cutoff_angstrom': float(cutoff),
                        'atom_i': pair[0] + 1,
                        'atom_j': pair[1] + 1,
                        'pair_key': f'{pair[0] + 1}-{pair[1] + 1}',
                        'pair_type': obs['pair_type'],
                        'element_i': obs['element_i'],
                        'element_j': obs['element_j'],
                        'is_homonuclear': obs['is_homonuclear'],
                        'is_heteronuclear': obs['is_heteronuclear'],
                        'graph_distance': obs['graph_distance'],
                        'graph_distance_bin': obs['graph_distance_bin'],
                        'is_bonded': obs['is_bonded'],
                        'is_nonbonded': obs['is_nonbonded'],
                        'cp_index': obs['cp_index'],
                        'bond_length_angstrom': obs['bond_length_angstrom'],
                        'offset_angstrom': obs['offset_angstrom'],
                        'offset_over_length': obs['offset_over_length'],
                        't_obs': obs['t_obs'],
                        'x_obs_angstrom': obs['x_obs_angstrom'],
                        't_proatomic': float(pred.fraction_from_i),
                        'x_proatomic_angstrom': float(pred.x_from_i_angstrom),
                        'err_proatomic_fraction': float(pred.fraction_from_i - obs['t_obs']),
                        'err_proatomic_angstrom': float(pred.x_from_i_angstrom - obs['x_obs_angstrom']),
                        'in_candidate_graph': pair in candidate_pair_set,
                    }
                )

            if not candidate_pairs:
                qtaim_edge_rows.extend(local_q_rows)
                candidate_edge_rows.extend(local_candidate_rows)
                molecule_rows.append(
                    {
                        'system_key': row.system_key,
                        'name': row.name,
                        'group': row.group,
                        'cutoff_angstrom': float(cutoff),
                        'n_atoms': int(n_atoms),
                        'true_edge_count': int(len(qtaim_pairs)),
                        'candidate_edge_count': 0,
                        'candidate_true_edge_count': 0,
                        'candidate_false_edge_count': 0,
                        'candidate_inflation_factor': float('nan'),
                        'candidate_coverage': 0.0,
                        'candidate_precision': float('nan'),
                        'fit_status': 'no_candidate_edges',
                        'fit_status_detail': '',
                        'fit_warnings': '',
                        'unaccounted_pair_count': 0,
                        'recovered_edge_count_raw': 0,
                        'recovered_edge_count_visible': 0,
                        'recovered_true_edge_count_raw': 0,
                        'recovered_true_edge_count_visible': 0,
                        'recovered_false_edge_count_raw': 0,
                        'recovered_false_edge_count_visible': 0,
                        'recovered_precision_raw': float('nan'),
                        'recovered_recall_raw': 0.0,
                        'recovered_f1_raw': 0.0,
                        'conditional_recall_raw': 0.0,
                        'recovered_precision_visible': float('nan'),
                        'recovered_recall_visible': 0.0,
                        'recovered_f1_visible': 0.0,
                        'conditional_recall_visible': 0.0,
                        'recovered_true_edge_rmse_angstrom': float('nan'),
                        'recovered_true_edge_mae_angstrom': float('nan'),
                        'recovered_true_edge_rmse_fraction': float('nan'),
                        'recovered_visible_true_edge_rmse_angstrom': float('nan'),
                        'recovered_visible_true_edge_mae_angstrom': float('nan'),
                        'extra_edge_rate_raw': float('nan'),
                        'extra_edge_rate_visible': float('nan'),
                        'all_true_edges_in_candidate': False,
                        'all_true_edges_recovered_raw': False,
                        'all_true_edges_recovered_visible': False,
                    }
                )
                continue

            try:
                resolved = pv.resolve_pair_bisector_constraints(positions, candidate_constraints, measurement='fraction', domain=box)
                fit = pv.fit_power_weights(positions, resolved, measurement='fraction', domain=box, connectivity_check='diagnose')
                realized = pv.match_realized_pairs(
                    positions,
                    domain=box,
                    radii=np.asarray(fit.radii, dtype=float),
                    constraints=resolved,
                    tessellation_check='diagnose',
                    unaccounted_pair_check='diagnose',
                )
                cells, _diag = _compute_cells(positions, box, np.asarray(fit.radii, dtype=float))
                face_rows = _extract_face_rows(cells)
                face_by_pair = {entry['pair']: entry for entry in face_rows}
                recovered_pairs_raw = set(face_by_pair)
                recovered_pairs_visible = {pair for pair, face in face_by_pair.items() if bool(face['intersection_inside'])}
                weights = np.asarray(fit.weights, dtype=float)
            except Exception as exc:
                qtaim_edge_rows.extend(local_q_rows)
                skipped_rows.append(
                    {
                        'system_key': row.system_key,
                        'name': row.name,
                        'group': row.group,
                        'json_path': str(row.json_path),
                        'reason': f'j3_fit_error@{cutoff:.1f}A: {exc}',
                    }
                )
                continue

            # Update QTAIM-edge rows now that recovery data are known.
            for edge_row in local_q_rows:
                pair = undirected(int(edge_row['atom_i']) - 1, int(edge_row['atom_j']) - 1)
                recovered_raw = pair in recovered_pairs_raw
                recovered_visible = pair in recovered_pairs_visible
                t_rec = _fraction_from_weights(positions, weights, pair[0], pair[1]) if recovered_raw else float('nan')
                x_rec = _position_from_weights(positions, weights, pair[0], pair[1]) if recovered_raw else float('nan')
                face = face_by_pair.get(pair)
                analytic = _analytic_fields(positions, weights, box, pair) if recovered_raw else {
                    'analytic_t_recovered': float('nan'),
                    'analytic_sigma': float('nan'),
                    'analytic_clearance_unclipped': float('nan'),
                    'analytic_box_clearance': float('nan'),
                    'analytic_clearance_clipped': float('nan'),
                    'analytic_visible_unclipped': False,
                    'analytic_visible_clipped': False,
                    'analytic_margin_safe': False,
                }
                edge_row.update(
                    {
                        'recovered_raw': recovered_raw,
                        'recovered_visible': recovered_visible,
                        't_recovered': float(t_rec) if math.isfinite(t_rec) else float('nan'),
                        'x_recovered_angstrom': float(x_rec) if math.isfinite(x_rec) else float('nan'),
                        'err_recovered_fraction': float(t_rec - float(edge_row['t_obs'])) if recovered_raw and math.isfinite(t_rec) else float('nan'),
                        'err_recovered_angstrom': float(x_rec - float(edge_row['x_obs_angstrom'])) if recovered_raw and math.isfinite(x_rec) else float('nan'),
                        'intersection_inside': bool(face['intersection_inside']) if face is not None else False,
                        'intersection_edge_min_dist': float(face['intersection_edge_min_dist']) if face is not None else float('nan'),
                        'intersection_centroid_dist': float(face['intersection_centroid_dist']) if face is not None else float('nan'),
                        'face_area': float(face['area']) if face is not None else float('nan'),
                        'is_unaccounted_recovered_edge': recovered_raw and pair not in candidate_pair_set,
                    }
                )
                edge_row.update(analytic)
            qtaim_edge_rows.extend(local_q_rows)
            candidate_edge_rows.extend(local_candidate_rows)

            # Selected/recovered edge rows for the full tessellation graph.
            local_selected_rows: list[dict[str, object]] = []
            for pair, face in face_by_pair.items():
                i, j = pair
                path_distance = int(round(float(graph_info.topological_distances[i, j])))
                bond_length = float(np.linalg.norm(positions[j] - positions[i]))
                t_rec = _fraction_from_weights(positions, weights, i, j)
                x_rec = _position_from_weights(positions, weights, i, j)
                analytic = _analytic_fields(positions, weights, box, pair)
                is_qtaim = pair in qtaim_pairs
                qobs = qtaim_obs.get(pair)
                local_selected_rows.append(
                    {
                        'system_key': row.system_key,
                        'name': row.name,
                        'group': row.group,
                        'cutoff_angstrom': float(cutoff),
                        'atom_i': i + 1,
                        'atom_j': j + 1,
                        'pair_key': f'{i + 1}-{j + 1}',
                        'element_i': atom_symbols_json[i],
                        'element_j': atom_symbols_json[j],
                        'pair_type': '-'.join(sorted((atom_symbols_json[i], atom_symbols_json[j]))),
                        'graph_distance': path_distance,
                        'graph_distance_bin': _distance_bin(path_distance),
                        'is_bonded': path_distance == 1,
                        'is_nonbonded': path_distance != 1,
                        'bond_length_angstrom': bond_length,
                        'in_candidate_graph': pair in candidate_pair_set,
                        'is_qtaim_edge': is_qtaim,
                        'is_unaccounted_recovered_edge': pair not in candidate_pair_set,
                        'intersection_inside': bool(face['intersection_inside']),
                        'intersection_edge_min_dist': float(face['intersection_edge_min_dist']),
                        'intersection_centroid_dist': float(face['intersection_centroid_dist']),
                        'face_area': float(face['area']),
                        't_recovered': float(t_rec),
                        'x_recovered_angstrom': float(x_rec),
                        't_obs': float(qobs['t_obs']) if qobs is not None else float('nan'),
                        'x_obs_angstrom': float(qobs['x_obs_angstrom']) if qobs is not None else float('nan'),
                        'offset_angstrom': float(qobs['offset_angstrom']) if qobs is not None else float('nan'),
                        'err_recovered_fraction': float(t_rec - qobs['t_obs']) if qobs is not None else float('nan'),
                        'err_recovered_angstrom': float(x_rec - qobs['x_obs_angstrom']) if qobs is not None else float('nan'),
                        'analytic_t_recovered': float(analytic['analytic_t_recovered']),
                        'analytic_sigma': float(analytic['analytic_sigma']),
                        'analytic_clearance_unclipped': float(analytic['analytic_clearance_unclipped']),
                        'analytic_box_clearance': float(analytic['analytic_box_clearance']),
                        'analytic_clearance_clipped': float(analytic['analytic_clearance_clipped']),
                        'analytic_visible_unclipped': bool(analytic['analytic_visible_unclipped']),
                        'analytic_visible_clipped': bool(analytic['analytic_visible_clipped']),
                        'analytic_margin_safe': bool(analytic['analytic_margin_safe']),
                    }
                )
            selected_edge_rows.extend(local_selected_rows)

            raw_true_rows = [r for r in local_selected_rows if r['is_qtaim_edge']]
            vis_true_rows = [r for r in local_selected_rows if r['is_qtaim_edge'] and r['intersection_inside']]
            recovered_true_raw = {pair for pair in recovered_pairs_raw if pair in qtaim_pairs}
            recovered_true_visible = {pair for pair in recovered_pairs_visible if pair in qtaim_pairs}
            raw_metrics = _f1(recovered_pairs_raw, qtaim_pairs)
            visible_metrics = _f1(recovered_pairs_visible, qtaim_pairs)
            molecule_rows.append(
                {
                    'system_key': row.system_key,
                    'name': row.name,
                    'group': row.group,
                    'cutoff_angstrom': float(cutoff),
                    'n_atoms': int(n_atoms),
                    'true_edge_count': int(len(qtaim_pairs)),
                    'candidate_edge_count': int(len(candidate_pair_set)),
                    'candidate_true_edge_count': int(len(candidate_true_set)),
                    'candidate_false_edge_count': int(len(candidate_false_set)),
                    'candidate_inflation_factor': _safe_ratio(len(candidate_pair_set), len(qtaim_pairs)),
                    'candidate_coverage': _safe_ratio(len(candidate_true_set), len(qtaim_pairs)),
                    'candidate_precision': _safe_ratio(len(candidate_true_set), len(candidate_pair_set)),
                    'fit_status': fit.status,
                    'fit_status_detail': getattr(fit, 'status_detail', ''),
                    'fit_warnings': ' | '.join(getattr(fit, 'warnings', ())),
                    'unaccounted_pair_count': int(len(getattr(realized, 'unaccounted_pairs', ()))),
                    'recovered_edge_count_raw': int(len(recovered_pairs_raw)),
                    'recovered_edge_count_visible': int(len(recovered_pairs_visible)),
                    'recovered_true_edge_count_raw': int(len(recovered_true_raw)),
                    'recovered_true_edge_count_visible': int(len(recovered_true_visible)),
                    'recovered_false_edge_count_raw': int(len(recovered_pairs_raw - qtaim_pairs)),
                    'recovered_false_edge_count_visible': int(len(recovered_pairs_visible - qtaim_pairs)),
                    'recovered_precision_raw': raw_metrics['precision'],
                    'recovered_recall_raw': raw_metrics['recall'],
                    'recovered_f1_raw': raw_metrics['f1'],
                    'conditional_recall_raw': _safe_ratio(len(recovered_true_raw & candidate_true_set), len(candidate_true_set)),
                    'recovered_precision_visible': visible_metrics['precision'],
                    'recovered_recall_visible': visible_metrics['recall'],
                    'recovered_f1_visible': visible_metrics['f1'],
                    'conditional_recall_visible': _safe_ratio(len(recovered_true_visible & candidate_true_set), len(candidate_true_set)),
                    'recovered_true_edge_rmse_angstrom': rmse(np.asarray([r['err_recovered_angstrom'] for r in raw_true_rows], dtype=float)),
                    'recovered_true_edge_mae_angstrom': mae(np.asarray([r['err_recovered_angstrom'] for r in raw_true_rows], dtype=float)),
                    'recovered_true_edge_rmse_fraction': rmse(np.asarray([r['err_recovered_fraction'] for r in raw_true_rows], dtype=float)),
                    'recovered_visible_true_edge_rmse_angstrom': rmse(np.asarray([r['err_recovered_angstrom'] for r in vis_true_rows], dtype=float)),
                    'recovered_visible_true_edge_mae_angstrom': mae(np.asarray([r['err_recovered_angstrom'] for r in vis_true_rows], dtype=float)),
                    'extra_edge_rate_raw': _safe_ratio(len(recovered_pairs_raw - qtaim_pairs), len(recovered_pairs_raw)),
                    'extra_edge_rate_visible': _safe_ratio(len(recovered_pairs_visible - qtaim_pairs), len(recovered_pairs_visible)),
                    'all_true_edges_in_candidate': candidate_true_set == qtaim_pairs,
                    'all_true_edges_recovered_raw': recovered_true_raw == qtaim_pairs,
                    'all_true_edges_recovered_visible': recovered_true_visible == qtaim_pairs,
                }
            )

    if not molecule_rows:
        raise RuntimeError('No J3 molecule-level rows were produced; cannot build outputs.')

    qtaim_df = pd.DataFrame(qtaim_edge_rows)
    candidate_df = pd.DataFrame(candidate_edge_rows)
    selected_df = pd.DataFrame(selected_edge_rows)
    molecule_df = pd.DataFrame(molecule_rows)
    skipped_df = pd.DataFrame(skipped_rows)

    subset_rows: list[dict[str, object]] = []
    subset_specs = [
        ('all', lambda q, c, s, m: (q, c, s, m)),
        ('bonded', lambda q, c, s, m: (q[q['is_bonded']], c[c['is_bonded']], s[s['is_bonded']], m)),
        ('nonbonded', lambda q, c, s, m: (q[q['is_nonbonded']], c[c['is_nonbonded']], s[s['is_nonbonded']], m)),
        ('heteronuclear', lambda q, c, s, m: (q[q['is_heteronuclear']], c[(c['element_i'] != c['element_j'])], s[(s['element_i'] != s['element_j'])], m)),
    ]
    for cutoff in cutoffs:
        q_cut = qtaim_df[qtaim_df['cutoff_angstrom'] == float(cutoff)]
        c_cut = candidate_df[candidate_df['cutoff_angstrom'] == float(cutoff)]
        s_cut = selected_df[selected_df['cutoff_angstrom'] == float(cutoff)]
        m_cut = molecule_df[molecule_df['cutoff_angstrom'] == float(cutoff)]
        for subset_name, fn in subset_specs:
            q_sub, c_sub, s_sub, m_sub = fn(q_cut, c_cut, s_cut, m_cut)
            subset_rows.append(_subset_summary(float(cutoff), subset_name, q_sub, c_sub, m_sub, s_sub))
    subset_df = pd.DataFrame(subset_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    qtaim_df.to_csv(output_dir / 'qtaim_edge_level.csv', index=False)
    candidate_df.to_csv(output_dir / 'candidate_edge_level.csv', index=False)
    selected_df.to_csv(output_dir / 'selected_edge_level.csv', index=False)
    molecule_df.to_csv(output_dir / 'molecule_level.csv', index=False)
    subset_df.to_csv(output_dir / 'subset_summary.csv', index=False)
    skipped_df.to_csv(output_dir / 'skipped_rows.csv', index=False)

    summary_payload = {
        'manifest_csv': _display_path(manifest_csv),
        'lookup_csv': _display_path(lookup_csv),
        'cutoffs_angstrom': [float(x) for x in cutoffs],
        'reference_cutoff_angstrom': float(max(cutoffs)),
        'offset_threshold_angstrom': float(args.offset_threshold),
        'box_margin_angstrom': float(args.box_margin),
        'n_manifest_rows': int(len(manifest)),
        'n_processed_rows': int(molecule_df['system_key'].nunique()),
        'n_skipped_rows': int(len(skipped_df)),
        'n_cutoff_runs': int(len(molecule_df)),
        'n_true_edges_total_across_cutoffs': int(len(qtaim_df)),
        'n_candidate_edges_total_across_cutoffs': int(len(candidate_df)),
        'n_selected_edges_total_across_cutoffs': int(len(selected_df)),
    }
    write_metadata_json(summary_payload, output_dir / 'summary.json')
    _write_report(output_dir / 'REPORT.md', summary_payload, subset_df)
    if not args.no_plots:
        _make_plots(subset_df, output_dir)

    print(f'[J3] wrote analysis to {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
