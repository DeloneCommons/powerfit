#!/usr/bin/env python3
"""Capture the exact release-time environment snapshot for the paper artifact.

This helper is intentionally separate from the ordinary rerun/build path. Use it
once from the clean environment you want to archive, typically just before the
final GitHub/Zenodo/arXiv freeze. It writes:

- ``environments/system.txt`` with a concise, machine-independent system note;
- ``environments/requirements-lock-py313.txt`` with the exact Python
  distributions visible to the active interpreter.

The script does not attempt to rebuild experiments or the manuscript. It merely
records the environment already in use.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSTEM_OUTPUT = REPO_ROOT / 'environments' / 'system.txt'
DEFAULT_LOCK_OUTPUT = REPO_ROOT / 'environments' / 'requirements-lock-py313.txt'
MINIMAL_REQUIREMENTS = Path('environments/requirements-py313.txt')
DEV_REQUIREMENTS = Path('environments/requirements-dev.txt')
QTAIM_REQUIREMENTS = Path('environments/requirements-qtaim.txt')
BUNDLED_WHEEL = Path(
    'external_software/'
    'pyvoro2-0.6.3-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl'
)


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            'Write the release-time environment snapshot files under '
            'environments/.'
        )
    )
    parser.add_argument(
        '--system-output',
        type=Path,
        default=DEFAULT_SYSTEM_OUTPUT,
        help='Path to the system note to overwrite.',
    )
    parser.add_argument(
        '--lock-output',
        type=Path,
        default=DEFAULT_LOCK_OUTPUT,
        help='Path to the exact Python lock file to overwrite.',
    )
    return parser.parse_args()


def _repo_relative(path: Path) -> str:
    """Return a repository-relative POSIX path string.

    Args:
        path: Path inside the repository.

    Returns:
        Repository-relative POSIX string.
    """
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def _ensure_parent(path: Path) -> None:
    """Create the output parent directory if needed.

    Args:
        path: Output file path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def _run_text_command(args: list[str]) -> str | None:
    """Run a command and return combined stdout/stderr text.

    Args:
        args: Command-line vector.

    Returns:
        Combined command output on success, or ``None`` if the command is not
        available or exits unsuccessfully.
    """
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text or None


def _first_line(text: str | None) -> str:
    """Return the first non-empty output line.

    Args:
        text: Command output.

    Returns:
        First non-empty line, or ``'unavailable'`` when absent.
    """
    if not text:
        return 'unavailable'
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return 'unavailable'


def _detect_execution_environment() -> str:
    """Summarize the current execution environment.

    Returns:
        Human-readable environment summary without machine-specific paths.
    """
    if platform.system() == 'Linux':
        proc_version = ''
        proc_path = Path('/proc/version')
        if proc_path.is_file():
            proc_version = proc_path.read_text(encoding='utf-8').lower()
        if os.environ.get('WSL_DISTRO_NAME') or 'microsoft' in proc_version:
            return 'WSL2 on Windows'
        return 'Linux'
    if platform.system() == 'Darwin':
        return 'macOS'
    if platform.system() == 'Windows':
        return 'Windows'
    return platform.system() or 'unknown'


def _pip_version() -> str:
    """Return the current ``pip`` version string.

    Returns:
        ``pip`` version, or ``'unavailable'`` when it cannot be determined.
    """
    text = _run_text_command([sys.executable, '-m', 'pip', '--version'])
    if not text:
        return 'unavailable'
    match = re.search(r'pip\s+([^\s]+)', text)
    if match is None:
        return 'unavailable'
    return match.group(1)


def _sorted_distributions() -> list[tuple[str, str, str]]:
    """Collect installed Python distributions.

    Returns:
        Sorted tuples of ``(normalized_name, display_name, version)``.
    """
    records: dict[str, tuple[str, str]] = {}
    for dist in metadata.distributions():
        name = dist.metadata.get('Name') or dist.name or ''
        version = dist.version
        normalized = re.sub(r'[-_.]+', '-', name).lower()
        if not normalized:
            continue
        current = records.get(normalized)
        if current is None or len(name) < len(current[0]):
            records[normalized] = (name, version)
    return [
        (normalized, display_name, version)
        for normalized, (display_name, version) in sorted(records.items())
    ]


def _render_lock_text() -> str:
    """Render the exact Python lock file.

    Returns:
        Text for ``requirements-lock-py313.txt``.
    """
    lines = [
        '# Exact Python package snapshot for the frozen paper artifact.',
        '# Generated by scripts/capture_environment_snapshot.py from the',
        '# active interpreter environment.',
        '#',
        '# Generate this file from a clean release-time virtual environment',
        '# so it does not capture unrelated packages.',
        '# Minimal top-level requirements remain in',
        '# environments/requirements-py313.txt.',
        '',
    ]
    for _, display_name, version in _sorted_distributions():
        lines.append(f'{display_name}=={version}')
    lines.append('')
    return '\n'.join(lines)


def _tool_summary() -> dict[str, str]:
    """Collect concise tool version summaries.

    Returns:
        Mapping from tool name to short version string.
    """
    return {
        'latexmk': _first_line(_run_text_command(['latexmk', '-v'])),
        'bibtex': _first_line(_run_text_command(['bibtex', '--version'])),
        'pip': _pip_version(),
    }


def _render_system_text(lock_output: Path) -> str:
    """Render the repository system note.

    Args:
        lock_output: Output path for the exact Python lock file.

    Returns:
        Text for ``system.txt``.
    """
    libc_name, libc_version = platform.libc_ver()
    libc_text = 'unavailable'
    if libc_name:
        libc_text = f'{libc_name} {libc_version}'.strip()
    tools = _tool_summary()
    lines = [
        'Reference environment used for the frozen repository snapshot',
        '===========================================================',
        '',
        'Generated by: scripts/capture_environment_snapshot.py',
        f'Python: {platform.python_version()}',
        f'Python implementation: {platform.python_implementation()}',
        f'Operating system: {platform.system() or "unknown"}',
        f'OS release: {platform.release() or "unknown"}',
        f'Machine: {platform.machine() or "unknown"}',
        f'Execution environment: {_detect_execution_environment()}',
        f'libc: {libc_text}',
        f'latexmk: {tools["latexmk"]}',
        f'bibtex: {tools["bibtex"]}',
        f'pip: {tools["pip"]}',
        f'Bundled wheel path: {BUNDLED_WHEEL.as_posix()}',
        f'Python requirements: {MINIMAL_REQUIREMENTS.as_posix()}',
        f'Locked Python environment: {_repo_relative(lock_output)}',
        f'Optional extras: {DEV_REQUIREMENTS.as_posix()}',
        f'Optional QTAIM helpers: {QTAIM_REQUIREMENTS.as_posix()}',
        '',
        'The lock file records the exact Python distributions visible to the',
        'active interpreter when this snapshot was generated. Create it from a',
        'clean release environment to avoid capturing unrelated packages.',
        '',
        'The bundled wheel is manylinux and therefore Linux-oriented. On other',
        'platforms, use pyvoro2==0.6.3 from PyPI (or build the same version from',
        'source) together with the same Python requirements.',
        '',
    ]
    return '\n'.join(lines)


def _write_text(path: Path, text: str) -> None:
    """Write UTF-8 text to disk.

    Args:
        path: Output file path.
        text: File content.
    """
    _ensure_parent(path)
    path.write_text(text, encoding='utf-8')


def main() -> int:
    """Run the environment snapshot helper.

    Returns:
        Process exit status.
    """
    args = _parse_args()
    system_output = args.system_output.resolve()
    lock_output = args.lock_output.resolve()

    try:
        lock_rel = lock_output.relative_to(REPO_ROOT)
        system_output.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise SystemExit(
            'Both --system-output and --lock-output must stay inside the '
            'repository root.'
        ) from exc

    _write_text(lock_output, _render_lock_text())
    _write_text(system_output, _render_system_text(lock_output))

    print(
        '[env] wrote exact Python lock file to '
        f'{lock_rel.as_posix()}'
    )
    print(
        '[env] wrote system snapshot to '
        f'{_repo_relative(system_output)}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
