"""Run project-specific RDKit + PySCF geometry optimizations for QTAIM manifests.

This script builds starting geometries from SMILES (or uses manual XYZ input),
optimizes them with PySCF, and writes canonical XYZ files for downstream QTAIM
analysis. The added console progress reporting does not change any generated
XYZ or CSV artifacts.
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

from rdkit import Chem
from rdkit.Chem import AllChem
from pyscf import dft, gto, lib

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


def _portable_optional_path(path: Path | None, base_dir: Path) -> str:
    if path is None:
        return ''
    return _portable_path(path, base_dir)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected a positive integer, got {value!r}') from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError(f'Expected a positive integer, got {value!r}')
    return parsed


def _nonnegative_seed(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected an integer seed, got {value!r}') from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f'Expected a non-negative integer seed, got {value!r}')
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'Expected a positive float, got {value!r}') from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f'Expected a positive float, got {value!r}')
    return parsed


@dataclass(frozen=True)
class ManifestRow:
    system_label: str
    optimized_xyz_path: Path
    charge: int
    multiplicity: int
    smiles: str | None
    input_xyz_path: Path | None
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
    optimizer: str
    maxsteps: int
    nproc: int
    overwrite: bool
    allow_inplace: bool
    summary_path: Path
    error_log: Path
    rdkit_num_confs: int
    rdkit_prune_rms_thresh: float
    rdkit_seed: int
    rdkit_forcefield: str
    rdkit_max_iters: int
    no_progress: bool


@dataclass(frozen=True)
class StartingGeometry:
    coords_block: str
    source_mode: str
    comment: str
    rdkit_num_confs_requested: int | None = None
    rdkit_num_confs_embedded: int | None = None
    rdkit_forcefield: str | None = None
    rdkit_best_conf_id: int | None = None
    rdkit_best_energy: float | None = None
    rdkit_best_converged: bool | None = None


@dataclass(frozen=True)
class RunResult:
    status: str
    final_energy: float | None
    message: str
    start_geometry: StartingGeometry


FORCEFIELD_CHOICES = ('auto', 'mmff94', 'mmff94s', 'uff')


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
    value = row.get('system_id', '').strip()
    if value:
        return value
    value = row.get('name', '').strip()
    if value:
        return value.replace(' ', '_')
    if default_stem:
        return default_stem
    return f'row_{row_index}'


def load_manifest(manifest_csv: Path, allow_inplace: bool) -> list[ManifestRow]:
    base_dir = manifest_csv.parent
    with manifest_csv.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        required = {'xyz_path', 'charge', 'multiplicity'}
        missing = sorted(required - fieldnames)
        if missing:
            raise ValueError('Manifest is missing required columns: ' + ', '.join(missing))
        if 'smiles' not in fieldnames and 'input_xyz_path' not in fieldnames:
            raise ValueError('Manifest must include at least one of the columns smiles or input_xyz_path')

        rows: list[ManifestRow] = []
        for idx, raw_row in enumerate(reader, start=2):
            if not any((value or '').strip() for value in raw_row.values()):
                continue
            try:
                output_xyz = _csv_path(base_dir, (raw_row.get('xyz_path') or '').strip())
                smiles = (raw_row.get('smiles') or '').strip() or None
                input_xyz_raw = (raw_row.get('input_xyz_path') or '').strip()
                input_xyz = _csv_path(base_dir, input_xyz_raw) if input_xyz_raw else None
                label = _pick_label(raw_row, output_xyz.stem, idx)
                charge = int(raw_row['charge'])
                multiplicity = int(raw_row['multiplicity'])
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f'Failed to parse manifest row {idx}: {exc}') from exc
            if multiplicity < 1:
                raise ValueError(f'Multiplicity must be >= 1 for {label}')
            if input_xyz is None and smiles is None:
                raise ValueError(f'Row {idx} ({label}) must provide either smiles or input_xyz_path')
            if input_xyz is not None and input_xyz == output_xyz and not allow_inplace:
                raise ValueError(
                    f'Input and output XYZ paths are identical for {label}: {input_xyz}. '
                    'Use separate columns (for example input_xyz_path -> xyz_path) or pass --allow-inplace.'
                )
            rows.append(
                ManifestRow(
                    system_label=label,
                    optimized_xyz_path=output_xyz,
                    charge=charge,
                    multiplicity=multiplicity,
                    smiles=smiles,
                    input_xyz_path=input_xyz,
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
            'Project-specific PySCF geometry-optimization runner. Reads a manifest CSV, '
            'builds starting geometries from SMILES with RDKit ETKDG conformer search '
            '(or uses a manual input XYZ when provided), then writes optimized XYZ files.'
        )
    )
    parser.add_argument('manifest_csv', help='Path to the manifest CSV.')
    parser.add_argument('--basis', default='def2svp', help='Basis set (default: def2svp).')
    parser.add_argument('--xc', default='b3lyp', help='Exchange-correlation functional (default: b3lyp).')
    parser.add_argument('--grid-level', type=_positive_int, default=3, help='PySCF DFT grid level (default: 3).')
    parser.add_argument('--max-cycle', type=_positive_int, default=100, help='Maximum SCF cycles per step (default: 100).')
    parser.add_argument('--conv-tol', type=float, default=1e-9, help='SCF convergence tolerance (default: 1e-9).')
    parser.add_argument(
        '--optimizer',
        choices=['geometric', 'berny'],
        default='geometric',
        help='Geometry optimizer backend (default: geometric).',
    )
    parser.add_argument('--maxsteps', type=_positive_int, default=100, help='Maximum optimization steps (default: 100).')
    parser.add_argument('--nproc', type=_positive_int, default=1, help='Number of threads (default: 1).')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing optimized XYZ files.')
    parser.add_argument(
        '--allow-inplace',
        action='store_true',
        help='Allow the output XYZ path to be identical to the manual input XYZ path.',
    )
    parser.add_argument('--summary-path', help='Optional output CSV summary path. Defaults next to the manifest.')
    parser.add_argument('--error-log', help='Optional error log path. Defaults next to the manifest.')
    parser.add_argument('--no-progress', action='store_true', help='Disable tqdm/text progress output.')
    parser.add_argument(
        '--rdkit-num-confs',
        type=_positive_int,
        default=100,
        help='Number of ETKDG conformers to generate per SMILES row (default: 100).',
    )
    parser.add_argument(
        '--rdkit-prune-rms-thresh',
        type=_positive_float,
        default=0.25,
        help='RMS threshold (Å) for pruning near-duplicate RDKit conformers (default: 0.25).',
    )
    parser.add_argument(
        '--rdkit-seed',
        type=_nonnegative_seed,
        default=61453,
        help='RDKit random seed for conformer embedding (default: 61453).',
    )
    parser.add_argument(
        '--rdkit-forcefield',
        choices=FORCEFIELD_CHOICES,
        default='auto',
        help='Force field used to rank RDKit conformers (default: auto = MMFF94 else UFF).',
    )
    parser.add_argument(
        '--rdkit-max-iters',
        type=_positive_int,
        default=500,
        help='Maximum iterations for RDKit force-field optimization (default: 500).',
    )
    return parser


def parse_args(argv: Iterable[str] | None = None) -> CliConfig:
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest_csv = Path(_expand(args.manifest_csv)).resolve()
    if not manifest_csv.is_file():
        parser.error(f'Manifest CSV not found: {manifest_csv}')
    summary_path = Path(_expand(args.summary_path)).resolve() if args.summary_path else manifest_csv.with_name('pyscf_geomopt_summary.csv')
    error_log = Path(_expand(args.error_log)).resolve() if args.error_log else manifest_csv.with_name('pyscf_geomopt_errors.log')
    return CliConfig(
        manifest_csv=manifest_csv,
        basis=args.basis,
        xc=args.xc,
        grid_level=args.grid_level,
        max_cycle=args.max_cycle,
        conv_tol=args.conv_tol,
        optimizer=args.optimizer,
        maxsteps=args.maxsteps,
        nproc=args.nproc,
        overwrite=bool(args.overwrite),
        allow_inplace=bool(args.allow_inplace),
        summary_path=summary_path,
        error_log=error_log,
        rdkit_num_confs=args.rdkit_num_confs,
        rdkit_prune_rms_thresh=args.rdkit_prune_rms_thresh,
        rdkit_seed=args.rdkit_seed,
        rdkit_forcefield=args.rdkit_forcefield,
        rdkit_max_iters=args.rdkit_max_iters,
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
            'source_mode',
            'smiles',
            'input_xyz_path',
            'optimized_xyz_path',
            'charge',
            'multiplicity',
            'optimizer',
            'xc',
            'basis',
            'grid_level',
            'maxsteps',
            'rdkit_num_confs_requested',
            'rdkit_num_confs_embedded',
            'rdkit_forcefield',
            'rdkit_best_conf_id',
            'rdkit_best_energy',
            'rdkit_best_converged',
            'final_energy_hartree',
            'message',
        ])


def append_summary(path: Path, row: list[object]) -> None:
    _write_summary_header_if_needed(path)
    with path.open('a', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(row)


def append_error(error_log: Path, system_label: str, exc: BaseException) -> None:
    error_log.parent.mkdir(parents=True, exist_ok=True)
    tb = traceback.format_exc()
    with error_log.open('a', encoding='utf-8') as handle:
        handle.write(f'[{system_label}] {type(exc).__name__}: {exc}\n')
        handle.write(tb)
        if not tb.endswith('\n'):
            handle.write('\n')
        handle.write('\n---\n\n')


def _load_optimizer(name: str):
    if name == 'geometric':
        try:
            from pyscf.geomopt.geometric_solver import optimize as optimize_fn
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                'Failed to import pyscf.geomopt.geometric_solver.optimize. '
                "Install the 'geometric' package or use --optimizer berny if pyberny is available."
            ) from exc
        return optimize_fn
    if name == 'berny':
        try:
            from pyscf.geomopt.berny_solver import optimize as optimize_fn
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                'Failed to import pyscf.geomopt.berny_solver.optimize. '
                "Install 'pyberny' or switch back to --optimizer geometric."
            ) from exc
        return optimize_fn
    raise ValueError(f'Unknown optimizer backend: {name}')


def _build_mf_from_xyz(coords_block: str, charge: int, multiplicity: int, config: CliConfig):
    spin = multiplicity - 1
    mol = gto.Mole()
    mol.atom = coords_block
    mol.charge = charge
    mol.spin = spin
    mol.basis = config.basis
    mol.verbose = 0
    mol.build(parse_arg=False)

    if multiplicity == 1:
        mf = dft.RKS(mol)
    else:
        mf = dft.UKS(mol)
    mf.xc = config.xc
    mf.grids.level = config.grid_level
    mf.max_cycle = config.max_cycle
    mf.conv_tol = config.conv_tol
    mf.verbose = 0
    return mol, mf


def _format_xyz(mol, comment: str) -> str:
    coords = mol.atom_coords(unit='Ang')
    lines = [str(mol.natm), comment]
    for idx in range(mol.natm):
        symbol = mol.atom_symbol(idx)
        x, y, z = coords[idx]
        lines.append(f'{symbol:<2} {x:>16.10f} {y:>16.10f} {z:>16.10f}')
    return '\n'.join(lines) + '\n'


def _rdkit_forcefield_results(mol_h, config: CliConfig) -> tuple[str, list[tuple[int, float]]]:
    ff_choice = config.rdkit_forcefield.lower()
    if ff_choice == 'auto':
        if AllChem.MMFFHasAllMoleculeParams(mol_h):
            ff_choice = 'mmff94'
        elif AllChem.UFFHasAllMoleculeParams(mol_h):
            ff_choice = 'uff'
        else:
            raise RuntimeError('RDKit could not find MMFF or UFF parameters for the generated molecule')

    num_threads = config.nproc if config.nproc > 0 else 0
    if ff_choice == 'mmff94':
        if not AllChem.MMFFHasAllMoleculeParams(mol_h):
            raise RuntimeError('Requested MMFF94, but RDKit does not have MMFF parameters for this molecule')
        results = AllChem.MMFFOptimizeMoleculeConfs(
            mol_h,
            numThreads=num_threads,
            maxIters=config.rdkit_max_iters,
            mmffVariant='MMFF94',
        )
        return ('MMFF94', [(int(not_converged), float(energy)) for not_converged, energy in results])
    if ff_choice == 'mmff94s':
        if not AllChem.MMFFHasAllMoleculeParams(mol_h):
            raise RuntimeError('Requested MMFF94s, but RDKit does not have MMFF parameters for this molecule')
        results = AllChem.MMFFOptimizeMoleculeConfs(
            mol_h,
            numThreads=num_threads,
            maxIters=config.rdkit_max_iters,
            mmffVariant='MMFF94s',
        )
        return ('MMFF94s', [(int(not_converged), float(energy)) for not_converged, energy in results])
    if ff_choice == 'uff':
        if not AllChem.UFFHasAllMoleculeParams(mol_h):
            raise RuntimeError('Requested UFF, but RDKit does not have UFF parameters for this molecule')
        results = AllChem.UFFOptimizeMoleculeConfs(
            mol_h,
            numThreads=num_threads,
            maxIters=config.rdkit_max_iters,
        )
        return ('UFF', [(int(not_converged), float(energy)) for not_converged, energy in results])
    raise ValueError(f'Unknown RDKit forcefield choice: {config.rdkit_forcefield}')


def _coords_block_from_conformer(mol_h, conf_id: int) -> str:
    conf = mol_h.GetConformer(conf_id)
    lines: list[str] = []
    for atom in mol_h.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        lines.append(f'{atom.GetSymbol()} {pos.x:.10f} {pos.y:.10f} {pos.z:.10f}')
    return '\n'.join(lines)


def _starting_geometry_from_smiles(row: ManifestRow, config: CliConfig) -> StartingGeometry:
    assert row.smiles is not None
    mol = Chem.MolFromSmiles(row.smiles)
    if mol is None:
        raise ValueError(f'RDKit failed to parse SMILES for {row.system_label}: {row.smiles!r}')

    formal_charge = Chem.GetFormalCharge(mol)
    if formal_charge != row.charge:
        raise ValueError(
            f'SMILES formal charge ({formal_charge}) does not match manifest charge ({row.charge}) '
            f'for {row.system_label}. Encode charges explicitly in SMILES or provide input_xyz_path.'
        )

    mol_h = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = config.rdkit_seed
    params.numThreads = config.nproc if config.nproc > 0 else 0
    params.pruneRmsThresh = config.rdkit_prune_rms_thresh
    conf_ids = list(AllChem.EmbedMultipleConfs(mol_h, numConfs=config.rdkit_num_confs, params=params))
    if not conf_ids:
        raise RuntimeError(f'RDKit could not embed any conformers for {row.system_label}')

    ff_label, results = _rdkit_forcefield_results(mol_h, config)
    if len(results) != len(conf_ids):
        raise RuntimeError(
            f'Unexpected RDKit optimization output for {row.system_label}: '
            f'{len(results)} results for {len(conf_ids)} conformers'
        )

    ranked = [
        {
            'conf_id': int(conf_id),
            'not_converged': int(not_converged),
            'energy': float(energy),
        }
        for conf_id, (not_converged, energy) in zip(conf_ids, results)
    ]
    converged = [entry for entry in ranked if entry['not_converged'] == 0]
    pool = converged if converged else ranked
    best = min(pool, key=lambda entry: entry['energy'])

    coords_block = _coords_block_from_conformer(mol_h, best['conf_id'])
    comment = (
        f'optimized by PySCF ({config.optimizer}) xc={config.xc} basis={config.basis} '
        f'charge={row.charge} multiplicity={row.multiplicity} '
        f'start=RDKit_ETKDGv3 ff={ff_label} conf={best["conf_id"]} '
        f'ff_energy={best["energy"]:.8f}'
    )
    return StartingGeometry(
        coords_block=coords_block,
        source_mode='smiles_rdkit',
        comment=comment,
        rdkit_num_confs_requested=config.rdkit_num_confs,
        rdkit_num_confs_embedded=len(conf_ids),
        rdkit_forcefield=ff_label,
        rdkit_best_conf_id=best['conf_id'],
        rdkit_best_energy=best['energy'],
        rdkit_best_converged=(best['not_converged'] == 0),
    )


def _starting_geometry_from_manual_xyz(row: ManifestRow, config: CliConfig) -> StartingGeometry:
    assert row.input_xyz_path is not None
    coords_block, input_comment = read_xyz_coords_block(row.input_xyz_path)
    comment = (
        f'optimized by PySCF ({config.optimizer}) xc={config.xc} basis={config.basis} '
        f'charge={row.charge} multiplicity={row.multiplicity} start=manual_xyz'
    )
    if input_comment:
        comment = f'{comment}; input_comment={input_comment}'
    return StartingGeometry(
        coords_block=coords_block,
        source_mode='manual_xyz',
        comment=comment,
    )


def _build_starting_geometry(row: ManifestRow, config: CliConfig) -> StartingGeometry:
    if row.input_xyz_path is not None:
        return _starting_geometry_from_manual_xyz(row, config)
    return _starting_geometry_from_smiles(row, config)


def run_single_system(row: ManifestRow, config: CliConfig) -> RunResult:
    start_geometry = _build_starting_geometry(row, config)
    _mol0, mf0 = _build_mf_from_xyz(start_geometry.coords_block, row.charge, row.multiplicity, config)
    optimize_fn = _load_optimizer(config.optimizer)
    try:
        mol_opt = optimize_fn(mf0, maxsteps=config.maxsteps)
    except TypeError:
        mol_opt = optimize_fn(mf0, maxsteps=config.maxsteps)

    final_coords_block = '\n'.join(
        f'{mol_opt.atom_symbol(i)} {mol_opt.atom_coords(unit="Ang")[i][0]} {mol_opt.atom_coords(unit="Ang")[i][1]} {mol_opt.atom_coords(unit="Ang")[i][2]}'
        for i in range(mol_opt.natm)
    )
    _mol_final, mf_final = _build_mf_from_xyz(final_coords_block, row.charge, row.multiplicity, config)
    final_energy = mf_final.kernel()
    if not mf_final.converged:
        raise RuntimeError(f'Final SCF did not converge for {row.system_label}')

    row.optimized_xyz_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = row.optimized_xyz_path.with_suffix(row.optimized_xyz_path.suffix + '.tmp')
    if temp_path.exists():
        temp_path.unlink()
    temp_path.write_text(_format_xyz(mol_opt, start_geometry.comment), encoding='utf-8')
    temp_path.replace(row.optimized_xyz_path)
    return RunResult(
        status='success',
        final_energy=float(final_energy),
        message='ok',
        start_geometry=start_geometry,
    )


def main(argv: Iterable[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        rows = load_manifest(config.manifest_csv, allow_inplace=config.allow_inplace)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2

    lib.num_threads(config.nproc)
    base_dir = config.manifest_csv.parent
    _write_summary_header_if_needed(config.summary_path)

    total = len(rows)
    progress_write(f'Loaded {total} geometry-optimization rows from {config.manifest_csv}')
    progress_write(
        f'Default method: {config.xc}/{config.basis}, optimizer={config.optimizer}, '
        f'grid level {config.grid_level}, nproc={config.nproc}'
    )
    if not config.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')

    exit_code = 0
    row_iter = iter_progress(rows, total=total, desc='pyscf geomopt', disable=config.no_progress, unit='system')
    for index, row in enumerate(row_iter, start=1):
        if hasattr(row_iter, 'set_postfix_str'):
            row_iter.set_postfix_str(row.system_label)
        portable_in = _portable_optional_path(row.input_xyz_path, base_dir)
        portable_out = _portable_path(row.optimized_xyz_path, base_dir)
        smiles_text = row.smiles or ''
        source_mode = 'manual_xyz' if row.input_xyz_path is not None else 'smiles_rdkit'
        prefix = f'[{index}/{total}] {row.system_label}'

        if row.optimized_xyz_path.exists() and not config.overwrite:
            progress_write(f'{prefix} -> skipped (output exists)')
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    'skipped_existing',
                    source_mode,
                    smiles_text,
                    portable_in,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.optimizer,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    config.maxsteps,
                    config.rdkit_num_confs if source_mode == 'smiles_rdkit' else '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    'output exists; use --overwrite to regenerate',
                ],
            )
            continue

        if row.input_xyz_path is not None and not row.input_xyz_path.is_file():
            message = f'Input XYZ file not found: {row.input_xyz_path}'
            progress_write(f'{prefix} -> error: {message}', stream=sys.stderr)
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    'error',
                    source_mode,
                    smiles_text,
                    portable_in,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.optimizer,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    config.maxsteps,
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    message,
                ],
            )
            config.error_log.parent.mkdir(parents=True, exist_ok=True)
            with config.error_log.open('a', encoding='utf-8') as handle:
                handle.write(f'[{row.system_label}] {message}\n\n')
            exit_code = 1
            continue

        temp_path = row.optimized_xyz_path.with_suffix(row.optimized_xyz_path.suffix + '.tmp')
        for stale in (row.optimized_xyz_path, temp_path):
            if stale.exists() and config.overwrite:
                stale.unlink()

        try:
            result = run_single_system(row, config)
            sg = result.start_geometry
            progress_write(
                f'{prefix} -> success, source={sg.source_mode}, final E = {result.final_energy:.12f} Eh'
            )
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    result.status,
                    sg.source_mode,
                    smiles_text,
                    portable_in,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.optimizer,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    config.maxsteps,
                    sg.rdkit_num_confs_requested if sg.rdkit_num_confs_requested is not None else '',
                    sg.rdkit_num_confs_embedded if sg.rdkit_num_confs_embedded is not None else '',
                    sg.rdkit_forcefield or '',
                    sg.rdkit_best_conf_id if sg.rdkit_best_conf_id is not None else '',
                    f'{sg.rdkit_best_energy:.8f}' if sg.rdkit_best_energy is not None else '',
                    sg.rdkit_best_converged if sg.rdkit_best_converged is not None else '',
                    f'{result.final_energy:.12f}' if result.final_energy is not None else '',
                    result.message,
                ],
            )
        except Exception as exc:  # noqa: BLE001
            progress_write(f'{prefix} -> error: {exc}', stream=sys.stderr)
            if row.optimized_xyz_path.exists():
                row.optimized_xyz_path.unlink()
            if temp_path.exists():
                temp_path.unlink()
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    'error',
                    source_mode,
                    smiles_text,
                    portable_in,
                    portable_out,
                    row.charge,
                    row.multiplicity,
                    config.optimizer,
                    config.xc,
                    config.basis,
                    config.grid_level,
                    config.maxsteps,
                    config.rdkit_num_confs if source_mode == 'smiles_rdkit' else '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    str(exc),
                ],
            )
            append_error(config.error_log, row.system_label, exc)
            exit_code = 1
    progress_write(f'Finished geometry-optimization stage with exit code {exit_code}. Summary: {config.summary_path}')
    if exit_code != 0:
        progress_write(f'Errors were recorded in: {config.error_log}', stream=sys.stderr)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
