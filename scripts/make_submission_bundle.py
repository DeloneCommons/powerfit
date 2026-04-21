#!/usr/bin/env python3
"""Create a flat journal-submission source bundle.

The manuscript tree may contain subdirectories (for example ``figures/`` or
``tables/``), but some submission systems expect uploaded LaTeX files to sit at
one folder level. This script parses ``manuscript.tex`` and copies only that
source file, its referenced figure/table dependencies, and the standard root
metadata files (bibliography, highlights, keywords, compiled ``.bbl``). The
bundle is intentionally source-only so that it cannot drift out of sync with an
older compiled PDF. PDF figures are preferred when both PDF and raster copies
exist.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT_DIR = REPO_ROOT / "manuscript"
OUTPUT_DIR = REPO_ROOT / "submission" / "flat"

TEXT_SUFFIXES = {".tex", ".bib", ".bbl", ".bst", ".cls", ".sty", ".txt"}
FIGURE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".eps", ".tif", ".tiff"}
ROOT_FILES = ["manuscript.tex", "refs.bib", "manuscript.bbl", "highlights.txt", "keywords.txt"]

INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
INPUT_RE = re.compile(r"\\input\{([^}]+)\}")


def _strip_comment(line: str) -> str:
    out = []
    escaped = False
    for ch in line:
        if ch == "\\":
            escaped = not escaped
            out.append(ch)
            continue
        if ch == "%" and not escaped:
            break
        escaped = False
        out.append(ch)
    return "".join(out)


def _read_tex(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return "\n".join(_strip_comment(line) for line in text.splitlines())


def _resolve(name: str, *, kind: str) -> Path:
    rel = Path(name)
    roots = [MANUSCRIPT_DIR]
    if kind == "input":
        roots.append(MANUSCRIPT_DIR / "tables")
        suffixes = [rel.suffix] if rel.suffix else [".tex"]
    else:
        roots.extend([MANUSCRIPT_DIR / "figures", MANUSCRIPT_DIR / "tables"])
        suffixes = [rel.suffix] if rel.suffix else [".pdf", ".png", ".jpg", ".jpeg", ".eps", ".tif", ".tiff"]
        # Prefer PDF for graphics when no extension is given.
        suffixes = sorted(set(suffixes), key=lambda s: (s != ".pdf", s))

    for root in roots:
        candidate = root / rel
        if candidate.suffix:
            if candidate.exists():
                return candidate
        else:
            for suffix in suffixes:
                resolved = candidate.with_suffix(suffix)
                if resolved.exists():
                    return resolved
    raise FileNotFoundError(f"Could not resolve {kind} dependency {name!r}")


def collect_dependencies() -> list[Path]:
    files: set[Path] = set()
    for name in ROOT_FILES:
        path = MANUSCRIPT_DIR / name
        if path.exists():
            files.add(path)

    queue = [MANUSCRIPT_DIR / "manuscript.tex"]
    seen_tex: set[Path] = set()
    while queue:
        tex_path = queue.pop()
        if tex_path in seen_tex:
            continue
        seen_tex.add(tex_path)
        files.add(tex_path)
        text = _read_tex(tex_path)
        for include_name in INPUT_RE.findall(text):
            dep = _resolve(include_name, kind="input")
            files.add(dep)
            if dep.suffix == ".tex":
                queue.append(dep)
        for graphic_name in INCLUDEGRAPHICS_RE.findall(text):
            dep = _resolve(graphic_name, kind="graphic")
            files.add(dep)

    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="Accepted for backward compatibility; the output directory is always recreated.")
    parser.parse_args()

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    seen_names: dict[str, Path] = {}
    copied = 0
    for src in collect_dependencies():
        if src.suffix.lower() not in TEXT_SUFFIXES | FIGURE_SUFFIXES:
            continue
        dst = OUTPUT_DIR / src.name
        if src.name in seen_names:
            other = seen_names[src.name]
            raise SystemExit(
                f"Name collision while flattening submission bundle: {src} and {other} would both map to {dst.name!r}."
            )
        seen_names[src.name] = src
        shutil.copy2(src, dst)
        copied += 1

    print(f"Created flat submission bundle in: {OUTPUT_DIR}")
    print(f"Copied {copied} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
