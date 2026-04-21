"""Run project-specific Multiwfn topology searches and parse QTAIM JSON.

The script consumes Molden files listed in a manifest, drives the fixed
Multiwfn CP-search workflow used in this project, and stores compact JSON
records together with raw stdout/stderr logs. Added console progress output
does not modify the parsed JSON or CSV summary artifacts.
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

CP_LINE_RE = re.compile(
    r'^\s*(?P<index>\d+)\s+'
    r'(?P<x>[-+0-9.Ee]+)\s+'
    r'(?P<y>[-+0-9.Ee]+)\s+'
    r'(?P<z>[-+0-9.Ee]+)\s+'
    r'\((?P<sig1>3),(?P<sig2>[-+]\d)\)\s*(?P<rest>.*)$'
)
NUCLEUS_RE = re.compile(r'Nucleus:\s*(?P<atom_index>\d+)\((?P<element>[^)]*)\)')
BCP_EDGE_RE = re.compile(
    r'(?P<atom_i>\d+)\((?P<element_i>[^)]*)\)\s*--\s*'
    r'(?P<atom_j>\d+)\((?P<element_j>[^)]*)\)'
)
COUNTS_RE = re.compile(
    r'\(3,-3\):\s*(?P<ncp>\d+),\s*'
    r'\(3,-1\):\s*(?P<bcp>\d+),\s*'
    r'\(3,\+1\):\s*(?P<rcp>\d+),\s*'
    r'\(3,\+3\):\s*(?P<ccp>\d+)'
)
POINCARE_RE = re.compile(
    r'Poincare-Hopf verification:\s*(?P<ncp>[-+]?\d+)\s*-\s*(?P<bcp>[-+]?\d+)\s*\+\s*(?P<rcp>[-+]?\d+)\s*-\s*(?P<ccp>[-+]?\d+)\s*=\s*(?P<result>[-+]?\d+)'
)
VERSION_RE = re.compile(r'Version\s+(?P<version>[0-9][0-9A-Za-z.+_-]*)')
PATH_COUNT_RE = re.compile(r'Totally found\s+(?P<count>\d+)\s+new paths')

TOPOLOGY_STDIN = '\n'.join([
    '2',
    '2',
    '3',
    '4',
    '5',
    '8',
    '0',
    '-10',
    'q',
    '',
])


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
    json_path: Path
    raw_row: dict[str, str]


@dataclass(frozen=True)
class CliConfig:
    manifest_csv: Path
    multiwfn_binary: Path
    raw_root: Path
    summary_path: Path
    error_log: Path
    nproc: int
    overwrite: bool
    omp_stacksize: str
    timeout_sec: int
    no_progress: bool


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
        required = {'xyz_path', 'molden_path'}
        missing = required - fieldnames
        if missing:
            raise ValueError('Manifest is missing required columns: ' + ', '.join(sorted(missing)))
        json_column = 'json_path' if 'json_path' in fieldnames else 'qtaim_json_path' if 'qtaim_json_path' in fieldnames else None
        if json_column is None:
            raise ValueError('Manifest must contain either json_path or qtaim_json_path column')

        rows: list[ManifestRow] = []
        for idx, raw_row in enumerate(reader, start=2):
            if not any((value or '').strip() for value in raw_row.values()):
                continue
            xyz_path = _csv_path(base_dir, raw_row['xyz_path'].strip())
            molden_path = _csv_path(base_dir, raw_row['molden_path'].strip())
            json_path = _csv_path(base_dir, raw_row[json_column].strip())
            label = _pick_label(raw_row, molden_path.stem, idx)
            rows.append(
                ManifestRow(
                    system_label=label,
                    xyz_path=xyz_path,
                    molden_path=molden_path,
                    json_path=json_path,
                    raw_row={k: (v or '') for k, v in raw_row.items()},
                )
            )
    if not rows:
        raise ValueError(f'No data rows found in manifest: {manifest_csv}')
    return rows


def read_xyz_atoms(xyz_path: Path) -> list[dict[str, object]]:
    text = xyz_path.read_text(encoding='utf-8')
    lines = [line.rstrip() for line in text.splitlines() if line.strip() != '']
    natoms = int(lines[0])
    atoms: list[dict[str, object]] = []
    for idx, line in enumerate(lines[2:2 + natoms], start=1):
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f'Invalid XYZ atom line in {xyz_path}: {line!r}')
        atoms.append(
            {
                'atom_index': idx,
                'element': parts[0],
                'position_angstrom': [float(parts[1]), float(parts[2]), float(parts[3])],
            }
        )
    return atoms


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            'Run Multiwfn topology search (CP searches 2-5 plus path generation 8) '
            'for each Molden file listed in a manifest CSV, then parse the output '
            'into compact QTAIM JSON records.'
        )
    )
    parser.add_argument('manifest_csv', help='Path to the showcase manifest CSV.')
    parser.add_argument(
        '--multiwfn-binary',
        default=None,
        help='Path to Multiwfn_noGUI. Defaults to external_software/Multiwfn_noGUI in the repo.',
    )
    parser.add_argument(
        '--raw-root',
        default=None,
        help='Directory where per-system raw Multiwfn logs will be stored. Defaults next to the manifest.',
    )
    parser.add_argument('--summary-path', help='Optional output CSV summary path. Defaults next to the manifest.')
    parser.add_argument('--error-log', help='Optional error log path. Defaults next to the manifest.')
    parser.add_argument('--nproc', type=_positive_int, default=1, help='Number of threads to request for Multiwfn.')
    parser.add_argument('--omp-stacksize', default='512M', help='OMP_STACKSIZE passed to Multiwfn (default: 512M).')
    parser.add_argument('--timeout-sec', type=_positive_int, default=600, help='Per-system timeout in seconds (default: 600).')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing JSON outputs.')
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
    raw_root = Path(_expand(args.raw_root)).resolve() if args.raw_root else manifest_csv.parent / 'multiwfn_raw'
    summary_path = Path(_expand(args.summary_path)).resolve() if args.summary_path else manifest_csv.with_name('multiwfn_run_summary.csv')
    error_log = Path(_expand(args.error_log)).resolve() if args.error_log else manifest_csv.with_name('multiwfn_errors.log')
    if not multiwfn_binary.is_file():
        parser.error(f'Multiwfn binary not found: {multiwfn_binary}')
    return CliConfig(
        manifest_csv=manifest_csv,
        multiwfn_binary=multiwfn_binary,
        raw_root=raw_root,
        summary_path=summary_path,
        error_log=error_log,
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
            'system_label',
            'status',
            'molden_path',
            'json_path',
            'multiwfn_version',
            'ncp',
            'bcp',
            'rcp',
            'ccp',
            'poincare_result',
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


def _cp_type(sig2: str) -> str:
    mapping = {'-3': 'ncp', '-1': 'bcp', '+1': 'rcp', '+3': 'ccp'}
    if sig2 not in mapping:
        raise ValueError(f'Unsupported CP signature component: {sig2}')
    return mapping[sig2]


def _bohr_to_angstrom(coords: list[float]) -> list[float]:
    return [value * BOHR_TO_ANGSTROM for value in coords]


def parse_multiwfn_output(text: str) -> dict[str, object]:
    lines = text.splitlines()

    version_match = VERSION_RE.search(text)
    version = version_match.group('version') if version_match else None

    path_count_match = PATH_COUNT_RE.search(text)
    generated_path_count = int(path_count_match.group('count')) if path_count_match else None

    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip().startswith('Summary of found CPs:'):
            start_idx = idx
    if start_idx is None:
        raise ValueError('Could not locate "Summary of found CPs:" block in Multiwfn output')

    counts_idx = None
    poincare_idx = None
    for idx in range(start_idx + 1, len(lines)):
        if 'The number of critical points of each type:' in lines[idx]:
            counts_idx = idx
            break
    if counts_idx is None:
        raise ValueError('Could not locate the CP counts line in Multiwfn output')

    for idx in range(counts_idx + 1, len(lines)):
        if 'Poincare-Hopf verification:' in lines[idx]:
            poincare_idx = idx
            break

    cp_entries: list[dict[str, object]] = []
    for line in lines[start_idx + 1:counts_idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith('Index'):
            continue
        match = CP_LINE_RE.match(line)
        if match is None:
            continue
        coords_bohr = [float(match.group('x')), float(match.group('y')), float(match.group('z'))]
        cp_kind = _cp_type(match.group('sig2'))
        rest = match.group('rest').strip()
        cp_entry: dict[str, object] = {
            'cp_index': int(match.group('index')),
            'cp_signature': f"({match.group('sig1')},{match.group('sig2')})",
            'cp_type': cp_kind,
            'position_bohr': coords_bohr,
            'position_angstrom': _bohr_to_angstrom(coords_bohr),
        }
        if cp_kind == 'ncp':
            nucleus_match = NUCLEUS_RE.search(rest)
            if nucleus_match is not None:
                cp_entry['nucleus_atom_index'] = int(nucleus_match.group('atom_index'))
                cp_entry['nucleus_element'] = nucleus_match.group('element').strip()
        elif cp_kind == 'bcp':
            edge_match = BCP_EDGE_RE.search(rest)
            if edge_match is not None:
                atom_i = int(edge_match.group('atom_i'))
                atom_j = int(edge_match.group('atom_j'))
                cp_entry['atom_i'] = atom_i
                cp_entry['atom_j'] = atom_j
                cp_entry['elements'] = [edge_match.group('element_i').strip(), edge_match.group('element_j').strip()]
        cp_entries.append(cp_entry)

    counts_match = COUNTS_RE.search(lines[counts_idx])
    if counts_match is None and counts_idx + 1 < len(lines):
        counts_match = COUNTS_RE.search(lines[counts_idx + 1])
    if counts_match is None:
        raise ValueError('Failed to parse the CP counts line from Multiwfn output')
    counts = {
        'ncp': int(counts_match.group('ncp')),
        'bcp': int(counts_match.group('bcp')),
        'rcp': int(counts_match.group('rcp')),
        'ccp': int(counts_match.group('ccp')),
    }

    poincare = None
    if poincare_idx is not None:
        poincare_match = POINCARE_RE.search(lines[poincare_idx])
        if poincare_match is not None:
            poincare = {
                'ncp': int(poincare_match.group('ncp')),
                'bcp': int(poincare_match.group('bcp')),
                'rcp': int(poincare_match.group('rcp')),
                'ccp': int(poincare_match.group('ccp')),
                'result': int(poincare_match.group('result')),
                'satisfied': int(poincare_match.group('result')) == 1,
            }

    unique_edges: dict[tuple[int, int], dict[str, object]] = {}
    for cp in cp_entries:
        if cp.get('cp_type') != 'bcp':
            continue
        if 'atom_i' not in cp or 'atom_j' not in cp:
            continue
        atom_i = int(cp['atom_i'])
        atom_j = int(cp['atom_j'])
        edge_key = tuple(sorted((atom_i, atom_j)))
        unique_edges[edge_key] = {
            'atom_i': edge_key[0],
            'atom_j': edge_key[1],
            'cp_index': int(cp['cp_index']),
        }

    return {
        'multiwfn_version': version,
        'generated_path_count': generated_path_count,
        'critical_points': cp_entries,
        'counts': counts,
        'poincare_hopf': poincare,
        'bcp_graph': list(unique_edges.values()),
    }


def make_json_record(row: ManifestRow, base_dir: Path, multiwfn_binary: Path, raw_dir: Path, parsed: dict[str, object]) -> dict[str, object]:
    atoms = read_xyz_atoms(row.xyz_path)
    counts = parsed['counts']
    critical_points = parsed['critical_points']
    ring_cp_indices = [cp['cp_index'] for cp in critical_points if cp['cp_type'] == 'rcp']
    cage_cp_indices = [cp['cp_index'] for cp in critical_points if cp['cp_type'] == 'ccp']

    return {
        'schema_version': 1,
        'system_label': row.system_label,
        'source_paths': {
            'xyz_path': _portable_path(row.xyz_path, base_dir),
            'molden_path': _portable_path(row.molden_path, base_dir),
            'multiwfn_stdout_path': _portable_path(raw_dir / 'stdout.txt', base_dir),
            'multiwfn_stderr_path': _portable_path(raw_dir / 'stderr.txt', base_dir),
            'multiwfn_stdin_path': _portable_path(raw_dir / 'stdin.txt', base_dir),
        },
        'software': {
            'multiwfn_binary': _portable_path(multiwfn_binary, base_dir),
            'multiwfn_variant': 'noGUI',
            'multiwfn_version': parsed.get('multiwfn_version'),
        },
        'search_protocol': {
            'topology_menu_sequence': [2, 3, 4, 5, 8, 0],
            'notes': 'Critical-point coordinates reported by Multiwfn topology analysis are in Bohr.',
        },
        'units': {
            'xyz_atoms': 'angstrom',
            'critical_points': {
                'position_bohr': 'bohr',
                'position_angstrom': 'angstrom',
            },
        },
        'atoms': atoms,
        'counts': counts,
        'poincare_hopf': parsed.get('poincare_hopf'),
        'generated_path_count': parsed.get('generated_path_count'),
        'critical_points': critical_points,
        'bcp_graph': parsed['bcp_graph'],
        'motif_summary': {
            'n_bcp': counts['bcp'],
            'n_rcp': counts['rcp'],
            'n_ccp': counts['ccp'],
            'ring_cp_indices': ring_cp_indices,
            'cage_cp_indices': cage_cp_indices,
            'has_ring_cp': bool(ring_cp_indices),
            'has_cage_cp': bool(cage_cp_indices),
        },
    }


def run_multiwfn(row: ManifestRow, config: CliConfig, base_dir: Path) -> dict[str, object]:
    if not row.molden_path.is_file():
        raise FileNotFoundError(f'Molden file not found: {row.molden_path}')
    raw_dir = config.raw_root / row.system_label
    raw_dir.mkdir(parents=True, exist_ok=True)

    stdin_path = raw_dir / 'stdin.txt'
    stdout_path = raw_dir / 'stdout.txt'
    stderr_path = raw_dir / 'stderr.txt'
    stdin_path.write_text(TOPOLOGY_STDIN, encoding='utf-8')

    env = os.environ.copy()
    env['OMP_STACKSIZE'] = config.omp_stacksize
    env['OMP_NUM_THREADS'] = str(config.nproc)
    env['Multiwfnpath'] = str(config.multiwfn_binary.parent)

    if not os.access(config.multiwfn_binary, os.X_OK):
        current_mode = config.multiwfn_binary.stat().st_mode
        config.multiwfn_binary.chmod(current_mode | 0o111)

    proc = subprocess.run(
        [str(config.multiwfn_binary), str(row.molden_path)],
        input=TOPOLOGY_STDIN,
        text=True,
        capture_output=True,
        cwd=raw_dir,
        env=env,
        timeout=config.timeout_sec,
    )

    stdout_path.write_text(proc.stdout, encoding='utf-8')
    stderr_path.write_text(proc.stderr, encoding='utf-8')

    if proc.returncode != 0:
        raise RuntimeError(
            f'Multiwfn exited with code {proc.returncode} for {row.system_label}. '
            f'See {stdout_path} and {stderr_path}.'
        )

    parsed = parse_multiwfn_output(proc.stdout)
    record = make_json_record(row, base_dir, config.multiwfn_binary, raw_dir, parsed)
    row.json_path.parent.mkdir(parents=True, exist_ok=True)
    temp_json = row.json_path.with_suffix(row.json_path.suffix + '.tmp')
    if temp_json.exists():
        temp_json.unlink()
    temp_json.write_text(json.dumps(record, indent=2, sort_keys=False) + '\n', encoding='utf-8')
    temp_json.replace(row.json_path)
    return record


def main(argv: Iterable[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        rows = load_manifest(config.manifest_csv)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 2

    _write_summary_header_if_needed(config.summary_path)
    base_dir = config.manifest_csv.parent
    total = len(rows)
    progress_write(f'Loaded {total} topology rows from {config.manifest_csv}')
    progress_write(
        f'Multiwfn binary: {config.multiwfn_binary}, nproc={config.nproc}, timeout={config.timeout_sec}s'
    )
    if not config.no_progress and not tqdm_available():
        progress_write('tqdm is not available; using plain text status messages.')
    exit_code = 0

    row_iter = iter_progress(rows, total=total, desc='multiwfn topology', disable=config.no_progress, unit='system')
    for index, row in enumerate(row_iter, start=1):
        if hasattr(row_iter, 'set_postfix_str'):
            row_iter.set_postfix_str(row.system_label)
        portable_molden = _portable_path(row.molden_path, base_dir)
        portable_json = _portable_path(row.json_path, base_dir)
        prefix = f'[{index}/{total}] {row.system_label}'

        if row.json_path.exists() and not config.overwrite:
            progress_write(f'{prefix} -> skipped (output exists)')
            append_summary(
                config.summary_path,
                [row.system_label, 'skipped_existing', portable_molden, portable_json, '', '', '', '', '', '', 'output exists; use --overwrite to regenerate'],
            )
            continue

        temp_json = row.json_path.with_suffix(row.json_path.suffix + '.tmp')
        for stale in (row.json_path, temp_json):
            if stale.exists() and config.overwrite:
                stale.unlink()

        try:
            record = run_multiwfn(row, config, base_dir)
            counts = record['counts']
            poincare_result = ''
            if isinstance(record.get('poincare_hopf'), dict):
                poincare_result = record['poincare_hopf'].get('result', '')
            progress_write(
                f"{prefix} -> success, CP counts: ncp={counts.get('ncp', '')}, bcp={counts.get('bcp', '')}, rcp={counts.get('rcp', '')}, ccp={counts.get('ccp', '')}"
            )
            append_summary(
                config.summary_path,
                [
                    row.system_label,
                    'success',
                    portable_molden,
                    portable_json,
                    record['software'].get('multiwfn_version', ''),
                    counts.get('ncp', ''),
                    counts.get('bcp', ''),
                    counts.get('rcp', ''),
                    counts.get('ccp', ''),
                    poincare_result,
                    'ok',
                ],
            )
        except Exception as exc:  # noqa: BLE001
            progress_write(f'{prefix} -> error: {exc}', stream=sys.stderr)
            if row.json_path.exists():
                row.json_path.unlink()
            if temp_json.exists():
                temp_json.unlink()
            append_summary(
                config.summary_path,
                [row.system_label, 'error', portable_molden, portable_json, '', '', '', '', '', '', str(exc)],
            )
            append_error(config.error_log, row.system_label, exc)
            exit_code = 1
    progress_write(f'Finished Multiwfn topology stage with exit code {exit_code}. Summary: {config.summary_path}')
    if exit_code != 0:
        progress_write(f'Errors were recorded in: {config.error_log}', stream=sys.stderr)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
