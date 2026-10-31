#!/usr/bin/env python3
"""Fast repository-integrity checks for the frozen paper artifact.

This helper is intentionally lightweight. It checks the issues that most often
make a reproducibility archive frustrating to navigate or easy to break when it
is moved between machines:

- broken relative markdown links;
- leaked machine-specific absolute paths in text artifacts;
- canonical manuscript source dependencies;
- missing documented Python runtime requirements;
- mismatched digests for pinned third-party binary artifacts;
- missing, changed, or added files in the frozen scientific artifact.

The script is safe to run locally or in CI. It exits with status 0 only when
all checks pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

MARKDOWN_SUFFIX = ".md"
BINARY_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".whl",
    ".zip",
    ".gz",
    ".xz",
    ".bz2",
    ".7z",
    ".tar",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".a",
    ".o",
    ".pyc",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".xyz",
}
TEXT_SCAN_SUFFIXES = {
    ".md",
    ".tex",
    ".py",
    ".sh",
    ".yml",
    ".yaml",
    ".json",
    ".csv",
    ".txt",
    ".ini",
    ".cfg",
    ".bib",
}
SKIP_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "ENV", "__pycache__", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".ipynb_checkpoints",
}
SKIP_ROOT_DIR_NAMES = {"build", ".smoke", ".tmp_figure_binary_constancy"}
FROZEN_MANIFEST_PATH = Path("scripts/frozen_artifacts.sha256.json")
FROZEN_DIRECTORIES = (
    "experiments", "results", "data", "environments", "external_software",
    "scripts/qtaim",
)
FROZEN_FILES = ("scripts/_figure_io.py",)
FROZEN_CACHE_DIR_NAMES = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".ipynb_checkpoints",
}
ABSOLUTE_PATH_ALLOWLIST = {
    Path("external_software/settings.ini"),
    Path("scripts/check_repo_consistency.py"),
}
ABSOLUTE_PATH_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/mnt/[\w./-]*"), "workspace path"),
    (re.compile(r"/home/[^\s/]+/[\w./-]*"), "home-directory path"),
    (re.compile(r"/Users/[^\s/]+/[\w./-]*"), "macOS home-directory path"),
    (re.compile(r"/private/tmp/[\w./-]*"), "macOS temp path"),
    (re.compile(r"/var/folders/[\w./-]*"), "macOS temp path"),
    (re.compile(r"C:\\\\Users\\[^\s\\]+(?:\\[\w .-]+)*"), "Windows user path"),
    (re.compile(r"/tmp/powerfit_smoke[\w./-]*"), "repo-specific temp path"),
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

BINARY_MANIFEST_EXPECTATIONS: dict[Path, dict[str, str]] = {
    Path("external_software/pyvoro2-version.txt"): {
        "artifact_field": "artifact file",
        "sha256_field": "sha256",
        "label": "bundled pyvoro2 wheel",
    },
    Path("external_software/multiwfn-version.txt"): {
        "artifact_field": "artifact file",
        "sha256_field": "sha256",
        "label": "bundled Multiwfn executable",
    },
}


REQUIREMENT_EXPECTATIONS: dict[Path, dict[str, str]] = {
    Path("environments/requirements-py313.txt"): {
        "numpy": "numerical kernels used by benchmark and figure helpers",
        "scipy": "linear algebra and numerical utilities used by the experiment layer",
        "pandas": "archived-result aggregation and manuscript-table generation",
        "matplotlib": "manuscript figure generation",
        "pyyaml": "YAML protocol loading",
        "jinja2": "table-generation templating support",
        "rdkit": "committed-data Experiment J analyses",
        "tqdm": "optional progress bars used by the committed-data Experiment J analyses",
    },
    Path("environments/requirements-qtaim.txt"): {
        "pyscf": "optional quantum-chemistry helper scripts",
        "geometric": "optional PySCF geometry-optimization backend",
        "rdkit": "optional molecular graph helpers",
        "scipy": "optional QTAIM helper numerics",
        "pandas": "optional QTAIM helper aggregation",
        "tqdm": "optional QTAIM helper progress bars",
    },
}


@dataclass(frozen=True)
class Problem:
    path: str
    detail: str


def _repo_rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _iter_candidate_files() -> Iterable[Path]:
    # Prune before descending: archives, smoke reports, and installed packages
    # are generated outputs, not repository sources to audit.
    for directory, children, names in os.walk(REPO_ROOT, followlinks=False):
        parent = Path(directory)
        excluded = SKIP_DIR_NAMES | (SKIP_ROOT_DIR_NAMES if parent == REPO_ROOT else set())
        children[:] = sorted(
            name for name in children
            if name not in excluded and not (parent / name).is_symlink()
        )
        for name in sorted(names):
            path = parent / name
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            if path.suffix and path.suffix.lower() not in TEXT_SCAN_SUFFIXES:
                continue
            yield path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _check_markdown_links() -> list[Problem]:
    problems: list[Problem] = []
    for md_path in _iter_candidate_files():
        if md_path.suffix.lower() != MARKDOWN_SUFFIX:
            continue
        text = _read_text(md_path)
        for raw_target in MARKDOWN_LINK_RE.findall(text):
            target = raw_target.strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0].split("?", 1)[0].strip()
            if not target:
                continue
            resolved = (md_path.parent / target).resolve()
            if not resolved.exists():
                problems.append(Problem(_repo_rel(md_path), f"broken markdown link: {raw_target}"))
    return problems


def _check_absolute_paths() -> list[Problem]:
    problems: list[Problem] = []
    for path in _iter_candidate_files():
        repo_rel = Path(_repo_rel(path))
        if repo_rel in ABSOLUTE_PATH_ALLOWLIST:
            continue
        text = _read_text(path)
        for pattern, label in ABSOLUTE_PATH_PATTERNS:
            match = pattern.search(text)
            if match:
                snippet = match.group(0)
                problems.append(Problem(_repo_rel(path), f"{label}: {snippet}"))
                break
    return problems


def _check_manuscript_dependencies() -> list[Problem]:
    relative = Path("scripts/check_manuscript.py")
    script = REPO_ROOT / relative
    if not script.is_file():
        return [Problem(relative.as_posix(), "missing manuscript source checker")]
    try:
        result = subprocess.run(
            [sys.executable, str(script)], cwd=REPO_ROOT,
            text=True, capture_output=True, check=False,
        )
    except OSError as exc:
        return [Problem(relative.as_posix(), f"cannot run manuscript source checker: {exc}")]
    if result.returncode:
        detail = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        return [Problem(relative.as_posix(), detail or f"source checker exited with status {result.returncode}")]
    return []



def _parse_simple_manifest(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in _read_text(path).splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _sha256_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _check_frozen_artifacts() -> list[Problem]:
    """Verify the recorded Git baseline without requiring Git at runtime.

    The manifest is an archival record, not a cache to refresh after changes.
    Only Python/tool caches are ignored inside protected directories; new
    scientific files must not silently become part of the frozen snapshot.
    """
    manifest_name = FROZEN_MANIFEST_PATH.as_posix()
    try:
        payload = json.loads((REPO_ROOT / FROZEN_MANIFEST_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Problem(manifest_name, f"cannot read frozen artifact manifest: {exc}")]
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return [Problem(manifest_name, "invalid frozen artifact manifest schema")]
    if (
        payload.get("protected_directories") != list(FROZEN_DIRECTORIES)
        or payload.get("protected_files") != list(FROZEN_FILES)
        or not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("baseline_commit", "")))
    ):
        return [Problem(manifest_name, "invalid protected paths or baseline commit in frozen artifact manifest")]
    entries = payload.get("files")
    if not isinstance(entries, dict) or not entries:
        return [Problem(manifest_name, "invalid or empty files map in frozen artifact manifest")]

    problems: list[Problem] = []
    for relative, digest in entries.items():
        path = Path(relative)
        protected = relative in FROZEN_FILES or any(
            relative.startswith(directory + "/") for directory in FROZEN_DIRECTORIES
        )
        if (
            path.is_absolute() or ".." in path.parts or "\\" in relative
            or path.as_posix() != relative or not protected
        ):
            problems.append(Problem(manifest_name, f"invalid frozen artifact path: {relative!r}"))
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            problems.append(Problem(manifest_name, f"invalid SHA256 digest for {relative!r}"))
    for directory in FROZEN_DIRECTORIES:
        if not any(relative.startswith(directory + "/") for relative in entries):
            problems.append(Problem(manifest_name, f"invalid manifest: no entries for {directory}"))
    for relative in FROZEN_FILES:
        if relative not in entries:
            problems.append(Problem(manifest_name, f"invalid manifest: missing entry for {relative}"))
    if problems:
        return problems

    for relative, expected in sorted(entries.items()):
        path = REPO_ROOT / relative
        if any((REPO_ROOT / part).is_symlink() for part in [Path(relative), *Path(relative).parents] if part != Path(".")):
            problems.append(Problem(relative, "symlink cannot replace a frozen artifact"))
        elif not path.is_file():
            problems.append(Problem(relative, "missing frozen artifact"))
        else:
            try:
                actual = _sha256_digest(path)
            except OSError as exc:
                problems.append(Problem(relative, f"cannot read frozen artifact: {exc}"))
                continue
            if actual != expected:
                problems.append(Problem(relative, f"frozen artifact digest mismatch: expected {expected}, got {actual}"))

    for protected in FROZEN_DIRECTORIES:
        start = REPO_ROOT / protected
        if start.is_symlink():
            problems.append(Problem(protected, "symlink cannot replace a frozen directory"))
            continue
        for directory, children, names in os.walk(start, followlinks=False):
            parent = Path(directory)
            retained = []
            for name in sorted(children):
                if name in FROZEN_CACHE_DIR_NAMES:
                    continue
                path = parent / name
                if path.is_symlink():
                    problems.append(Problem(_repo_rel(path), "unexpected symlink in frozen directory"))
                else:
                    retained.append(name)
            children[:] = retained
            for name in sorted(names):
                path = parent / name
                if path.suffix in {".pyc", ".pyo"}:
                    continue
                relative = _repo_rel(path)
                if relative not in entries:
                    problems.append(Problem(relative, "unexpected file in frozen directory (absent from baseline manifest)"))
    return problems


def _check_bundled_binary_hashes() -> list[Problem]:
    problems: list[Problem] = []
    for rel_manifest_path, expected in BINARY_MANIFEST_EXPECTATIONS.items():
        manifest_path = REPO_ROOT / rel_manifest_path
        label = expected["label"]
        if not manifest_path.is_file():
            problems.append(
                Problem(rel_manifest_path.as_posix(), f"missing manifest for {label}")
            )
            continue

        fields = _parse_simple_manifest(manifest_path)
        artifact_name = fields.get(expected["artifact_field"].lower())
        expected_digest = fields.get(expected["sha256_field"].lower())
        if not artifact_name:
            problems.append(
                Problem(
                    rel_manifest_path.as_posix(),
                    f"manifest is missing {expected['artifact_field']!r}",
                )
            )
            continue
        if not expected_digest:
            problems.append(
                Problem(
                    rel_manifest_path.as_posix(),
                    f"manifest is missing {expected['sha256_field']!r}",
                )
            )
            continue

        artifact_path = manifest_path.parent / artifact_name
        if not artifact_path.is_file():
            problems.append(
                Problem(
                    _repo_rel(manifest_path),
                    f"declared {label} does not exist: {artifact_name}",
                )
            )
            continue

        normalized_expected = expected_digest.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_expected):
            problems.append(
                Problem(
                    _repo_rel(manifest_path),
                    f"manifest digest is not a valid SHA256 hex string: {expected_digest}",
                )
            )
            continue

        actual_digest = _sha256_digest(artifact_path)
        if actual_digest != normalized_expected:
            problems.append(
                Problem(
                    _repo_rel(artifact_path),
                    f"{label} digest mismatch: expected {normalized_expected}, got {actual_digest}",
                )
            )
    return problems


def _canonical_requirement_name(line: str) -> str | None:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "--")):
        return None
    if line.startswith(("git+", "http://", "https://")):
        return None
    line = line.split(";", 1)[0].strip()
    line = line.split("[", 1)[0].strip()
    name = re.split(r"[<>=!~]", line, maxsplit=1)[0].strip()
    if not name:
        return None
    return name.lower().replace("_", "-")


def _load_requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in _read_text(path).splitlines():
        name = _canonical_requirement_name(raw_line)
        if name is not None:
            names.add(name)
    return names


def _check_requirements() -> list[Problem]:
    problems: list[Problem] = []
    for rel_path, expected in REQUIREMENT_EXPECTATIONS.items():
        path = REPO_ROOT / rel_path
        if not path.is_file():
            problems.append(Problem(rel_path.as_posix(), "requirements file is missing"))
            continue
        names = _load_requirement_names(path)
        for package, role in sorted(expected.items()):
            if package not in names:
                problems.append(
                    Problem(
                        rel_path.as_posix(),
                        f"missing requirement {package!r} ({role})",
                    )
                )
    return problems


def _print_group(title: str, problems: list[Problem]) -> None:
    print(f"[{title}] {len(problems)} issue(s)")
    for problem in problems:
        print(f"  - {problem.path}: {problem.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-frozen", action="store_true",
        help="Skip archived scientific-file digests after an explicitly requested full rerun; keep all other checks.",
    )
    args = parser.parse_args(argv)
    groups = [
        ("markdown-links", _check_markdown_links()),
        ("absolute-paths", _check_absolute_paths()),
        ("manuscript", _check_manuscript_dependencies()),
        ("requirements", _check_requirements()),
        ("bundled-binaries", _check_bundled_binary_hashes()),
    ]
    if args.skip_frozen:
        print("[frozen-artifacts] skipped by explicit --skip-frozen; the baseline manifest is unchanged.")
    else:
        groups.append(("frozen-artifacts", _check_frozen_artifacts()))
    if any(problems for _, problems in groups):
        print("Repository consistency check failed.")
        for title, problems in groups:
            if problems:
                _print_group(title, problems)
        return 1

    n_scanned = sum(1 for _ in _iter_candidate_files())
    print(
        "Repository consistency check passed: "
        f"{n_scanned} text-like files scanned, markdown links resolved, "
        "requirements documented, bundled binary digests verified, "
        "and canonical manuscript sources validated."
    )
    if not args.skip_frozen:
        print("[frozen-artifacts] all archived file digests match; no scientific files added or removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
