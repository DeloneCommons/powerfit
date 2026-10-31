#!/usr/bin/env python3
"""Historical v1.0.0 figure checks; current figures use check_manuscript_figures.py.

Verify byte-stable figure outputs for a representative generator subset.

This script is intentionally separate from ``check_repo_consistency.py``. It
reruns a small representative subset of the figure generators twice inside a
throwaway temporary directory and compares the resulting file hashes. The
intended guarantee is narrow: identical bytes are expected only for the same
repo revision in the same locked Python environment.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
DEFAULT_QTAIM_MANIFEST = Path('data/qtaim_main/systems_final.csv')
DEFAULT_EXACT_RECOVERY_RUNS = Path('results/exact_recovery/runs.csv')


@dataclass(frozen=True)
class FigureCase:
    """Description of one deterministic-figure check case.

    Args:
        name: Short case name used in console output and temp directories.
        description: Human-readable summary of what the case covers.
        build_command: Callable that returns the command to execute for one run.
        expected_outputs: Callable that returns the output files to hash for one
            run directory.
    """

    name: str
    description: str
    build_command: Callable[[Path], list[str]]
    expected_outputs: Callable[[Path], list[Path]]


@dataclass(frozen=True)
class OutputDigest:
    """Digest summary for one generated file."""

    relpath: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class CaseResult:
    """Outcome of one case comparison."""

    case: FigureCase
    outputs: list[OutputDigest]


def _sha256(path: Path) -> str:
    """Return the SHA256 digest of a file.

    Args:
        path: File to hash.

    Returns:
        Hexadecimal SHA256 digest string.
    """
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _run_case(case: FigureCase, run_dir: Path, *, verbose: bool) -> CaseResult:
    """Execute one figure generator case and collect file hashes.

    Args:
        case: Case definition to execute.
        run_dir: Temporary directory reserved for this run.
        verbose: Whether to print the full command line before running.

    Returns:
        File digests for the expected outputs.

    Raises:
        FileNotFoundError: If any expected output is missing.
        subprocess.CalledProcessError: If the generator command fails.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = case.build_command(run_dir)
    if verbose:
        display = ' '.join(str(part) for part in cmd)
        print(f'[constancy] {case.name}: {display}', flush=True)
    env = dict(os.environ)
    env.setdefault('MPLBACKEND', 'Agg')
    subprocess.run(cmd, cwd=REPO_ROOT, check=True, env=env)

    digests: list[OutputDigest] = []
    for output in case.expected_outputs(run_dir):
        if not output.is_file():
            raise FileNotFoundError(
                f'Expected output was not created for case {case.name}: {output}'
            )
        digests.append(
            OutputDigest(
                relpath=output.relative_to(run_dir),
                sha256=_sha256(output),
                size_bytes=output.stat().st_size,
            )
        )
    return CaseResult(case=case, outputs=digests)


def _compare_results(first: CaseResult, second: CaseResult) -> list[str]:
    """Compare two runs of the same case.

    Args:
        first: Digest set from the first run.
        second: Digest set from the second run.

    Returns:
        Human-readable mismatch descriptions. Empty means success.
    """
    mismatches: list[str] = []
    second_map = {digest.relpath: digest for digest in second.outputs}
    for digest in first.outputs:
        relpath = digest.relpath
        other = second_map.get(relpath)
        if other is None:
            mismatches.append(
                f'{first.case.name}: missing output in second run: {relpath}'
            )
            continue
        if digest.sha256 != other.sha256:
            mismatches.append(
                f'{first.case.name}: hash mismatch for {relpath} '
                f'({digest.sha256} != {other.sha256})'
            )
        if digest.size_bytes != other.size_bytes:
            mismatches.append(
                f'{first.case.name}: size mismatch for {relpath} '
                f'({digest.size_bytes} != {other.size_bytes})'
            )
    return mismatches


def _normalize_outputs(base_dir: Path, outputs: Iterable[Path]) -> list[Path]:
    """Return outputs sorted by stable run-local path.

    Args:
        base_dir: Run directory that contains the outputs.
        outputs: Output paths to normalize.

    Returns:
        Sorted list of absolute paths.
    """
    return sorted(outputs, key=lambda path: str(path.relative_to(base_dir)))


def _manuscript_cases() -> list[FigureCase]:
    """Return manuscript-facing figure-generator checks."""
    return [
        FigureCase(
            name='workflow-schematic',
            description='workflow overview PNG/PDF pair',
            build_command=lambda run_dir: [
                PYTHON,
                'scripts/make_workflow_schematic.py',
                '--figure-path',
                str(run_dir / 'figure_powerfit_workflow_overview.png'),
            ],
            expected_outputs=lambda run_dir: _normalize_outputs(
                run_dir,
                [
                    run_dir / 'figure_powerfit_workflow_overview.png',
                    run_dir / 'figure_powerfit_workflow_overview.pdf',
                ],
            ),
        ),
        FigureCase(
            name='missing-data-manuscript',
            description='Experiment C composite PNG/PDF pair',
            build_command=lambda run_dir: [
                PYTHON,
                'experiments/analysis/plot_missing_data_manuscript.py',
                '--output-dir',
                str(run_dir / 'missing_data_analysis'),
                '--figure-path',
                str(run_dir / 'figure_C_missing_data_composite.png'),
            ],
            expected_outputs=lambda run_dir: _normalize_outputs(
                run_dir,
                [
                    run_dir / 'figure_C_missing_data_composite.png',
                    run_dir / 'figure_C_missing_data_composite.pdf',
                ],
            ),
        ),
        FigureCase(
            name='j4-geometry-cases',
            description='J4 geometry showcase PNG/PDF pair',
            build_command=lambda run_dir: [
                PYTHON,
                'scripts/make_j4_geometry_cases.py',
                '--output-pdf',
                str(run_dir / 'figure_J4_geometry_cases.pdf'),
                '--output-png',
                str(run_dir / 'figure_J4_geometry_cases.png'),
            ],
            expected_outputs=lambda run_dir: _normalize_outputs(
                run_dir,
                [
                    run_dir / 'figure_J4_geometry_cases.png',
                    run_dir / 'figure_J4_geometry_cases.pdf',
                ],
            ),
        ),
        FigureCase(
            name='j4-mask-transfer',
            description='J4 precision-recall PNG/PDF pair',
            build_command=lambda run_dir: [
                PYTHON,
                'scripts/make_j4_mask_transfer_figure.py',
                '--output-pdf',
                str(run_dir / 'figure_J4_mask_transfer.pdf'),
                '--output-png',
                str(run_dir / 'figure_J4_mask_transfer.png'),
            ],
            expected_outputs=lambda run_dir: _normalize_outputs(
                run_dir,
                [
                    run_dir / 'figure_J4_mask_transfer.png',
                    run_dir / 'figure_J4_mask_transfer.pdf',
                ],
            ),
        ),
    ]


def _representative_cases(
    *,
    qtaim_manifest: Path,
    exact_recovery_runs: Path,
) -> list[FigureCase]:
    """Return the representative cross-directory subset.

    Args:
        qtaim_manifest: Frozen QTAIM manifest used for the representative
            QTAIM plot-writer check.
        exact_recovery_runs: Frozen Experiment A runs CSV used for the
            representative analysis-plot check.

    Returns:
        List of case definitions.
    """
    cases = _manuscript_cases()
    cases.extend(
        [
            FigureCase(
                name='analysis-exact-recovery',
                description='Experiment A analysis PDFs',
                build_command=lambda run_dir: [
                    PYTHON,
                    'experiments/analysis/analyze_exact_recovery.py',
                    '--runs',
                    str(exact_recovery_runs),
                    '--output-dir',
                    str(run_dir),
                ],
                expected_outputs=lambda run_dir: _normalize_outputs(
                    run_dir,
                    [
                        run_dir / 'separator_rmse.pdf',
                        run_dir / 'edge_difference_rmse.pdf',
                        run_dir / 'centered_weight_rmse.pdf',
                    ],
                ),
            ),
            FigureCase(
                name='qtaim-dataset-audit',
                description='J1 audit representative PNG/PDF figures',
                build_command=lambda run_dir: [
                    PYTHON,
                    'scripts/qtaim/analyze_qtaim_dataset_audit.py',
                    str(qtaim_manifest),
                    '--output-dir',
                    str(run_dir),
                    '--no-progress',
                ],
                expected_outputs=lambda run_dir: _normalize_outputs(
                    run_dir,
                    [
                        run_dir / 'figures' / 'offset_histogram.png',
                        run_dir / 'figures' / 'offset_histogram.pdf',
                        run_dir / 'figures' / 'molecule_topology_flags.png',
                        run_dir / 'figures' / 'molecule_topology_flags.pdf',
                    ],
                ),
            ),
        ]
    )
    return cases


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--suite',
        choices=('manuscript', 'representative'),
        default='representative',
        help=(
            'Which generator subset to rerun twice. "manuscript" checks only '
            'the four manuscript-facing generators; "representative" adds one '
            'analysis generator and one QTAIM generator.'
        ),
    )
    parser.add_argument(
        '--qtaim-manifest',
        type=Path,
        default=DEFAULT_QTAIM_MANIFEST,
        help=(
            'Manifest used by the representative QTAIM case '
            '(default: data/qtaim_main/systems_final.csv).'
        ),
    )
    parser.add_argument(
        '--exact-recovery-runs',
        type=Path,
        default=DEFAULT_EXACT_RECOVERY_RUNS,
        help=(
            'Runs CSV used by the representative Experiment A analysis case '
            '(default: results/exact_recovery/runs.csv).'
        ),
    )
    parser.add_argument(
        '--keep-temp',
        action='store_true',
        help='Keep the temporary run directories for debugging.',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print the full command line for each run.',
    )
    return parser


def _resolve_repo_path(path: Path) -> Path:
    """Resolve a path relative to the repository root.

    Args:
        path: User-provided path.

    Returns:
        Absolute path.
    """
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def main(argv: Iterable[str] | None = None) -> int:
    """Run the configured determinism checks.

    Args:
        argv: Optional command-line argument sequence.

    Returns:
        Process exit code.
    """
    args = build_parser().parse_args(argv)
    qtaim_manifest = _resolve_repo_path(args.qtaim_manifest)
    exact_recovery_runs = _resolve_repo_path(args.exact_recovery_runs)

    if args.suite == 'representative':
        if not qtaim_manifest.is_file():
            raise SystemExit(f'QTAIM manifest not found: {qtaim_manifest}')
        if not exact_recovery_runs.is_file():
            raise SystemExit(
                f'Exact-recovery runs CSV not found: {exact_recovery_runs}'
            )
        cases = _representative_cases(
            qtaim_manifest=qtaim_manifest,
            exact_recovery_runs=exact_recovery_runs,
        )
    else:
        cases = _manuscript_cases()

    temp_root_obj: tempfile.TemporaryDirectory[str] | None = None
    if args.keep_temp:
        temp_root = (REPO_ROOT / '.tmp_figure_binary_constancy').resolve()
        if temp_root.exists():
            shutil.rmtree(temp_root)
        temp_root.mkdir(parents=True, exist_ok=True)
    else:
        temp_root_obj = tempfile.TemporaryDirectory(
            prefix='powerfit-figure-check-'
        )
        temp_root = Path(temp_root_obj.name)

    try:
        print(
            f'[constancy] suite={args.suite} | temp_root={temp_root}',
            flush=True,
        )
        mismatches: list[str] = []
        for case in cases:
            run1_dir = temp_root / case.name / 'run1'
            run2_dir = temp_root / case.name / 'run2'
            first = _run_case(case, run1_dir, verbose=args.verbose)
            second = _run_case(case, run2_dir, verbose=args.verbose)
            case_mismatches = _compare_results(first, second)
            mismatches.extend(case_mismatches)
            if case_mismatches:
                print(f'[constancy] FAIL {case.name}: {case.description}')
                for item in case_mismatches:
                    print(f'  - {item}')
            else:
                print(f'[constancy] PASS {case.name}: {case.description}')
                for digest in first.outputs:
                    print(
                        f'  - {digest.relpath} '
                        f'| sha256={digest.sha256[:12]}... '
                        f'| size={digest.size_bytes}',
                        flush=True,
                    )
        if mismatches:
            print('[constancy] figure binary constancy check FAILED', flush=True)
            return 1
        print('[constancy] figure binary constancy check passed', flush=True)
        return 0
    finally:
        if temp_root_obj is not None:
            temp_root_obj.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
