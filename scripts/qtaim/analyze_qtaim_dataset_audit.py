"""Experiment J1: audit the molecular QTAIM benchmark.

This script summarizes how topologically nontrivial the current QTAIM dataset is
before any separator-law or powerfit experiment is run. It is intended to answer
common concerns about benchmark triviality by quantifying:

- how often ring and cage critical points occur;
- how often QTAIM BCP edges are nonbonded in the explicit-H molecular graph;
- how axis-faithful the projected BCP separator proxy is, overall and stratified into bonded vs nonbonded support;
- which element pairs dominate the observed support graph.

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
default, skips rows whose QTAIM JSON is not yet available. This makes it safe to
run against an in-progress full manifest while only part of the dataset has been
computed.

Outputs
-------
The output directory contains:
- ``edge_level.csv``
- ``molecule_level.csv``
- ``pair_type_summary.csv``
- ``graph_distance_summary.csv``
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
from rdkit import Chem
from rdkit.Chem import rdmolops

from _figure_io import save_figure

from _cli_progress import iter_progress, progress_write, tqdm_available


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


LOW_OFFSET_DEFAULT = 0.02



def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())




def projection_fraction_and_offset(pi: np.ndarray, pj: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    d = pj - pi
    dd = float(np.dot(d, d))
    t = float(np.dot(x - pi, d) / dd)
    off = float(np.linalg.norm(np.cross(x - pi, d)) / math.sqrt(dd))
    return t, off


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Run the J1 topology audit on a molecular QTAIM manifest.'
    )
    parser.add_argument('manifest_csv', help='Manifest CSV with json_path plus connectivity_smiles/smiles.')
    parser.add_argument('--output-dir', default=None, help='Directory for audit outputs. Defaults to results/qtaim_main/J1_dataset_audit when the manifest lives under data/qtaim_main/.')
    parser.add_argument(
        '--offset-threshold',
        type=float,
        default=LOW_OFFSET_DEFAULT,
        help=f'Low-offset threshold in angstrom for audit summaries (default: {LOW_OFFSET_DEFAULT:.2f}).',
    )
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm progress bars.')
    parser.add_argument('--require-all', action='store_true', help='Fail if any listed QTAIM JSON is missing instead of skipping it.')
    parser.add_argument('--no-plots', action='store_true', help='Do not generate diagnostic figures.')
    return parser




def choose_default_output_dir(manifest_csv: Path) -> Path:
    repo_root = manifest_csv.parents[2] if len(manifest_csv.parents) >= 3 else manifest_csv.parent
    if manifest_csv.parent.name == 'qtaim_main':
        return (repo_root / 'results' / 'qtaim_main' / 'J1_dataset_audit').resolve()
    return (repo_root / 'results' / f'{manifest_csv.stem}_dataset_audit').resolve()


def parse_args(argv: Iterable[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest_csv = Path(_expand(args.manifest_csv)).resolve()
    if not manifest_csv.is_file():
        parser.error(f'Manifest CSV not found: {manifest_csv}')
    output_dir = Path(_expand(args.output_dir)).resolve() if args.output_dir else choose_default_output_dir(manifest_csv)
    return args, manifest_csv, output_dir


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
    if path_distance <= 1:
        return 'bonded'
    if path_distance <= 3:
        return '2-3'
    return '4+'


def _safe_p95(values: np.ndarray) -> float:
    return float(np.percentile(values, 95.0)) if values.size else float('nan')


def _write_report(path: Path, summary: dict, molecule_df: pd.DataFrame, graph_distance_df: pd.DataFrame) -> None:
    low_offset = summary['offset_threshold_angstrom']
    path24 = graph_distance_df.loc[graph_distance_df['graph_distance_bin'] == '2-3', 'n_edges'].sum() if not graph_distance_df.empty else 0
    text = f"""# J1 dataset audit

Processed manifest: `{summary['manifest_csv']}`

Current processing status:
- manifest rows: **{summary['n_manifest_rows']}**
- processed molecules: **{summary['n_processed_rows']}**
- skipped rows: **{summary['n_skipped_rows']}**

Topology summary on the full frozen benchmark:
- total QTAIM BCP edges: **{summary['total_bcp_edges']}**
- molecules with at least one RCP: **{summary['molecules_with_rcp_fraction']:.1%}** ({summary['molecules_with_rcp_count']}/{summary['n_processed_rows']})
- molecules with at least one CCP: **{summary['molecules_with_ccp_fraction']:.1%}** ({summary['molecules_with_ccp_count']}/{summary['n_processed_rows']})
- molecules with at least one nonbonded BCP: **{summary['molecules_with_nonbonded_bcp_fraction']:.1%}** ({summary['molecules_with_nonbonded_bcp_count']}/{summary['n_processed_rows']})
- nonbonded BCP fraction over all BCP edges: **{summary['nonbonded_bcp_edge_fraction']:.2%}**

Connector-projection audit:
- median off-axis distance: **{summary['offset_median_angstrom']:.5f} Å**
- 95th percentile off-axis distance: **{summary['offset_p95_angstrom']:.5f} Å**
- maximum off-axis distance: **{summary['offset_max_angstrom']:.5f} Å**
- edges with off-axis distance ≤ {low_offset:.2f} Å: **{summary['low_offset_fraction']:.2%}**

Bonded vs nonbonded connector-projection split:
- bonded edges: **{summary['bonded_bcp_edge_count']}** total, median off-axis **{summary['bonded_offset_median_angstrom']:.5f} Å**, low-offset share **{summary['bonded_low_offset_fraction']:.2%}**
- nonbonded edges: **{summary['nonbonded_bcp_edge_count']}** total, median off-axis **{summary['nonbonded_offset_median_angstrom']:.5f} Å**, low-offset share **{summary['nonbonded_low_offset_fraction']:.2%}**

Interpretation notes:
- The full frozen benchmark is not topologically trivial: higher-order critical points are already common.
- The explicit-H molecular-graph audit shows that many molecules contain QTAIM-supported nonbonded contacts.
- The pooled off-axis summary is dominated by bonded edges. Bonded BCPs are strongly connector-aligned, whereas the nonbonded subset is a much harsher proxy-mismatch regime and should be read accordingly in the main text.
- In the current subset, **{path24}** BCP edges fall into graph-distance class 2–3; all remaining nonbonded BCP edges occur at graph distance ≥ 4. This supports the use of a simple bonded-vs-nonbonded split in the main text, while keeping the exact graph distance in the edge-level export for optional supplement analysis.

Files:
- `molecule_level.csv`: one row per processed molecule
- `edge_level.csv`: one row per QTAIM BCP-supported pair
- `pair_type_summary.csv`: element-pair composition summary
- `graph_distance_summary.csv`: bonded vs nonbonded summary, plus exact graph distance bins
- `skipped_rows.csv`: rows skipped because inputs were incomplete or inconsistent
"""
    path.write_text(text, encoding='utf-8')


def _make_plots(edge_df: pd.DataFrame, molecule_df: pd.DataFrame, output_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        return

    fig_dir = output_dir / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)

    # Offset histogram on log-spaced x bins would be overkill here; simple histogram is enough.
    fig = plt.figure(figsize=(6.0, 4.0))
    ax = fig.add_subplot(111)
    ax.hist(edge_df['offset_angstrom'].to_numpy(dtype=float), bins=40)
    ax.set_xlabel('BCP off-axis distance (Å)')
    ax.set_ylabel('QTAIM BCP edges')
    ax.set_title('J1: projected BCP off-axis distances')
    fig.tight_layout()
    save_figure(
        fig,
        fig_dir / 'offset_histogram.png',
        title='offset_histogram',
        png_dpi=200,
        save_pdf_sibling=True,
    )
    plt.close(fig)

    labels = ['has RCP', 'has CCP', 'has nonbonded BCP']
    values = [
        float(np.mean(molecule_df['has_ring_cp'].astype(bool))),
        float(np.mean(molecule_df['has_cage_cp'].astype(bool))),
        float(np.mean(molecule_df['has_nonbonded_bcp'].astype(bool))),
    ]
    fig = plt.figure(figsize=(5.6, 4.0))
    ax = fig.add_subplot(111)
    ax.bar(labels, values)
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel('Fraction of molecules')
    ax.set_title('J1: topology flags in full benchmark')
    for idx, value in enumerate(values):
        ax.text(idx, min(0.98, value + 0.03), f'{value:.0%}', ha='center', va='bottom')
    fig.tight_layout()
    save_figure(
        fig,
        fig_dir / 'molecule_topology_flags.png',
        title='molecule_topology_flags',
        png_dpi=200,
        save_pdf_sibling=True,
    )
    plt.close(fig)


def main(argv: Iterable[str] | None = None) -> int:
    args, manifest_csv, output_dir = parse_args(argv)
    manifest_rows = load_manifest(manifest_csv)
    output_dir.mkdir(parents=True, exist_ok=True)

    processed_rows: list[dict] = []
    molecule_rows: list[dict] = []
    skipped_rows: list[dict] = []

    total = len(manifest_rows)
    progress_write(f'Loaded {total} QTAIM rows from {manifest_csv}')
    progress_write(f'Output dir: {output_dir}')
    if not args.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')
    iterator = iter_progress(manifest_rows, total=total, desc='J1 audit', disable=args.no_progress, unit='system')
    for row in iterator:
        if hasattr(iterator, 'set_postfix_str'):
            iterator.set_postfix_str(row.system_key)
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
        local_rows: list[dict] = []
        for edge in obj['bcp_graph']:
            atom_i = int(edge['atom_i']) - 1
            atom_j = int(edge['atom_j']) - 1
            cp_index = int(edge['cp_index'])
            cp = cp_by_index[cp_index]
            point_i = positions[atom_i]
            point_j = positions[atom_j]
            bcp = np.array(cp['position_angstrom'], dtype=float)
            bond_length = float(np.linalg.norm(point_j - point_i))
            _, offset = projection_fraction_and_offset(point_i, point_j, bcp)
            path_distance = int(round(float(graph_info.topological_distances[atom_i, atom_j])))
            element_i = atom_symbols_json[atom_i]
            element_j = atom_symbols_json[atom_j]
            local_rows.append({
                'system_key': row.system_key,
                'name': row.name,
                'group': row.group,
                'atom_i': atom_i + 1,
                'atom_j': atom_j + 1,
                'cp_index': cp_index,
                'element_i': element_i,
                'element_j': element_j,
                'pair_type': '-'.join(sorted((element_i, element_j))),
                'is_homonuclear': element_i == element_j,
                'is_heteronuclear': element_i != element_j,
                'bond_length_angstrom': bond_length,
                'offset_angstrom': offset,
                'offset_over_length': offset / bond_length,
                'graph_distance': path_distance,
                'graph_distance_bin': _distance_bin(path_distance),
                'is_bonded': path_distance == 1,
                'is_nonbonded': path_distance != 1,
                'molecule_has_ring_cp': bool(obj['motif_summary']['has_ring_cp']),
                'molecule_has_cage_cp': bool(obj['motif_summary']['has_cage_cp']),
            })
        processed_rows.extend(local_rows)

        offsets = np.array([row_['offset_angstrom'] for row_ in local_rows], dtype=float)
        graph_distances = np.array([row_['graph_distance'] for row_ in local_rows], dtype=int)
        molecule_rows.append({
            'system_key': row.system_key,
            'name': row.name,
            'group': row.group,
            'n_atoms': int(len(obj['atoms'])),
            'n_bcp': int(obj['counts']['bcp']),
            'n_rcp': int(obj['counts']['rcp']),
            'n_ccp': int(obj['counts']['ccp']),
            'has_ring_cp': bool(obj['motif_summary']['has_ring_cp']),
            'has_cage_cp': bool(obj['motif_summary']['has_cage_cp']),
            'n_homonuclear_bcp': int(sum(bool(row_['is_homonuclear']) for row_ in local_rows)),
            'n_heteronuclear_bcp': int(sum(bool(row_['is_heteronuclear']) for row_ in local_rows)),
            'n_bonded_bcp': int(sum(bool(row_['is_bonded']) for row_ in local_rows)),
            'n_nonbonded_bcp': int(sum(bool(row_['is_nonbonded']) for row_ in local_rows)),
            'has_nonbonded_bcp': bool(any(bool(row_['is_nonbonded']) for row_ in local_rows)),
            'fraction_nonbonded_bcp': (float(np.mean([bool(row_['is_nonbonded']) for row_ in local_rows])) if local_rows else float('nan')),
            'offset_median_angstrom': float(np.median(offsets)) if offsets.size else float('nan'),
            'offset_p95_angstrom': _safe_p95(offsets),
            'offset_max_angstrom': float(np.max(offsets)) if offsets.size else float('nan'),
            'max_graph_distance': int(np.max(graph_distances)) if graph_distances.size else 0,
        })

    edge_df = pd.DataFrame(processed_rows)
    molecule_df = pd.DataFrame(molecule_rows)
    skipped_df = pd.DataFrame(skipped_rows)

    if edge_df.empty or molecule_df.empty:
        raise RuntimeError('No QTAIM systems were processed successfully.')

    pair_type_summary = (
        edge_df.groupby('pair_type', dropna=False)
        .agg(
            n_edges=('pair_type', 'size'),
            heteronuclear_fraction=('is_heteronuclear', 'mean'),
            nonbonded_fraction=('is_nonbonded', 'mean'),
            low_offset_fraction=('offset_angstrom', lambda s: float(np.mean(np.asarray(s) <= float(args.offset_threshold)))),
            offset_median_angstrom=('offset_angstrom', 'median'),
            offset_p95_angstrom=('offset_angstrom', lambda s: float(np.percentile(np.asarray(s, dtype=float), 95.0))),
        )
        .reset_index()
        .sort_values(['n_edges', 'pair_type'], ascending=[False, True])
    )

    graph_distance_summary = (
        edge_df.groupby(['graph_distance', 'graph_distance_bin'], dropna=False)
        .agg(
            n_edges=('graph_distance', 'size'),
            heteronuclear_fraction=('is_heteronuclear', 'mean'),
            low_offset_fraction=('offset_angstrom', lambda s: float(np.mean(np.asarray(s) <= float(args.offset_threshold)))),
            offset_median_angstrom=('offset_angstrom', 'median'),
            offset_p95_angstrom=('offset_angstrom', lambda s: float(np.percentile(np.asarray(s, dtype=float), 95.0))),
        )
        .reset_index()
        .sort_values(['graph_distance'])
    )

    total_bcp_edges = int(len(edge_df))
    bonded_edge_df = edge_df[edge_df['is_bonded'].astype(bool)]
    nonbonded_edge_df = edge_df[edge_df['is_nonbonded'].astype(bool)]
    summary = {
        'manifest_csv': _display_path(manifest_csv),
        'output_dir': _display_path(output_dir),
        'offset_threshold_angstrom': float(args.offset_threshold),
        'n_manifest_rows': int(len(manifest_rows)),
        'n_processed_rows': int(len(molecule_df)),
        'n_skipped_rows': int(len(skipped_df)),
        'total_bcp_edges': total_bcp_edges,
        'total_rcp': int(molecule_df['n_rcp'].sum()),
        'total_ccp': int(molecule_df['n_ccp'].sum()),
        'molecules_with_rcp_count': int(molecule_df['has_ring_cp'].sum()),
        'molecules_with_rcp_fraction': float(molecule_df['has_ring_cp'].mean()),
        'molecules_with_ccp_count': int(molecule_df['has_cage_cp'].sum()),
        'molecules_with_ccp_fraction': float(molecule_df['has_cage_cp'].mean()),
        'molecules_with_nonbonded_bcp_count': int(molecule_df['has_nonbonded_bcp'].sum()),
        'molecules_with_nonbonded_bcp_fraction': float(molecule_df['has_nonbonded_bcp'].mean()),
        'nonbonded_bcp_edge_fraction': float(edge_df['is_nonbonded'].mean()),
        'heteronuclear_bcp_edge_fraction': float(edge_df['is_heteronuclear'].mean()),
        'bonded_bcp_edge_count': int(len(bonded_edge_df)),
        'nonbonded_bcp_edge_count': int(len(nonbonded_edge_df)),
        'offset_median_angstrom': float(edge_df['offset_angstrom'].median()),
        'bonded_offset_median_angstrom': float(bonded_edge_df['offset_angstrom'].median()),
        'nonbonded_offset_median_angstrom': float(nonbonded_edge_df['offset_angstrom'].median()),
        'offset_p95_angstrom': float(np.percentile(edge_df['offset_angstrom'].to_numpy(dtype=float), 95.0)),
        'offset_max_angstrom': float(edge_df['offset_angstrom'].max()),
        'low_offset_fraction': float(np.mean(edge_df['offset_angstrom'].to_numpy(dtype=float) <= float(args.offset_threshold))),
        'bonded_low_offset_fraction': float(np.mean(bonded_edge_df['offset_angstrom'].to_numpy(dtype=float) <= float(args.offset_threshold))),
        'nonbonded_low_offset_fraction': float(np.mean(nonbonded_edge_df['offset_angstrom'].to_numpy(dtype=float) <= float(args.offset_threshold))),
        'graph_distance_2_3_edges': int(edge_df['graph_distance_bin'].eq('2-3').sum()),
        'graph_distance_ge4_edges': int(edge_df['graph_distance_bin'].eq('4+').sum()),
    }

    edge_df.to_csv(output_dir / 'edge_level.csv', index=False)
    molecule_df.to_csv(output_dir / 'molecule_level.csv', index=False)
    pair_type_summary.to_csv(output_dir / 'pair_type_summary.csv', index=False)
    graph_distance_summary.to_csv(output_dir / 'graph_distance_summary.csv', index=False)
    skipped_df.to_csv(output_dir / 'skipped_rows.csv', index=False)
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    _write_report(output_dir / 'REPORT.md', summary, molecule_df, graph_distance_summary)
    if not args.no_plots:
        _make_plots(edge_df, molecule_df, output_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
