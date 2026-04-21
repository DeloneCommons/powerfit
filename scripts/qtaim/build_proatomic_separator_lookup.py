"""Build the frozen proatomic separator lookup table from radial density data.

This stage tabulates the local two-atom separator law on a fixed distance grid
for all supported element pairs. The script already supported progress bars;
this header simply documents its role in the QTAIM workflow.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover
    tqdm = None

from _proatomic_pairlaw import PairLawRecord, load_radial_density_table, write_lookup_csv, write_metadata_json


def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw))


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected a positive float, got {value!r}') from exc
    if parsed <= 0.0:
        raise argparse.ArgumentTypeError(f'Expected a positive float, got {value!r}')
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Build a proatomic pair-law lookup table from the aggregated radial-density grid. '
            'The lookup stores the promolecule-density minimum along the internuclear segment '
            'for every ordered element pair on a fixed distance grid.'
        )
    )
    parser.add_argument(
        '--radial-density-grid',
        default=None,
        help='Input radial density CSV. Defaults to data/proatomic/radial/radial_density_grid.csv.',
    )
    parser.add_argument(
        '--lookup-csv',
        default=None,
        help='Output lookup CSV. Defaults to data/proatomic/pairlaw/separator_lookup.csv.',
    )
    parser.add_argument(
        '--meta-json',
        default=None,
        help='Output metadata JSON. Defaults to data/proatomic/pairlaw/separator_lookup.meta.json.',
    )
    parser.add_argument('--distance-min-angstrom', type=_positive_float, default=0.50, help='Minimum internuclear distance in angstrom (default: 0.50).')
    parser.add_argument('--distance-max-angstrom', type=_positive_float, default=5.00, help='Maximum internuclear distance in angstrom (default: 5.00).')
    parser.add_argument('--distance-step-angstrom', type=_positive_float, default=0.01, help='Distance grid step in angstrom (default: 0.01).')
    parser.add_argument('--xatol', type=_positive_float, default=1.0e-6, help='Minimizer tolerance in angstrom (default: 1e-6).')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing lookup outputs.')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm progress bars.')
    return parser


def parse_args(argv: Iterable[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    proatomic_root = repo_root / 'data' / 'proatomic'
    radial_density_grid = Path(_expand(args.radial_density_grid)).resolve() if args.radial_density_grid else (proatomic_root / 'radial' / 'radial_density_grid.csv').resolve()
    lookup_csv = Path(_expand(args.lookup_csv)).resolve() if args.lookup_csv else (proatomic_root / 'pairlaw' / 'separator_lookup.csv').resolve()
    meta_json = Path(_expand(args.meta_json)).resolve() if args.meta_json else (proatomic_root / 'pairlaw' / 'separator_lookup.meta.json').resolve()
    if not radial_density_grid.is_file():
        parser.error(f'Radial density grid not found: {radial_density_grid}')
    if args.distance_max_angstrom <= args.distance_min_angstrom:
        parser.error('--distance-max-angstrom must be greater than --distance-min-angstrom')
    if not args.overwrite:
        for candidate in (lookup_csv, meta_json):
            if candidate.exists():
                parser.error(f'Output exists, pass --overwrite to replace it: {candidate}')
    return args, radial_density_grid, lookup_csv, meta_json


def _iter_rows_with_progress(rows, use_progress: bool, total: int, desc: str):
    if use_progress and tqdm is not None:
        return tqdm(rows, total=total, desc=desc)
    return rows


def main(argv: Iterable[str] | None = None) -> int:
    args, radial_density_grid, lookup_csv, meta_json = parse_args(argv)
    print(f'[pairlaw] loading radial densities from {radial_density_grid}')
    table = load_radial_density_table(radial_density_grid)

    distances = np.arange(
        float(args.distance_min_angstrom),
        float(args.distance_max_angstrom) + 0.5 * float(args.distance_step_angstrom),
        float(args.distance_step_angstrom),
        dtype=float,
    )
    elements = list(table.elements)
    total_jobs = len(elements) * len(elements) * len(distances)
    rows: list[PairLawRecord] = []

    job_iter = (
        (element_i, element_j, float(distance_angstrom))
        for element_i in elements
        for element_j in elements
        for distance_angstrom in distances
    )
    for element_i, element_j, distance_angstrom in _iter_rows_with_progress(
        job_iter,
        use_progress=not args.no_progress,
        total=total_jobs,
        desc='pair-law grid',
    ):
        rows.append(
            table.minimum_between_atoms(
                element_i,
                element_j,
                distance_angstrom,
                xatol=float(args.xatol),
            )
        )

    print(f'[pairlaw] writing {len(rows)} rows to {lookup_csv}')
    write_lookup_csv(rows, lookup_csv)

    meta_payload = {
        'mode': 'promolecule_density_minimum',
        'distance_grid': {
            'units': 'angstrom',
            'min': float(distances[0]),
            'max': float(distances[-1]),
            'step': float(args.distance_step_angstrom),
            'n_points': int(len(distances)),
        },
        'elements': elements,
        'ordered_pairs': int(len(elements) * len(elements)),
        'rows_written': int(len(rows)),
        'solver': {
            'method': 'scipy.optimize.minimize_scalar(method="bounded")',
            'xatol_angstrom': float(args.xatol),
        },
        'source_radial_density_grid': str(radial_density_grid),
    }
    radial_meta_path = radial_density_grid.parent / 'radial_density_meta.json'
    if radial_meta_path.is_file():
        try:
            meta_payload['source_radial_density_meta'] = json.loads(radial_meta_path.read_text(encoding='utf-8'))
        except Exception:
            meta_payload['source_radial_density_meta_path'] = str(radial_meta_path)
    write_metadata_json(meta_payload, meta_json)
    print(f'[pairlaw] metadata written to {meta_json}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
