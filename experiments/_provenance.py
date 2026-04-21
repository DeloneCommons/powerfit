"""Runtime provenance helpers for experiment metadata."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERSION_FILE = _REPO_ROOT / 'external_software' / 'pyvoro2-version.txt'


def _safe_version(module_name: str) -> str | None:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    return getattr(module, '__version__', None)


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _parse_version_file(path: Path = _VERSION_FILE) -> dict[str, Any]:
    if not path.exists():
        return {}
    out: dict[str, Any] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        value = value.strip()
        if not value:
            continue
        key = key.strip().lower().replace(' ', '_').replace('/', '_')
        out[key] = value
    artifact = out.get('artifact_file')
    if artifact:
        artifact_path = path.parent / artifact
        try:
            relative_artifact_path = artifact_path.relative_to(_REPO_ROOT)
            out['artifact_path'] = relative_artifact_path.as_posix()
        except ValueError:
            out['artifact_path'] = str(artifact_path)
        out['artifact_sha256_actual'] = _sha256(artifact_path)
    return out


def _git_info(repo_root: Path = _REPO_ROOT) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            res = subprocess.run(
                args,
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            return None
        return res.stdout.strip() or None

    commit = run('git', 'rev-parse', 'HEAD')
    dirty = run('git', 'status', '--porcelain')
    branch = run('git', 'rev-parse', '--abbrev-ref', 'HEAD')
    return {
        'git_commit': commit,
        'git_branch': branch,
        'git_dirty': bool(dirty) if dirty is not None else None,
    }


def build_runtime_provenance(repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = _REPO_ROOT if repo_root is None else Path(repo_root)
    package_versions = {
        'pyvoro2': _safe_version('pyvoro2'),
        'numpy': _safe_version('numpy'),
        'pandas': _safe_version('pandas'),
        'scipy': _safe_version('scipy'),
        'matplotlib': _safe_version('matplotlib'),
        'yaml': _safe_version('yaml'),
        'jinja2': _safe_version('jinja2'),
    }
    return {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'python': {
            'version': sys.version.split()[0],
            'executable': Path(sys.executable).name,
            'implementation': platform.python_implementation(),
        },
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'machine': platform.machine(),
        },
        'package_versions': package_versions,
        'pyvoro2_artifact': _parse_version_file(_VERSION_FILE),
        'git': _git_info(repo_root),
        'nondeterministic_columns': ['runtime_sec'],
    }


def dumps_runtime_provenance(repo_root: Path | None = None) -> str:
    return json.dumps(build_runtime_provenance(repo_root=repo_root), indent=2)
