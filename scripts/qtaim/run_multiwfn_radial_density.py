"""Run project-specific Multiwfn radial-density exports for proatomic atoms.

This script drives the fixed Multiwfn radial-distribution workflow used for the
proatomic baseline, captures raw outputs per atom, and aggregates the exported
RDF and spherically averaged density tables. Added terminal progress reporting
does not change any CSV or raw-output artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from _cli_progress import iter_progress, progress_write, tqdm_available

BOHR_TO_ANGSTROM = 0.529177210903
ANGSTROM_TO_BOHR = 1.0 / BOHR_TO_ANGSTROM
VERSION_RE = re.compile(r'Version\s+(?P<version>[0-9][0-9A-Za-z.+_-]*)')
RDF_EXPORT_RE = re.compile(r'The result has been output to RDF\.txt in current folder')
SPHAVG_EXPORT_RE = re.compile(r'The result has been output to sphavgval\.txt in current folder')


def _expand(raw: str) -> str:
    return os.path.expandvars(os.path.expanduser(raw))


def _csv_path(base_dir: Path, raw: str) -> Path:
    candidate = Path(_expand(raw))
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def _portable_path(path: Path, base_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return os.path.relpath(resolved, start=base_dir.resolve())
    except ValueError:
        return str(resolved)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected a positive integer, got {value!r}') from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(f'Expected a positive integer, got {value!r}')
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected a positive float, got {value!r}') from exc
    if parsed <= 0.0:
        raise argparse.ArgumentTypeError(f'Expected a positive float, got {value!r}')
    return parsed


@dataclass(frozen=True)
class ManifestRow:
    species_label: str
    element: str
    molden_path: Path
    basis: str | None
    xc: str | None
    charge: int | None
    multiplicity: int | None
    notes: str | None
    raw_row: dict[str, str]


@dataclass(frozen=True)
class CliConfig:
    manifest_csv: Path
    multiwfn_binary: Path
    raw_root: Path
    rdf_grid_path: Path
    radial_density_grid_path: Path
    meta_path: Path
    summary_path: Path
    error_log: Path
    rmax_angstrom: float
    n_radial_points: int
    n_shell_points: int
    nproc: int
    overwrite: bool
    omp_stacksize: str
    timeout_sec: int
    no_progress: bool


def _pick_label(row: dict[str, str], default_stem: str, row_index: int) -> str:
    for key in ('species_key', 'system_key', 'label', 'name', 'element'):
        value = (row.get(key) or '').strip()
        if value:
            return value.replace(' ', '_')
    if default_stem:
        return default_stem
    return f'row_{row_index}'


_REQUIRED_COLUMNS = {'element', 'molden_path'}


def load_manifest(manifest_csv: Path) -> list[ManifestRow]:
    base_dir = manifest_csv.parent
    with manifest_csv.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = _REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError('Manifest is missing required columns: ' + ', '.join(sorted(missing)))

        rows: list[ManifestRow] = []
        for idx, raw_row in enumerate(reader, start=2):
            if not any((value or '').strip() for value in raw_row.values()):
                continue
            molden_path = _csv_path(base_dir, raw_row['molden_path'].strip())
            label = _pick_label(raw_row, molden_path.stem, idx)
            charge_text = (raw_row.get('charge') or '').strip()
            multiplicity_text = (raw_row.get('multiplicity') or '').strip()
            rows.append(
                ManifestRow(
                    species_label=label,
                    element=(raw_row.get('element') or '').strip(),
                    molden_path=molden_path,
                    basis=(raw_row.get('basis') or '').strip() or None,
                    xc=(raw_row.get('xc') or '').strip() or None,
                    charge=int(charge_text) if charge_text else None,
                    multiplicity=int(multiplicity_text) if multiplicity_text else None,
                    notes=(raw_row.get('notes') or '').strip() or None,
                    raw_row={k: (v or '') for k, v in raw_row.items()},
                )
            )
    if not rows:
        raise ValueError(f'No data rows found in manifest: {manifest_csv}')
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Project-specific Multiwfn runner for isolated-atom radial electron-density data. '
            'Reads a proatomic manifest, exports both RDF.txt and sphavgval.txt for each atom, '
            'then aggregates them into CSV grids.'
        )
    )
    parser.add_argument('manifest_csv', help='Path to the proatomic manifest CSV.')
    parser.add_argument(
        '--multiwfn-binary',
        default=None,
        help='Path to Multiwfn_noGUI. Defaults to external_software/Multiwfn_noGUI in the repo.',
    )
    parser.add_argument(
        '--raw-root',
        default=None,
        help='Directory where per-species raw Multiwfn outputs will be stored. Defaults to data/proatomic/radial/raw/.',
    )
    parser.add_argument(
        '--rdf-grid-path',
        default=None,
        help='Output CSV for aggregated RDF values. Defaults to data/proatomic/radial/rdf_grid.csv.',
    )
    parser.add_argument(
        '--radial-density-grid-path',
        default=None,
        help='Output CSV for aggregated spherically averaged density. Defaults to data/proatomic/radial/radial_density_grid.csv.',
    )
    parser.add_argument(
        '--meta-path',
        default=None,
        help='Output JSON metadata path. Defaults to data/proatomic/radial/radial_density_meta.json.',
    )
    parser.add_argument('--summary-path', help='Optional output CSV summary path. Defaults next to the manifest.')
    parser.add_argument('--error-log', help='Optional error log path. Defaults next to the manifest.')
    parser.add_argument('--rmax-angstrom', type=_positive_float, default=5.0, help='Upper radial limit in Angstrom (default: 5.0).')
    parser.add_argument('--n-radial-points', type=_positive_int, default=501, help='Number of radial points (default: 501).')
    parser.add_argument('--n-shell-points', type=_positive_int, default=2030, help='Number of integration points in each shell (default: 2030).')
    parser.add_argument('--nproc', type=_positive_int, default=1, help='Number of threads to request for Multiwfn.')
    parser.add_argument('--omp-stacksize', default='512M', help='OMP_STACKSIZE passed to Multiwfn (default: 512M).')
    parser.add_argument('--timeout-sec', type=_positive_int, default=600, help='Per-species timeout in seconds (default: 600).')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing aggregated outputs and raw files.')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm/text progress output.')
    return parser


def parse_args(argv: Iterable[str] | None = None) -> CliConfig:
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest_csv = Path(_expand(args.manifest_csv)).resolve()
    if not manifest_csv.is_file():
        parser.error(f'Manifest CSV not found: {manifest_csv}')
    repo_root = Path(__file__).resolve().parents[2]
    multiwfn_binary = Path(_expand(args.multiwfn_binary)).resolve() if args.multiwfn_binary else (repo_root / 'external_software' / 'Multiwfn_noGUI').resolve()
    if not multiwfn_binary.is_file():
        parser.error(f'Multiwfn binary not found: {multiwfn_binary}')
    proatomic_root = manifest_csv.parent
    radial_dir = proatomic_root / 'radial'
    raw_root = Path(_expand(args.raw_root)).resolve() if args.raw_root else (radial_dir / 'raw').resolve()
    rdf_grid_path = Path(_expand(args.rdf_grid_path)).resolve() if args.rdf_grid_path else (radial_dir / 'rdf_grid.csv').resolve()
    radial_density_grid_path = Path(_expand(args.radial_density_grid_path)).resolve() if args.radial_density_grid_path else (radial_dir / 'radial_density_grid.csv').resolve()
    meta_path = Path(_expand(args.meta_path)).resolve() if args.meta_path else (radial_dir / 'radial_density_meta.json').resolve()
    summary_path = Path(_expand(args.summary_path)).resolve() if args.summary_path else (proatomic_root / 'multiwfn_radial_run_summary.csv').resolve()
    error_log = Path(_expand(args.error_log)).resolve() if args.error_log else (proatomic_root / 'multiwfn_radial_errors.log').resolve()
    return CliConfig(
        manifest_csv=manifest_csv,
        multiwfn_binary=multiwfn_binary,
        raw_root=raw_root,
        rdf_grid_path=rdf_grid_path,
        radial_density_grid_path=radial_density_grid_path,
        meta_path=meta_path,
        summary_path=summary_path,
        error_log=error_log,
        rmax_angstrom=args.rmax_angstrom,
        n_radial_points=args.n_radial_points,
        n_shell_points=args.n_shell_points,
        nproc=args.nproc,
        overwrite=bool(args.overwrite),
        omp_stacksize=args.omp_stacksize,
        timeout_sec=args.timeout_sec,
        no_progress=bool(args.no_progress),
    )


def _write_summary_header_if_needed(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([
            'species_label',
            'status',
            'element',
            'molden_path',
            'raw_dir',
            'multiwfn_version',
            'rmax_angstrom',
            'n_radial_points',
            'n_shell_points',
            'rdf_path',
            'sphavg_path',
            'message',
        ])


def append_summary(path: Path, row: list[object]) -> None:
    _write_summary_header_if_needed(path)
    with path.open('a', encoding='utf-8', newline='') as handle:
        csv.writer(handle).writerow(row)


def append_error(error_log: Path, species_label: str, exc: BaseException) -> None:
    error_log.parent.mkdir(parents=True, exist_ok=True)
    tb = traceback.format_exc()
    with error_log.open('a', encoding='utf-8') as handle:
        handle.write(f'[{species_label}] {type(exc).__name__}: {exc}\n')
        handle.write(tb)
        if not tb.endswith('\n'):
            handle.write('\n')
        handle.write('\n')


def build_stdin(config: CliConfig) -> str:
    return '\n'.join([
        '200',
        '5',
        '3',
        f'0.0,{config.rmax_angstrom:.6f}',
        '4',
        str(config.n_shell_points),
        '5',
        str(config.n_radial_points),
        '0',
        '5',
        '7',
        '0',
        '-1',
        '0',
        'q',
        '',
    ])


def parse_table(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 3:
            continue
        try:
            radius = float(parts[1])
            value = float(parts[2])
        except ValueError:
            continue
        rows.append((radius, value))
    if not rows:
        raise ValueError(f'Failed to parse any rows from {path}')
    return rows


def _validate_grid(grid_a: list[float], grid_b: list[float], tolerance: float = 1e-8) -> None:
    if len(grid_a) != len(grid_b):
        raise ValueError(f'Grid length mismatch: {len(grid_a)} vs {len(grid_b)}')
    for idx, (a, b) in enumerate(zip(grid_a, grid_b), start=1):
        if abs(a - b) > tolerance:
            raise ValueError(f'Grid mismatch at row {idx}: {a} vs {b}')


def write_grid_csv(path: Path, radii_angstrom: list[float], values_by_species: dict[str, list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    species_order = list(values_by_species.keys())
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['r_angstrom', *species_order])
        for idx, radius in enumerate(radii_angstrom):
            writer.writerow([f'{radius:.10f}', *[f'{values_by_species[species][idx]:.12e}' for species in species_order]])


def run_multiwfn(row: ManifestRow, config: CliConfig, base_dir: Path) -> dict[str, object]:
    if not row.molden_path.is_file():
        raise FileNotFoundError(f'Molden file not found: {row.molden_path}')

    raw_dir = config.raw_root / row.species_label
    if raw_dir.exists() and config.overwrite:
        for child in raw_dir.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink()
    raw_dir.mkdir(parents=True, exist_ok=True)

    stdin_text = build_stdin(config)
    (raw_dir / 'stdin.txt').write_text(stdin_text, encoding='utf-8')

    env = os.environ.copy()
    env['OMP_STACKSIZE'] = config.omp_stacksize
    env['OMP_NUM_THREADS'] = str(config.nproc)
    env['Multiwfnpath'] = str(config.multiwfn_binary.parent)

    if not os.access(config.multiwfn_binary, os.X_OK):
        current_mode = config.multiwfn_binary.stat().st_mode
        config.multiwfn_binary.chmod(current_mode | 0o111)

    proc = subprocess.run(
        [str(config.multiwfn_binary), str(row.molden_path)],
        input=stdin_text,
        text=True,
        capture_output=True,
        cwd=raw_dir,
        env=env,
        timeout=config.timeout_sec,
    )

    stdout_path = raw_dir / 'stdout.txt'
    stderr_path = raw_dir / 'stderr.txt'
    stdout_path.write_text(proc.stdout, encoding='utf-8')
    stderr_path.write_text(proc.stderr, encoding='utf-8')

    if proc.returncode != 0:
        raise RuntimeError(
            f'Multiwfn exited with code {proc.returncode} for {row.species_label}. '
            f'See {stdout_path} and {stderr_path}.'
        )

    if RDF_EXPORT_RE.search(proc.stdout) is None:
        raise RuntimeError(f'Multiwfn did not report exporting RDF.txt for {row.species_label}')
    if SPHAVG_EXPORT_RE.search(proc.stdout) is None:
        raise RuntimeError(f'Multiwfn did not report exporting sphavgval.txt for {row.species_label}')

    rdf_path = raw_dir / 'RDF.txt'
    sphavg_path = raw_dir / 'sphavgval.txt'
    if not rdf_path.is_file() or not sphavg_path.is_file():
        raise RuntimeError(f'Expected RDF.txt and sphavgval.txt in {raw_dir}, but at least one is missing')

    version_match = VERSION_RE.search(proc.stdout)
    version = version_match.group('version') if version_match else None

    rdf_rows = parse_table(rdf_path)
    sphavg_rows = parse_table(sphavg_path)
    rdf_r_ang = [radius for radius, _ in rdf_rows]
    rdf_values = [value for _, value in rdf_rows]
    sphavg_r_bohr = [radius for radius, _ in sphavg_rows]
    sphavg_r_ang = [radius * BOHR_TO_ANGSTROM for radius in sphavg_r_bohr]
    sphavg_values = [value for _, value in sphavg_rows]

    if len(rdf_rows) != config.n_radial_points:
        raise ValueError(
            f'Unexpected RDF point count for {row.species_label}: '
            f'{len(rdf_rows)} != {config.n_radial_points}'
        )
    if len(sphavg_rows) != config.n_radial_points:
        raise ValueError(
            f'Unexpected sphavg point count for {row.species_label}: '
            f'{len(sphavg_rows)} != {config.n_radial_points}'
        )

    _validate_grid(rdf_r_ang, sphavg_r_ang, tolerance=5e-7)

    return {
        'species_label': row.species_label,
        'element': row.element,
        'raw_dir': raw_dir,
        'multiwfn_version': version,
        'rdf_path': rdf_path,
        'sphavg_path': sphavg_path,
        'rdf_r_angstrom': rdf_r_ang,
        'rdf_values': rdf_values,
        'sphavg_r_bohr': sphavg_r_bohr,
        'sphavg_r_angstrom': sphavg_r_ang,
        'sphavg_values': sphavg_values,
    }


def write_metadata(
    path: Path,
    *,
    base_dir: Path,
    config: CliConfig,
    rows: list[ManifestRow],
    records: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    first = records[0]
    metadata = {
        'schema_version': 1,
        'source_manifest': _portable_path(config.manifest_csv, base_dir),
        'multiwfn': {
            'binary': _portable_path(config.multiwfn_binary, base_dir),
            'variant': 'noGUI',
            'version': first.get('multiwfn_version'),
        },
        'radial_protocol': {
            'main_menu_sequence': [200, 5],
            'real_space_function': 1,
            'center_angstrom': [0.0, 0.0, 0.0],
            'rmin_angstrom': 0.0,
            'rmax_angstrom': config.rmax_angstrom,
            'n_shell_points': config.n_shell_points,
            'n_radial_points': config.n_radial_points,
            'exports': {
                'rdf_txt': {
                    'filename': 'RDF.txt',
                    'radius_unit': 'angstrom',
                    'value_description': 'Multiwfn radial distribution function export for electron density',
                },
                'sphavg_txt': {
                    'filename': 'sphavgval.txt',
                    'radius_unit': 'bohr',
                    'value_description': 'Multiwfn spherically averaged real-space function export for electron density',
                },
            },
        },
        'aggregated_outputs': {
            'rdf_grid_csv': _portable_path(config.rdf_grid_path, base_dir),
            'radial_density_grid_csv': _portable_path(config.radial_density_grid_path, base_dir),
            'radius_unit': 'angstrom',
        },
        'species': [
            {
                'species_label': row.species_label,
                'element': row.element,
                'charge': row.charge,
                'multiplicity': row.multiplicity,
                'basis': row.basis,
                'xc': row.xc,
                'molden_path': _portable_path(row.molden_path, base_dir),
                'raw_dir': _portable_path((config.raw_root / row.species_label), base_dir),
                'notes': row.notes,
            }
            for row in rows
        ],
    }
    path.write_text(json.dumps(metadata, indent=2, sort_keys=False) + '\n', encoding='utf-8')


def main(argv: Iterable[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        rows = load_manifest(config.manifest_csv)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2

    base_dir = config.manifest_csv.parent
    if config.overwrite:
        for output_path in (config.rdf_grid_path, config.radial_density_grid_path, config.meta_path):
            if output_path.exists():
                output_path.unlink()

    _write_summary_header_if_needed(config.summary_path)
    records: list[dict[str, object]] = []
    exit_code = 0

    total = len(rows)
    progress_write(f'Loaded {total} radial-density rows from {config.manifest_csv}')
    progress_write(
        f'Multiwfn binary: {config.multiwfn_binary}, rmax={config.rmax_angstrom} Å, '
        f'n_radial_points={config.n_radial_points}, nproc={config.nproc}'
    )
    if not config.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')

    row_iter = iter_progress(rows, total=total, desc='multiwfn radial', disable=config.no_progress, unit='species')
    for idx, row in enumerate(row_iter, start=1):
        if hasattr(row_iter, 'set_postfix_str'):
            row_iter.set_postfix_str(row.species_label)
        portable_molden = _portable_path(row.molden_path, base_dir)
        prefix = f'[{idx}/{total}] {row.species_label}'
        progress_write(f'{prefix} -> starting from {portable_molden}')
        try:
            record = run_multiwfn(row, config, base_dir)
            records.append(record)
            progress_write(f'{prefix} -> success')
            append_summary(
                config.summary_path,
                [
                    row.species_label,
                    'success',
                    row.element,
                    portable_molden,
                    _portable_path(record['raw_dir'], base_dir),
                    record.get('multiwfn_version') or '',
                    f'{config.rmax_angstrom:.6f}',
                    config.n_radial_points,
                    config.n_shell_points,
                    _portable_path(record['rdf_path'], base_dir),
                    _portable_path(record['sphavg_path'], base_dir),
                    'ok',
                ],
            )
        except Exception as exc:  # noqa: BLE001
            exit_code = 1
            append_error(config.error_log, row.species_label, exc)
            append_summary(
                config.summary_path,
                [
                    row.species_label,
                    'error',
                    row.element,
                    portable_molden,
                    _portable_path(config.raw_root / row.species_label, base_dir),
                    '',
                    f'{config.rmax_angstrom:.6f}',
                    config.n_radial_points,
                    config.n_shell_points,
                    '',
                    '',
                    f'{type(exc).__name__}: {exc}',
                ],
            )
            progress_write(f'{prefix} -> error: {type(exc).__name__}: {exc}', stream=sys.stderr)

    if not records:
        progress_write('No successful Multiwfn RDF runs were completed.', stream=sys.stderr)
        return 1 if exit_code else 0

    species_order = [record['species_label'] for record in records]
    reference_r = records[0]['rdf_r_angstrom']
    rdf_values_by_species: dict[str, list[float]] = {}
    density_values_by_species: dict[str, list[float]] = {}
    for record in records:
        _validate_grid(reference_r, record['rdf_r_angstrom'])
        rdf_values_by_species[record['species_label']] = record['rdf_values']
        density_values_by_species[record['species_label']] = record['sphavg_values']

    write_grid_csv(config.rdf_grid_path, reference_r, rdf_values_by_species)
    write_grid_csv(config.radial_density_grid_path, reference_r, density_values_by_species)
    write_metadata(config.meta_path, base_dir=base_dir, config=config, rows=rows, records=records)

    progress_write(f'Wrote aggregated RDF grid: {_portable_path(config.rdf_grid_path, base_dir)}')
    progress_write(f'Wrote aggregated radial-density grid: {_portable_path(config.radial_density_grid_path, base_dir)}')
    progress_write(f'Wrote metadata: {_portable_path(config.meta_path, base_dir)}')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
