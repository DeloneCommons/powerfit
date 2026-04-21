"""Run project-specific PySCF single-point calculations for QTAIM manifests.

This script reads a manifest with optimized XYZ geometries and produces Molden
files for downstream Multiwfn topology analysis. Console-only progress output
has been added to make longer batch runs easier to track without changing any
CSV or Molden artifacts.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pyscf import dft, gto, lib
from pyscf.tools import molden

from _cli_progress import iter_progress, progress_write, tqdm_available


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


@dataclass(frozen=True)
class ManifestRow:
    system_label: str
    xyz_path: Path
    molden_path: Path
    charge: int
    multiplicity: int
    name: str | None
    raw_row: dict[str, str]


@dataclass(frozen=True)
class CliConfig:
    manifest_csv: Path
    basis: str
    xc: str
    grid_level: int
    max_cycle: int
    conv_tol: float
    nproc: int
    overwrite: bool
    summary_path: Path
    error_log: Path
    no_progress: bool


def read_xyz_coords_block(xyz_path: Path) -> tuple[str, str]:
    text = xyz_path.read_text(encoding='utf-8')
    lines = [line.rstrip() for line in text.splitlines() if line.strip() != '']
    if len(lines) < 2:
        raise ValueError(f'Invalid XYZ file (too short): {xyz_path}')
    try:
        natoms = int(lines[0])
    except ValueError as exc:
        raise ValueError(f'First line of XYZ file is not an integer atom count: {xyz_path}') from exc
    if len(lines) < 2 + natoms:
        raise ValueError(f'XYZ file is truncated: {xyz_path}')
    comment = lines[1]
    coords_block = '\n'.join(lines[2:2 + natoms])
    return coords_block, comment


def _pick_label(row: dict[str, str], default_stem: str, row_index: int) -> str:
    value = row.get('system_key', '').strip()
    if value:
        return value
    if default_stem:
        return default_stem
    value = row.get('name', '').strip()
    if value:
        return value.replace(' ', '_')
    value = row.get('system_id', '').strip()
    if value:
        return value
    return f'row_{row_index}'


def load_manifest(manifest_csv: Path) -> list[ManifestRow]:
    base_dir = manifest_csv.parent
    with manifest_csv.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        required = {'xyz_path', 'molden_path', 'charge', 'multiplicity'}
        missing = required - fieldnames
        if missing:
            raise ValueError(
                'Manifest is missing required columns: ' + ', '.join(sorted(missing))
            )

        rows: list[ManifestRow] = []
        for idx, raw_row in enumerate(reader, start=2):
            if not any((value or '').strip() for value in raw_row.values()):
                continue
            label = _pick_label(raw_row, '', idx)
            try:
                xyz_path = _csv_path(base_dir, raw_row['xyz_path'].strip())
                molden_path = _csv_path(base_dir, raw_row['molden_path'].strip())
                label = _pick_label(raw_row, molden_path.stem, idx)
                charge = int(raw_row['charge'])
                multiplicity = int(raw_row['multiplicity'])
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f'Failed to parse manifest row {idx} ({label}): {exc}') from exc
            if multiplicity < 1:
                raise ValueError(f'Multiplicity must be >= 1 for {label}')
            rows.append(
                ManifestRow(
                    system_label=label,
                    xyz_path=xyz_path,
                    molden_path=molden_path,
                    charge=charge,
                    multiplicity=multiplicity,
                    name=(raw_row.get('name') or '').strip() or None,
                    raw_row={k: (v or '') for k, v in raw_row.items()},
                )
            )
    if not rows:
        raise ValueError(f'No data rows found in manifest: {manifest_csv}')
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Project-specific PySCF single-point runner for the QTAIM showcase. '
            'Reads a manifest CSV containing xyz_path, molden_path, charge, and multiplicity.'
        )
    )
    parser.add_argument('manifest_csv', help='Path to the showcase manifest CSV.')
    parser.add_argument('--basis', default='def2svp', help='Basis set (default: def2svp).')
    parser.add_argument('--xc', default='b3lyp', help='Exchange-correlation functional (default: b3lyp).')
    parser.add_argument('--grid-level', type=_positive_int, default=3, help='PySCF DFT grid level (default: 3).')
    parser.add_argument('--max-cycle', type=_positive_int, default=100, help='Maximum SCF cycles (default: 100).')
    parser.add_argument('--conv-tol', type=float, default=1e-9, help='SCF convergence tolerance (default: 1e-9).')
    parser.add_argument('--nproc', type=_positive_int, default=1, help='Number of threads (default: 1).')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing Molden files.')
    parser.add_argument('--summary-path', help='Optional output CSV summary path. Defaults next to the manifest.')
    parser.add_argument('--error-log', help='Optional error log path. Defaults next to the manifest.')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm/text progress output.')
    return parser


def parse_args(argv: Iterable[str] | None = None) -> CliConfig:
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest_csv = Path(_expand(args.manifest_csv)).resolve()
    if not manifest_csv.is_file():
        parser.error(f'Manifest CSV not found: {manifest_csv}')
    summary_path = Path(_expand(args.summary_path)).resolve() if args.summary_path else manifest_csv.with_name('pyscf_run_summary.csv')
    error_log = Path(_expand(args.error_log)).resolve() if args.error_log else manifest_csv.with_name('pyscf_errors.log')
    return CliConfig(
        manifest_csv=manifest_csv,
        basis=args.basis,
        xc=args.xc,
        grid_level=args.grid_level,
        max_cycle=args.max_cycle,
        conv_tol=args.conv_tol,
        nproc=args.nproc,
        overwrite=bool(args.overwrite),
        summary_path=summary_path,
        error_log=error_log,
        no_progress=bool(args.no_progress),
    )


def _write_summary_header_if_needed(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([
            'system_label',
            'status',
            'xyz_path',
            'molden_path',
            'charge',
            'multiplicity',
            'xc',
            'basis',
            'grid_level',
            'converged',
            'total_energy_hartree',
            'message',
        ])


def append_summary(path: Path, row: list[object]) -> None:
    _write_summary_header_if_needed(path)
    with path.open('a', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(row)


def append_error(error_log: Path, system_label: str, exc: BaseException) -> None:
    error_log.parent.mkdir(parents=True, exist_ok=True)
    with error_log.open('a', encoding='utf-8') as handle:
        handle.write(f'[{system_label}] {type(exc).__name__}: {exc}\n')
        handle.write(traceback.format_exc())
        if not traceback.format_exc().endswith('\n'):
            handle.write('\n')
        handle.write('\n')


def run_single_system(row: ManifestRow, config: CliConfig) -> tuple[str, bool, float | None, str]:
    coords_block, _comment = read_xyz_coords_block(row.xyz_path)
    spin = row.multiplicity - 1

    mol = gto.Mole()
    mol.atom = coords_block
    mol.charge = row.charge
    mol.spin = spin
    mol.basis = config.basis
    mol.verbose = 0
    mol.build(parse_arg=False)

    if row.multiplicity == 1:
        mf = dft.RKS(mol)
    else:
        mf = dft.UKS(mol)
    mf.xc = config.xc
    mf.grids.level = config.grid_level
    mf.max_cycle = config.max_cycle
    mf.conv_tol = config.conv_tol
    mf.verbose = 0

    total_energy = mf.kernel()
    if not mf.converged:
        raise RuntimeError(f'SCF did not converge for {row.system_label}')

    row.molden_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = row.molden_path.with_suffix(row.molden_path.suffix + '.tmp')
    if temp_path.exists():
        temp_path.unlink()
    molden.from_scf(mf, str(temp_path))
    temp_path.replace(row.molden_path)
    return ('success', True, float(total_energy), 'ok')


def main(argv: Iterable[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        rows = load_manifest(config.manifest_csv)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2

    lib.num_threads(config.nproc)
    base_dir = config.manifest_csv.parent
    _write_summary_header_if_needed(config.summary_path)

    total = len(rows)
    progress_write(f'Loaded {total} single-point rows from {config.manifest_csv}')
    progress_write(f'Default method: {config.xc}/{config.basis}, grid level {config.grid_level}, nproc={config.nproc}')
    if not config.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')

    exit_code = 0
    row_iter = iter_progress(rows, total=total, desc='pyscf singlepoint', disable=config.no_progress, unit='system')
    for index, row in enumerate(row_iter, start=1):
        if hasattr(row_iter, 'set_postfix_str'):
            row_iter.set_postfix_str(row.system_label)
        portable_xyz = _portable_path(row.xyz_path, base_dir)
        portable_out = _portable_path(row.molden_path, base_dir)
        prefix = f'[{index}/{total}] {row.system_label}'

        if row.molden_path.exists() and not config.overwrite:
            progress_write(f'{prefix} -> skipped (output exists)')
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    'skipped_existing',
                    portable_xyz,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    '',
                    '',
                    'output exists; use --overwrite to regenerate',
                ],
            )
            continue

        if not row.xyz_path.is_file():
            message = f'XYZ file not found: {row.xyz_path}'
            progress_write(f'{prefix} -> error: {message}', stream=sys.stderr)
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    'error',
                    portable_xyz,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    False,
                    '',
                    message,
                ],
            )
            config.error_log.parent.mkdir(parents=True, exist_ok=True)
            with config.error_log.open('a', encoding='utf-8') as handle:
                handle.write(f'[{row.system_label}] {message}\n\n')
            exit_code = 1
            continue

        temp_path = row.molden_path.with_suffix(row.molden_path.suffix + '.tmp')
        for stale in (row.molden_path, temp_path):
            if stale.exists() and config.overwrite:
                stale.unlink()

        try:
            status, converged, total_energy, message = run_single_system(row, config)
            progress_write(f'{prefix} -> success, E = {total_energy:.12f} Eh')
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    status,
                    portable_xyz,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    converged,
                    f'{total_energy:.12f}' if total_energy is not None else '',
                    message,
                ],
            )
        except Exception as exc:  # noqa: BLE001
            progress_write(f'{prefix} -> error: {exc}', stream=sys.stderr)
            if row.molden_path.exists():
                row.molden_path.unlink()
            if temp_path.exists():
                temp_path.unlink()
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    'error',
                    portable_xyz,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    False,
                    '',
                    str(exc),
                ],
            )
            append_error(config.error_log, row.system_label, exc)
            exit_code = 1
    progress_write(f'Finished PySCF single-point stage with exit code {exit_code}. Summary: {config.summary_path}')
    if exit_code != 0:
        progress_write(f'Errors were recorded in: {config.error_log}', stream=sys.stderr)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
