#!/usr/bin/env python3
"""Build a source-only arXiv ZIP, preserving the canonical relative paths.

This creates a local archive; it does not submit or publish anything. The pinned
elsarticle class/style and their source notices are included; other standard
LaTeX packages remain distribution dependencies.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import zipfile

from check_manuscript import check_bibliography, check_sources, collect_dependencies

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_bundle(manuscript_dir: Path, output: Path) -> None:
    errors = check_sources(manuscript_dir) + check_bibliography(manuscript_dir)
    if errors:
        raise ValueError("Cannot package invalid manuscript: " + "; ".join(errors))
    files = collect_dependencies(manuscript_dir)
    files.append((manuscript_dir / "manuscript.bbl").resolve())
    output = output.resolve()
    if output in files:
        raise ValueError("Archive output would overwrite a manuscript dependency")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            relative = path.relative_to(manuscript_dir.resolve()).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    print(f"Created {output} ({len(files)} source files; nested paths preserved).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "build/powerfit-arxiv.zip")
    args = parser.parse_args()
    # Always refresh the bibliography before packaging: no stale tracked .bbl.
    subprocess.run(["bash", str(REPO_ROOT / "scripts/build_manuscript_pdfs.sh")], check=True)
    write_bundle(REPO_ROOT / "manuscript", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
