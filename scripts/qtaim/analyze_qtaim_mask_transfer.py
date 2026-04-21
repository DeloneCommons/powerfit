"""Experiment J4b: transfer showcase-derived representability masks to the main dataset.

This script upgrades the curated J4 showcase into a quantitative diagnostic-transfer
experiment. The showcase suggests three increasingly selective face-level masks:

- M0 raw: no representability filter;
- M1 visibility: keep only connector-visible faces;
- M2 numerical sliver cleanup: remove only near-zero-clearance faces from the
  visible graph;
- M3 clearance sweep: apply a clearance threshold to the visible graph after the
  numerical cleanup.

These masks are evaluated on two geometric objects over the molecular QTAIM benchmark:

- ordinary Voronoi tessellations (the no-fitting geometric baseline);
- recovered power-diagram graphs from J3 at a reference candidate cutoff.

The goal is not to freeze a universal threshold. Instead, the script quantifies how
raw/visible/numerical-cleanup/clearance-filtered graph agreement changes, and whether the
remaining disagreement is concentrated in the expected nonbonded tail.

Inputs
------
A manifest CSV with at least:
- ``json_path``
- ``connectivity_smiles`` or ``smiles``

The script also expects J3 recovered-edge outputs under
``results/qtaim_main/J3_candidate_recovery_refresh/selected_edge_level.csv`` unless an
alternative CSV is supplied.

Outputs
-------
The output directory contains:
- ``edge_level.csv``
- ``mask_summary.csv``
- ``clearance_sweep.csv``
- ``clearance_distribution_summary.csv``
- ``molecule_level.csv``
- ``skipped_rows.csv``
- ``summary.json``
- ``REPORT.md``
- figures under ``figures/``
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
from local_support import analyze_pair_local_support


BOX_MARGIN_DEFAULT = 5.0
REFERENCE_CUTOFF_DEFAULT = 5.0
SLIVER_CLEARANCE_DEFAULT = 1.0e-4
CLEARANCE_SWEEP_DEFAULT = (0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.80)
LOW_OFFSET_DEFAULT = 0.02



def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())



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


SUBSET_ORDER = ('all', 'bonded', 'nonbonded', 'heteronuclear')
DISTRIBUTION_SUBSET_ORDER = ('bonded', 'nonbonded')
MASK_ORDER = ('raw', 'visible', 'visible_non_sliver')
MASK_REPORT_LABELS = {
    'raw': 'raw',
    'visible': 'visible',
    'visible_non_sliver': 'visible + numerical cleanup',
}


def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw))


def _csv_path(base_dir: Path, raw: str) -> Path:
    candidate = Path(_expand(raw))
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def undirected(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def box_for_points(points: np.ndarray, margin: float) -> pv.Box:
    mins = points.min(axis=0) - margin
    maxs = points.max(axis=0) + margin
    return pv.Box(bounds=tuple((float(mins[k]), float(maxs[k])) for k in range(3)))


def _compute_cells(points: np.ndarray, box: pv.Box, radii: np.ndarray | None = None):
    mode = 'power' if radii is not None else 'standard'
    cells, diagnostics = pv.compute(
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
    pv.annotate_face_properties(cells, domain=box, diagnostics=diagnostics)
    return cells, diagnostics


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
                    'face_area': float(face.get('area', float('nan'))),
                    'intersection': list(map(float, face.get('intersection', [float('nan')] * 3))),
                    'centroid': list(map(float, face.get('centroid', [float('nan')] * 3))),
                    'normal': list(map(float, face.get('normal', [float('nan')] * 3))),
                }
            )
    return rows


def _analytic_fields(points: np.ndarray, weights: np.ndarray, box: pv.Box, pair: tuple[int, int]) -> dict[str, object]:
    diag = analyze_pair_local_support(points, weights, pair[0], pair[1], bounds=np.asarray(box.bounds, dtype=float))
    return {
        'analytic_t': float(diag.t_connector),
        'analytic_sigma': float(diag.sigma),
        'analytic_clearance_unclipped': float(diag.unclipped_clearance),
        'analytic_box_clearance': float(diag.box_clearance),
        'analytic_clearance_clipped': float(diag.clipped_clearance),
        'analytic_visible_unclipped': bool(diag.analytic_visible_unclipped),
        'analytic_visible_clipped': bool(diag.analytic_visible_clipped),
        'analytic_margin_safe': bool(diag.analytic_margin_safe),
    }


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


def _f1(pred: set[tuple[str, int, int]], true: set[tuple[str, int, int]]) -> dict[str, float]:
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


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return float('nan')
    return float(numerator / denominator)


def choose_default_output_dir(manifest_csv: Path) -> Path:
    repo_root = manifest_csv.parents[2] if len(manifest_csv.parents) >= 3 else manifest_csv.parent
    if manifest_csv.parent.name == 'qtaim_main':
        return (repo_root / 'results' / 'qtaim_main' / 'J4_mask_transfer_refresh').resolve()
    return (repo_root / 'results' / f'{manifest_csv.stem}_mask_transfer').resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Transfer showcase-derived representability masks to the molecular benchmark.'
    )
    parser.add_argument('manifest_csv', help='Manifest CSV with json_path plus connectivity_smiles/smiles.')
    parser.add_argument('--j3-selected-csv', default=None, help='J3 selected_edge_level.csv. Defaults to results/qtaim_main/J3_candidate_recovery_refresh/selected_edge_level.csv.')
    parser.add_argument('--reference-cutoff', type=float, default=REFERENCE_CUTOFF_DEFAULT, help=f'Reference J3 cutoff to evaluate (default: {REFERENCE_CUTOFF_DEFAULT:.1f} Å).')
    parser.add_argument('--output-dir', default=None, help='Directory for analysis outputs.')
    parser.add_argument('--box-margin', type=float, default=BOX_MARGIN_DEFAULT, help=f'Bounding-box margin in angstrom for non-periodic tessellations (default: {BOX_MARGIN_DEFAULT:.1f}).')
    parser.add_argument('--low-offset-threshold', type=float, default=LOW_OFFSET_DEFAULT, help=f'Low-offset threshold in angstrom for contextual summaries (default: {LOW_OFFSET_DEFAULT:.2f}).')
    parser.add_argument('--sliver-clearance-threshold', type=float, default=SLIVER_CLEARANCE_DEFAULT, help=f'Numerical-sliver clearance threshold (default: {SLIVER_CLEARANCE_DEFAULT:.1e}).')
    parser.add_argument('--clearance-thresholds', nargs='+', type=float, default=list(CLEARANCE_SWEEP_DEFAULT), help='Clearance sweep thresholds in angstrom.')
    parser.add_argument('--require-all', action='store_true', help='Fail if any listed QTAIM JSON is missing instead of skipping it.')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm progress bars.')
    parser.add_argument('--no-plots', action='store_true', help='Do not generate diagnostic figures.')
    return parser


def parse_args(argv: Iterable[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest_csv = Path(_expand(args.manifest_csv)).resolve()
    if not manifest_csv.is_file():
        parser.error(f'Manifest CSV not found: {manifest_csv}')
    repo_root = Path(__file__).resolve().parents[2]
    j3_selected_csv = Path(_expand(args.j3_selected_csv)).resolve() if args.j3_selected_csv else (repo_root / 'results' / 'qtaim_main' / 'J3_candidate_recovery_refresh' / 'selected_edge_level.csv').resolve()
    if not j3_selected_csv.is_file():
        parser.error(f'J3 selected_edge_level.csv not found: {j3_selected_csv}')
    output_dir = Path(_expand(args.output_dir)).resolve() if args.output_dir else choose_default_output_dir(manifest_csv)
    clearance_thresholds = tuple(sorted({float(x) for x in args.clearance_thresholds}))
    if not clearance_thresholds:
        parser.error('At least one clearance threshold must be provided.')
    return args, manifest_csv, j3_selected_csv, output_dir, clearance_thresholds


def _subset_mask(df: pd.DataFrame, subset: str) -> pd.Series:
    if subset == 'all':
        return pd.Series(True, index=df.index)
    if subset == 'bonded':
        return df['is_bonded'].astype(bool)
    if subset == 'nonbonded':
        return df['is_nonbonded'].astype(bool)
    if subset == 'heteronuclear':
        return df['is_heteronuclear'].astype(bool)
    raise KeyError(subset)


def _pairs_from_df(df: pd.DataFrame) -> set[tuple[str, int, int]]:
    return {(str(r.system_key), int(r.atom_i), int(r.atom_j)) for r in df.itertuples(index=False)}


def _mask_selector(df: pd.DataFrame, mask_name: str) -> pd.Series:
    if mask_name == 'raw':
        return pd.Series(True, index=df.index)
    if mask_name == 'visible':
        return df['intersection_inside'].astype(bool)
    if mask_name == 'visible_non_sliver':
        return df['intersection_inside'].astype(bool) & (~df['is_numerical_sliver'].astype(bool))
    raise KeyError(mask_name)


def _summary_row(model: str, subset: str, mask_name: str, q_df: pd.DataFrame, pred_df: pd.DataFrame) -> dict[str, object]:
    true_pairs = _pairs_from_df(q_df)
    pred_pairs = _pairs_from_df(pred_df)
    metrics = _f1(pred_pairs, true_pairs)
    extra_edge_rate = _safe_ratio(len(pred_pairs - true_pairs), len(pred_pairs)) if pred_pairs else float('nan')
    return {
        'model': model,
        'subset': subset,
        'mask': mask_name,
        'n_molecules': int(q_df['system_key'].nunique()) if not q_df.empty else 0,
        'n_true_edges': int(len(true_pairs)),
        'n_pred_edges': int(len(pred_pairs)),
        'precision': metrics['precision'],
        'recall': metrics['recall'],
        'f1': metrics['f1'],
        'extra_edge_rate': extra_edge_rate,
    }


def _sweep_row(model: str, subset: str, threshold: float, q_df: pd.DataFrame, pred_df: pd.DataFrame) -> dict[str, object]:
    true_pairs = _pairs_from_df(q_df)
    pred_pairs = _pairs_from_df(pred_df)
    metrics = _f1(pred_pairs, true_pairs)
    extra_edge_rate = _safe_ratio(len(pred_pairs - true_pairs), len(pred_pairs)) if pred_pairs else float('nan')
    return {
        'model': model,
        'subset': subset,
        'clearance_threshold_angstrom': float(threshold),
        'n_molecules': int(q_df['system_key'].nunique()) if not q_df.empty else 0,
        'n_true_edges': int(len(true_pairs)),
        'n_pred_edges': int(len(pred_pairs)),
        'precision': metrics['precision'],
        'recall': metrics['recall'],
        'f1': metrics['f1'],
        'extra_edge_rate': extra_edge_rate,
    }


def _distribution_row(model: str, subset: str, face_class: str, df: pd.DataFrame) -> dict[str, object]:
    values = pd.to_numeric(df['intersection_edge_min_dist'], errors='coerce').dropna().to_numpy(dtype=float)
    if values.size == 0:
        return {
            'model': model,
            'subset': subset,
            'face_class': face_class,
            'n_faces': 0,
            'mean_clearance_angstrom': float('nan'),
            'p05_clearance_angstrom': float('nan'),
            'p25_clearance_angstrom': float('nan'),
            'median_clearance_angstrom': float('nan'),
            'p75_clearance_angstrom': float('nan'),
            'p95_clearance_angstrom': float('nan'),
        }
    q05, q25, q50, q75, q95 = np.quantile(values, [0.05, 0.25, 0.50, 0.75, 0.95])
    return {
        'model': model,
        'subset': subset,
        'face_class': face_class,
        'n_faces': int(values.size),
        'mean_clearance_angstrom': float(values.mean()),
        'p05_clearance_angstrom': float(q05),
        'p25_clearance_angstrom': float(q25),
        'median_clearance_angstrom': float(q50),
        'p75_clearance_angstrom': float(q75),
        'p95_clearance_angstrom': float(q95),
    }


def _write_report(
    path: Path,
    summary: dict[str, object],
    mask_df: pd.DataFrame,
    sweep_df: pd.DataFrame,
    distribution_df: pd.DataFrame,
) -> None:
    vor_all = mask_df[
        (mask_df['model'] == 'voronoi')
        & (mask_df['subset'] == 'all')
        & (mask_df['mask'] == 'raw')
    ].iloc[0]
    vor_nonbonded = mask_df[
        (mask_df['model'] == 'voronoi')
        & (mask_df['subset'] == 'nonbonded')
        & (mask_df['mask'] == 'raw')
    ].iloc[0]
    rec_all = mask_df[
        (mask_df['model'] == 'recovered_powerfit')
        & (mask_df['subset'] == 'all')
        & (mask_df['mask'] == 'raw')
    ].iloc[0]
    rec_nonbonded = mask_df[
        (mask_df['model'] == 'recovered_powerfit')
        & (mask_df['subset'] == 'nonbonded')
        & (mask_df['mask'] == 'raw')
    ].iloc[0]

    lines = [
        '# Experiment J4b: mask transfer',
        '',
        f'- Manifest: `{summary["manifest_csv"]}`',
        f'- Reference J3 cutoff: **{summary["reference_cutoff_angstrom"]:.1f} A**',
        f'- Processed molecules: **{summary["n_processed_rows"]}**',
        f'- Skipped rows: **{summary["n_skipped_rows"]}**',
        (
            f'- Numerical sliver cleanup: visible face with clearance <= '
            f'**{summary["sliver_clearance_threshold"]:.1e} A** '
            '(clearance-only safeguard)'
        ),
        (
            '- J3 reports fixed-denominator support recovery against the common '
            '3975-edge QTAIM graph. J4b instead evaluates realized-face '
            "diagnostics within each model's realized-face archive."
        ),
        (
            f'- Archive-conditioned truth pool: Voronoi '
            f'**{int(vor_all["n_true_edges"])}** overall / '
            f'**{int(vor_nonbonded["n_true_edges"])}** nonbonded '
            'QTAIM-supported realized faces; recovered powerfit '
            f'**{int(rec_all["n_true_edges"])}** overall / '
            f'**{int(rec_nonbonded["n_true_edges"])}** nonbonded.'
        ),
        '',
        '## Overall archive-conditioned mask ladder',
        '',
    ]
    overall = mask_df[mask_df['subset'] == 'all']
    for model in ('voronoi', 'recovered_powerfit'):
        sub = overall[overall['model'] == model]
        if sub.empty:
            continue
        lines.append(f'### {model}')
        lines.append('')
        for mask_name in MASK_ORDER:
            row = sub[sub['mask'] == mask_name].iloc[0]
            mask_label = MASK_REPORT_LABELS.get(mask_name, mask_name)
            lines.append(
                f'- {mask_label}: precision / recall / F1 = **{row["precision"]:.3f} / {row["recall"]:.3f} / {row["f1"]:.3f}**, '
                f'extra-edge rate **{row["extra_edge_rate"]:.3f}**.'
            )
        lines.append('')

    bonded = mask_df[(mask_df['subset'] == 'bonded') & (mask_df['mask'] == 'visible_non_sliver')]
    nonbonded = mask_df[(mask_df['subset'] == 'nonbonded') & (mask_df['mask'] == 'visible_non_sliver')]
    if not bonded.empty and not nonbonded.empty:
        lines += [
            '## Bonded vs nonbonded after the visible numerical cleanup',
            '',
        ]
        for model in ('voronoi', 'recovered_powerfit'):
            b = bonded[bonded['model'] == model].iloc[0]
            nb = nonbonded[nonbonded['model'] == model].iloc[0]
            lines += [
                f'- {model}: bonded F1 **{b["f1"]:.3f}**, nonbonded F1 **{nb["f1"]:.3f}**.',
            ]
        lines.append('')

    lines += [
        '## Numerical-cleanup note',
        '',
        (
            f'- Near-zero-clearance faces removed on the full frozen benchmark: '
            f'Voronoi **{summary.get("n_voronoi_slivers", 0)}**, '
            f'recovered powerfit '
            f'**{summary.get("n_recovered_powerfit_slivers", 0)}**.'
        ),
        '- This safeguard is intentionally minimal. Face area is no longer part of the broad-dataset filtering story.',
        '',
        '## Clearance sweep takeaways',
        '',
    ]
    for subset in ('all', 'nonbonded', 'bonded'):
        sub = sweep_df[sweep_df['subset'] == subset]
        if sub.empty:
            continue
        for model in ('voronoi', 'recovered_powerfit'):
            m = sub[sub['model'] == model]
            if m.empty:
                continue
            best = m.loc[m['f1'].idxmax()]
            lines.append(
                f'- {model}, {subset}: best F1 on the tested sweep is **{best["f1"]:.3f}** at clearance >= **{best["clearance_threshold_angstrom"]:.2f} A** '
                f'(precision **{best["precision"]:.3f}**, recall **{best["recall"]:.3f}**).'
            )

    if 0.5 in set(float(x) for x in sweep_df['clearance_threshold_angstrom'].unique()):
        lines += [
            '',
            '## Same-threshold comparison at 0.50 A (archive-conditioned)',
            '',
        ]
        for subset in ('all', 'nonbonded', 'heteronuclear'):
            sv = sweep_df[(sweep_df['subset'] == subset) & (np.isclose(sweep_df['clearance_threshold_angstrom'], 0.5))]
            if sv.empty:
                continue
            vv = sv[sv['model'] == 'voronoi'].iloc[0]
            rv = sv[sv['model'] == 'recovered_powerfit'].iloc[0]
            lines.append(
                f'- {subset}: Voronoi F1 **{vv["f1"]:.3f}** vs recovered-powerfit F1 **{rv["f1"]:.3f}**; '
                f'precision **{vv["precision"]:.3f} -> {rv["precision"]:.3f}**, recall **{vv["recall"]:.3f} -> {rv["recall"]:.3f}**.'
            )

    lines += [
        '',
        '## Visible-face clearance distributions',
        '',
        (
            '- The sweep remains the primary transfer diagnostic. These '
            'distributions explain why it works by comparing visible realized '
            'faces split into QTAIM-supported versus surplus classes.'
        ),
        '',
    ]
    for subset in DISTRIBUTION_SUBSET_ORDER:
        lines.append(f'### {subset}')
        lines.append('')
        for model in ('voronoi', 'recovered_powerfit'):
            true_row = distribution_df[
                (distribution_df['subset'] == subset)
                & (distribution_df['model'] == model)
                & (distribution_df['face_class'] == 'qtaim_supported')
            ].iloc[0]
            extra_row = distribution_df[
                (distribution_df['subset'] == subset)
                & (distribution_df['model'] == model)
                & (distribution_df['face_class'] == 'extra')
            ].iloc[0]
            lines.append(
                f'- {model}: QTAIM-supported median clearance **{true_row["median_clearance_angstrom"]:.3f} A** '
                f'(p05/p95 **{true_row["p05_clearance_angstrom"]:.3f} / {true_row["p95_clearance_angstrom"]:.3f}**), '
                f'extra-face median **{extra_row["median_clearance_angstrom"]:.3f} A** '
                f'(p05/p95 **{extra_row["p05_clearance_angstrom"]:.3f} / {extra_row["p95_clearance_angstrom"]:.3f}**).'
            )
        lines.append('')

    lines += [
        '## Interpretation',
        '',
        '- J3 is the fixed-denominator recovery stage; J4b is the conditional realized-face diagnostic stage.',
        '- Visibility is the methane-derived transfer mask: it removes screened connector-nonvisible faces.',
        '- The near-zero-clearance cleanup is only a numerical safeguard. It is not a chemistry-specific filter and does not use face area.',
        (
            '- The clearance sweep is the adamantane-derived transfer '
            'diagnostic: it is not yet frozen as a universal rule, but it '
            'quantifies how much of the extra nonbonded tail lives in '
            'low-clearance faces.'
        ),
        (
            '- The new visible-face clearance distributions support the same '
            'point from the complementary angle: surplus realized faces are '
            'systematically left-shifted relative to QTAIM-supported faces, '
            'especially in the nonbonded regime.'
        ),
        '',
        '## Outputs',
        '',
        '- `edge_level.csv`',
        '- `mask_summary.csv`',
        '- `clearance_sweep.csv`',
        '- `clearance_distribution_summary.csv`',
        '- `molecule_level.csv`',
        '- `summary.json`',
    ]


    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _make_mask_ladder_plot(mask_df: pd.DataFrame, outpath: Path) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return

    order = list(MASK_ORDER)
    x = np.arange(len(order), dtype=float)
    width = 0.18

    fig = plt.figure(figsize=(9.5, 5.5))
    ax = fig.add_subplot(111)
    combos = [
        ('voronoi', 'all', 'Voronoi all'),
        ('recovered_powerfit', 'all', 'Recovered all'),
        ('voronoi', 'nonbonded', 'Voronoi nonbonded'),
        ('recovered_powerfit', 'nonbonded', 'Recovered nonbonded'),
    ]
    offsets = [-1.5 * width, -0.5 * width, 0.5 * width, 1.5 * width]
    for (model, subset, label), dx in zip(combos, offsets):
        vals = []
        sub = mask_df[(mask_df['model'] == model) & (mask_df['subset'] == subset)]
        for mask_name in order:
            row = sub[sub['mask'] == mask_name].iloc[0]
            vals.append(float(row['f1']))
        ax.bar(x + dx, vals, width=width, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels(order, rotation=15, ha='right')
    ax.set_ylabel('F1')
    ax.set_ylim(0.0, 1.05)
    ax.set_title('J4 mask-transfer ladder')
    ax.grid(True, axis='y', alpha=0.25)
    ax.legend(fontsize=9)
    fig.tight_layout()
    save_figure(
        fig,
        outpath,
        title=outpath.stem,
        png_dpi=220,
        save_png_sibling=True,
    )
    plt.close(fig)


def _make_clearance_sweep_plot(sweep_df: pd.DataFrame, outpath: Path) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return

    fig = plt.figure(figsize=(9.5, 5.5))
    ax = fig.add_subplot(111)
    for model, subset, label in [
        ('voronoi', 'all', 'Voronoi all'),
        ('recovered_powerfit', 'all', 'Recovered all'),
        ('voronoi', 'nonbonded', 'Voronoi nonbonded'),
        ('recovered_powerfit', 'nonbonded', 'Recovered nonbonded'),
    ]:
        sub = sweep_df[(sweep_df['model'] == model) & (sweep_df['subset'] == subset)].sort_values('clearance_threshold_angstrom')
        if sub.empty:
            continue
        ax.plot(sub['clearance_threshold_angstrom'], sub['f1'], marker='o', label=label)
    ax.set_xlabel('clearance threshold (Å)')
    ax.set_ylabel('F1 after visibility + numerical cleanup')
    ax.set_ylim(0.0, 1.05)
    ax.set_title('J4 clearance sweep')
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=9)
    fig.tight_layout()
    save_figure(
        fig,
        outpath,
        title=outpath.stem,
        png_dpi=220,
        save_png_sibling=True,
    )
    plt.close(fig)


def _make_clearance_distribution_plot(edge_df: pd.DataFrame, outpath: Path) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8), sharey=True)
    base = edge_df[edge_df['keep_visible_non_sliver'].astype(bool)].copy()
    label_map = {
        ('voronoi', 'qtaim_supported'): 'Voronoi true',
        ('voronoi', 'extra'): 'Voronoi extra',
        ('recovered_powerfit', 'qtaim_supported'): 'Recovered true',
        ('recovered_powerfit', 'extra'): 'Recovered extra',
    }
    combos = [
        ('voronoi', 'qtaim_supported'),
        ('voronoi', 'extra'),
        ('recovered_powerfit', 'qtaim_supported'),
        ('recovered_powerfit', 'extra'),
    ]
    for ax, subset in zip(axes, DISTRIBUTION_SUBSET_ORDER):
        subset_df = base[_subset_mask(base, subset)].copy()
        for model, face_class in combos:
            selector = subset_df['is_qtaim_edge'].astype(bool)
            if face_class == 'extra':
                selector = ~selector
            values = subset_df[
                (subset_df['model'] == model) & selector
            ]['intersection_edge_min_dist'].dropna().to_numpy(dtype=float)
            if values.size == 0:
                continue
            xs = np.sort(values)
            ys = np.arange(1, xs.size + 1, dtype=float) / float(xs.size)
            ax.step(xs, ys, where='post', label=label_map[(model, face_class)])
        ax.set_title(subset)
        ax.set_xlabel('connector clearance (A)')
        ax.grid(True, alpha=0.25)
    axes[0].set_ylabel('ECDF')
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    save_figure(
        fig,
        outpath,
        title=outpath.stem,
        png_dpi=220,
        save_png_sibling=True,
    )
    plt.close(fig)


def main(argv: Iterable[str] | None = None) -> int:
    args, manifest_csv, j3_selected_csv, output_dir, clearance_thresholds = parse_args(argv)
    manifest = load_manifest(manifest_csv)

    j3_df = pd.read_csv(j3_selected_csv)
    j3_df = j3_df[np.isclose(j3_df['cutoff_angstrom'].astype(float), float(args.reference_cutoff))].copy()
    if j3_df.empty:
        raise ValueError(f'No J3 recovered edges found at cutoff {args.reference_cutoff:.3f} Å in {j3_selected_csv}')

    output_dir.mkdir(parents=True, exist_ok=True)
    progress_write(f'Loaded {len(manifest)} manifest rows from {manifest_csv}')
    progress_write(f'Loaded J3 recovered edges from {j3_selected_csv} at {args.reference_cutoff:.1f} Å')
    progress_write(f'Output dir: {output_dir}')
    if not args.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')

    edge_rows: list[dict[str, object]] = []
    molecule_rows: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []

    j3_systems = set(j3_df['system_key'].astype(str).unique())
    total = len(manifest)
    manifest_iter = iter_progress(manifest, total=total, desc='J4b mask transfer', disable=args.no_progress, unit='system')
    for row in manifest_iter:
        if hasattr(manifest_iter, 'set_postfix_str'):
            manifest_iter.set_postfix_str(row.system_key)
        if not row.json_path.is_file():
            if args.require_all:
                raise FileNotFoundError(f'Missing QTAIM JSON: {row.json_path}')
            skipped_rows.append({'system_key': row.system_key, 'name': row.name, 'group': row.group, 'json_path': str(row.json_path), 'reason': 'missing_json'})
            continue
        if row.system_key not in j3_systems:
            skipped_rows.append({'system_key': row.system_key, 'name': row.name, 'group': row.group, 'json_path': str(row.json_path), 'reason': 'missing_j3_reference'})
            continue
        try:
            graph_info = _make_graph_info(row.smiles)
        except Exception as exc:
            skipped_rows.append({'system_key': row.system_key, 'name': row.name, 'group': row.group, 'json_path': str(row.json_path), 'reason': f'rdkit_error: {exc}'})
            continue
        try:
            obj = json.loads(row.json_path.read_text(encoding='utf-8'))
        except Exception as exc:
            skipped_rows.append({'system_key': row.system_key, 'name': row.name, 'group': row.group, 'json_path': str(row.json_path), 'reason': f'json_error: {exc}'})
            continue

        atom_symbols_json = [atom['element'] for atom in obj['atoms']]
        if atom_symbols_json != graph_info.atom_symbols:
            skipped_rows.append({'system_key': row.system_key, 'name': row.name, 'group': row.group, 'json_path': str(row.json_path), 'reason': 'atom_order_mismatch'})
            continue

        positions = np.array([atom['position_angstrom'] for atom in obj['atoms']], dtype=float)
        qtaim_pairs: set[tuple[int, int]] = set()
        low_offset_true_count = 0
        for edge in obj['bcp_graph']:
            i = int(edge['atom_i']) - 1
            j = int(edge['atom_j']) - 1
            pair = undirected(i, j)
            qtaim_pairs.add(pair)
        cp_by_index = {int(cp['cp_index']): cp for cp in obj['critical_points']}
        qtaim_obs: dict[tuple[int, int], dict[str, object]] = {}
        for edge in obj['bcp_graph']:
            i = int(edge['atom_i']) - 1
            j = int(edge['atom_j']) - 1
            pair = undirected(i, j)
            point_i = positions[pair[0]]
            point_j = positions[pair[1]]
            bcp = np.array(cp_by_index[int(edge['cp_index'])]['position_angstrom'], dtype=float)
            d = point_j - point_i
            dd = float(np.dot(d, d))
            t_obs = float(np.dot(bcp - point_i, d) / dd)
            offset = float(np.linalg.norm(np.cross(bcp - point_i, d)) / math.sqrt(dd))
            bond_length = float(np.linalg.norm(point_j - point_i))
            path_distance = int(round(float(graph_info.topological_distances[pair[0], pair[1]])))
            element_i = atom_symbols_json[pair[0]]
            element_j = atom_symbols_json[pair[1]]
            low_offset = offset <= float(args.low_offset_threshold)
            low_offset_true_count += int(low_offset)
            qtaim_obs[pair] = {
                't_obs': t_obs,
                'offset_angstrom': offset,
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
                'low_offset_true_edge': low_offset,
            }

        box = box_for_points(positions, margin=float(args.box_margin))
        cells, _diag = _compute_cells(positions, box, radii=None)
        vor_edges = _extract_face_rows(cells)

        def _append_model_edges(model_name: str, rows: list[dict[str, object]], *, weights: np.ndarray | None = None):
            sliver_count = 0
            raw_edge_count = len(rows)
            visible_edge_count = 0
            visible_non_sliver_count = 0
            for face in rows:
                i, j = face['pair']
                info = qtaim_obs.get(face['pair'])
                path_distance = int(round(float(graph_info.topological_distances[i, j])))
                element_i = atom_symbols_json[i]
                element_j = atom_symbols_json[j]
                is_qtaim_edge = face['pair'] in qtaim_pairs
                record = {
                    'system_key': row.system_key,
                    'name': row.name,
                    'group': row.group,
                    'model': model_name,
                    'atom_i': int(i + 1),
                    'atom_j': int(j + 1),
                    'pair_key': f'{i + 1}-{j + 1}',
                    'element_i': element_i,
                    'element_j': element_j,
                    'pair_type': '-'.join(sorted((element_i, element_j))),
                    'graph_distance': path_distance,
                    'graph_distance_bin': _distance_bin(path_distance),
                    'is_bonded': path_distance == 1,
                    'is_nonbonded': path_distance != 1,
                    'is_homonuclear': element_i == element_j,
                    'is_heteronuclear': element_i != element_j,
                    'is_qtaim_edge': bool(is_qtaim_edge),
                    'intersection_inside': bool(face['intersection_inside']),
                    'intersection_edge_min_dist': float(face['intersection_edge_min_dist']),
                    'intersection_centroid_dist': float(face['intersection_centroid_dist']),
                    'face_area': float(face['face_area']),
                    'bond_length_angstrom': float(np.linalg.norm(positions[j] - positions[i])),
                    't_obs': float(info['t_obs']) if info else float('nan'),
                    'offset_angstrom': float(info['offset_angstrom']) if info else float('nan'),
                    'low_offset_true_edge': bool(info['low_offset_true_edge']) if info else False,
                }
                if weights is not None:
                    record.update(_analytic_fields(positions, weights, box, face['pair']))
                else:
                    record.update(
                        {
                            'analytic_t': float(face.get('analytic_t', float('nan'))),
                            'analytic_sigma': float(face.get('analytic_sigma', float('nan'))),
                            'analytic_clearance_unclipped': float(face.get('analytic_clearance_unclipped', float('nan'))),
                            'analytic_box_clearance': float(face.get('analytic_box_clearance', float('nan'))),
                            'analytic_clearance_clipped': float(face.get('analytic_clearance_clipped', float('nan'))),
                            'analytic_visible_unclipped': bool(face.get('analytic_visible_unclipped', False)),
                            'analytic_visible_clipped': bool(face.get('analytic_visible_clipped', False)),
                            'analytic_margin_safe': bool(face.get('analytic_margin_safe', False)),
                        }
                    )
                is_sliver = bool(record['intersection_inside']) and (record['intersection_edge_min_dist'] <= float(args.sliver_clearance_threshold))
                record['is_numerical_sliver'] = is_sliver
                record['keep_raw'] = True
                record['keep_visible'] = bool(record['intersection_inside'])
                record['keep_visible_non_sliver'] = bool(record['intersection_inside']) and (not is_sliver)
                sliver_count += int(is_sliver)
                visible_edge_count += int(record['keep_visible'])
                visible_non_sliver_count += int(record['keep_visible_non_sliver'])
                edge_rows.append(record)
            molecule_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'model': model_name,
                'n_qtaim_edges': int(len(qtaim_pairs)),
                'n_low_offset_true_edges': int(low_offset_true_count),
                'raw_edge_count': int(raw_edge_count),
                'visible_edge_count': int(visible_edge_count),
                'visible_non_sliver_edge_count': int(visible_non_sliver_count),
                'numerical_sliver_edge_count': int(sliver_count),
            })

        _append_model_edges('voronoi', vor_edges, weights=np.zeros(len(positions), dtype=float))

        sub_j3 = j3_df[j3_df['system_key'].astype(str) == row.system_key].copy()
        if sub_j3.empty:
            skipped_rows.append({'system_key': row.system_key, 'name': row.name, 'group': row.group, 'json_path': str(row.json_path), 'reason': 'missing_j3_rows_after_filter'})
            # remove the voronoi rows we just added for fair comparison
            edge_rows[:] = [r for r in edge_rows if not (r['system_key'] == row.system_key and r['model'] == 'voronoi')]
            molecule_rows[:] = [r for r in molecule_rows if not (r['system_key'] == row.system_key and r['model'] == 'voronoi')]
            continue
        recovered_rows: list[dict[str, object]] = []
        for rec in sub_j3.to_dict(orient='records'):
            recovered_rows.append({
                'pair': undirected(int(rec['atom_i']) - 1, int(rec['atom_j']) - 1),
                'intersection_inside': bool(rec['intersection_inside']),
                'intersection_edge_min_dist': float(rec['intersection_edge_min_dist']),
                'intersection_centroid_dist': float(rec['intersection_centroid_dist']),
                'face_area': float(rec['face_area']),
                'analytic_t': float(rec.get('analytic_t_recovered', float('nan'))),
                'analytic_sigma': float(rec.get('analytic_sigma', float('nan'))),
                'analytic_clearance_unclipped': float(rec.get('analytic_clearance_unclipped', float('nan'))),
                'analytic_box_clearance': float(rec.get('analytic_box_clearance', float('nan'))),
                'analytic_clearance_clipped': float(rec.get('analytic_clearance_clipped', float('nan'))),
                'analytic_visible_unclipped': bool(rec.get('analytic_visible_unclipped', False)),
                'analytic_visible_clipped': bool(rec.get('analytic_visible_clipped', False)),
                'analytic_margin_safe': bool(rec.get('analytic_margin_safe', False)),
            })
        _append_model_edges('recovered_powerfit', recovered_rows)

    edge_df = pd.DataFrame.from_records(edge_rows)
    if edge_df.empty:
        raise ValueError('No edge rows were produced.')
    molecule_df = pd.DataFrame.from_records(molecule_rows)
    skipped_df = pd.DataFrame.from_records(skipped_rows)

    mask_rows: list[dict[str, object]] = []
    for model in ('voronoi', 'recovered_powerfit'):
        model_df = edge_df[edge_df['model'] == model].copy()
        for subset in SUBSET_ORDER:
            q_df = model_df[_subset_mask(model_df, subset) & model_df['is_qtaim_edge'].astype(bool)].copy()
            base = model_df[_subset_mask(model_df, subset)].copy()
            for mask_name in MASK_ORDER:
                pred = base[_mask_selector(base, mask_name)].copy()
                mask_rows.append(_summary_row(model, subset, mask_name, q_df, pred))
    mask_summary_df = pd.DataFrame.from_records(mask_rows)

    sweep_rows: list[dict[str, object]] = []
    for model in ('voronoi', 'recovered_powerfit'):
        model_df = edge_df[edge_df['model'] == model].copy()
        for subset in SUBSET_ORDER:
            q_df = model_df[_subset_mask(model_df, subset) & model_df['is_qtaim_edge'].astype(bool)].copy()
            base = model_df[_subset_mask(model_df, subset) & model_df['intersection_inside'].astype(bool) & (~model_df['is_numerical_sliver'].astype(bool))].copy()
            for thr in clearance_thresholds:
                pred = base[base['intersection_edge_min_dist'] >= float(thr)].copy()
                sweep_rows.append(_sweep_row(model, subset, float(thr), q_df, pred))
    clearance_sweep_df = pd.DataFrame.from_records(sweep_rows)

    distribution_rows: list[dict[str, object]] = []
    visible_base = edge_df[edge_df['keep_visible_non_sliver'].astype(bool)].copy()
    for model in ('voronoi', 'recovered_powerfit'):
        model_df = visible_base[visible_base['model'] == model].copy()
        for subset in DISTRIBUTION_SUBSET_ORDER:
            subset_df = model_df[_subset_mask(model_df, subset)].copy()
            distribution_rows.append(
                _distribution_row(
                    model,
                    subset,
                    'qtaim_supported',
                    subset_df[subset_df['is_qtaim_edge'].astype(bool)].copy(),
                )
            )
            distribution_rows.append(
                _distribution_row(
                    model,
                    subset,
                    'extra',
                    subset_df[~subset_df['is_qtaim_edge'].astype(bool)].copy(),
                )
            )
    clearance_distribution_df = pd.DataFrame.from_records(distribution_rows)

    summary = {
        'manifest_csv': _display_path(manifest_csv),
        'j3_selected_csv': _display_path(j3_selected_csv),
        'reference_cutoff_angstrom': float(args.reference_cutoff),
        'output_dir': _display_path(output_dir),
        'n_manifest_rows': len(manifest),
        'n_processed_rows': int(edge_df[['system_key']].drop_duplicates().shape[0]),
        'n_skipped_rows': int(len(skipped_df)),
        'box_margin_angstrom': float(args.box_margin),
        'low_offset_threshold_angstrom': float(args.low_offset_threshold),
        'sliver_clearance_threshold': float(args.sliver_clearance_threshold),
        'clearance_thresholds_angstrom': [float(x) for x in clearance_thresholds],
        'n_voronoi_slivers': int(edge_df[(edge_df['model'] == 'voronoi') & edge_df['is_numerical_sliver']].shape[0]),
        'n_recovered_powerfit_slivers': int(edge_df[(edge_df['model'] == 'recovered_powerfit') & edge_df['is_numerical_sliver']].shape[0]),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    edge_df.to_csv(output_dir / 'edge_level.csv', index=False)
    mask_summary_df.to_csv(output_dir / 'mask_summary.csv', index=False)
    clearance_sweep_df.to_csv(output_dir / 'clearance_sweep.csv', index=False)
    clearance_distribution_df.to_csv(output_dir / 'clearance_distribution_summary.csv', index=False)
    molecule_df.to_csv(output_dir / 'molecule_level.csv', index=False)
    skipped_df.to_csv(output_dir / 'skipped_rows.csv', index=False)
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    _write_report(
        output_dir / 'REPORT.md',
        summary,
        mask_summary_df,
        clearance_sweep_df,
        clearance_distribution_df,
    )

    if not args.no_plots:
        fig_dir = output_dir / 'figures'
        fig_dir.mkdir(parents=True, exist_ok=True)
        _make_mask_ladder_plot(mask_summary_df, fig_dir / 'mask_ladder_f1.pdf')
        _make_clearance_sweep_plot(clearance_sweep_df, fig_dir / 'clearance_sweep_f1.pdf')
        _make_clearance_distribution_plot(edge_df, fig_dir / 'clearance_distribution_ecdf.pdf')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
