#!/usr/bin/env python3
"""Fast repository-integrity checks for the frozen paper artifact.

This helper is intentionally lightweight. It checks the issues that most often
make a reproducibility archive frustrating to navigate or easy to break when it
is moved between machines:

- broken relative markdown links;
- leaked machine-specific absolute paths in text artifacts;
- submission-bundle dependency resolution and flat-name collisions;
- missing documented Python runtime requirements;
- mismatched digests for pinned third-party binary artifacts.

The script is safe to run locally or in CI. It exits with status 0 only when
all checks pass.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
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
SKIP_DIR_NAMES = {".git", ".venv", "__pycache__"}
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
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(REPO_ROOT).parts
        if any(part in SKIP_DIR_NAMES for part in parts):
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
    for md_path in REPO_ROOT.rglob(f"*{MARKDOWN_SUFFIX}"):
        if not md_path.is_file():
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


def _load_submission_module():
    module_path = REPO_ROOT / "scripts" / "make_submission_bundle.py"
    spec = importlib.util.spec_from_file_location("make_submission_bundle", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load submission helper from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_submission_dependencies() -> list[Problem]:
    problems: list[Problem] = []
    try:
        module = _load_submission_module()
        deps = list(module.collect_dependencies())
    except Exception as exc:  # pragma: no cover - surfaced in CLI output
        return [Problem("scripts/make_submission_bundle.py", f"dependency collection failed: {exc}")]

    seen_names: dict[str, Path] = {}
    for dep in deps:
        if not dep.exists():
            problems.append(Problem(_repo_rel(dep), "declared submission dependency does not exist"))
            continue
        name = dep.name
        other = seen_names.get(name)
        if other is not None and other.resolve() != dep.resolve():
            problems.append(
                Problem(
                    _repo_rel(dep),
                    f"flat-bundle name collision with {_repo_rel(other)} -> {name}",
                )
            )
        else:
            seen_names[name] = dep
    return problems



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


def main() -> int:
    markdown_problems = _check_markdown_links()
    absolute_path_problems = _check_absolute_paths()
    submission_problems = _check_submission_dependencies()
    requirements_problems = _check_requirements()
    bundled_binary_problems = _check_bundled_binary_hashes()

    total = (
        len(markdown_problems)
        + len(absolute_path_problems)
        + len(submission_problems)
        + len(requirements_problems)
        + len(bundled_binary_problems)
    )
    if total:
        print("Repository consistency check failed.")
        if markdown_problems:
            _print_group("markdown-links", markdown_problems)
        if absolute_path_problems:
            _print_group("absolute-paths", absolute_path_problems)
        if submission_problems:
            _print_group("submission-bundle", submission_problems)
        if requirements_problems:
            _print_group("requirements", requirements_problems)
        if bundled_binary_problems:
            _print_group("bundled-binaries", bundled_binary_problems)
        return 1

    n_scanned = sum(1 for _ in _iter_candidate_files())
    print(
        "Repository consistency check passed: "
        f"{n_scanned} text-like files scanned, markdown links resolved, "
        "requirements documented, bundled binary digests verified, and "
        "submission dependencies flattened cleanly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
