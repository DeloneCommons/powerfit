#!/usr/bin/env python3
"""Reproduce all seven canonical manuscript PDFs without rerunning experiments.

Use --output-dir to select a separate destination. An explicit build defaults
to manuscript/figures; validation belongs to check_manuscript_figures.py,
which always generates in temporary directories and preserves approved PDFs.
Frozen C/G inputs default to the repository's results/ tree. Historical
figures are isolated in build/legacy/ by build_legacy_figures.py.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
FIGURE_DIR = REPO_ROOT / "manuscript" / "figures"
FIGURE_NAMES = (
    "figure_02_separators.pdf",
    "figure_03_cycle.pdf",
    "figure_04_realization.pdf",
    "figure_05_workflow.pdf",
    "figure_C_identifiability.pdf",
    "figure_E_bcp_projection.pdf",
    "figure_G_mismatch.pdf",
)


def build_main_text_figures(
    *, output_dir: Path = FIGURE_DIR, results_root: Path | None = None,
    archive: Path | None = None, dry_run: bool = False,
) -> None:
    if results_root is not None and archive is not None:
        raise ValueError("Choose either an archive or a results root, not both")
    output_dir = output_dir.resolve()
    source_args = []
    if archive is not None:
        source_args = ["--archive", str(archive.resolve())]
    elif results_root is not None:
        source_args = ["--results-root", str(results_root.resolve())]
    environment = dict(os.environ)
    environment.setdefault("MPLCONFIGDIR", str(REPO_ROOT / "build/.cache/matplotlib"))
    for name, extra in (
        ("plot_theory_figures.py", []),
        ("plot_editorial_figures.py", source_args),
        ("plot_experiment_g.py", source_args),
    ):
        command = [sys.executable, str(REPO_ROOT / "scripts" / name),
                   "--output-dir", str(output_dir), *extra]
        print(f"[figures] {shlex.join(command)}", flush=True)
        if not dry_run:
            subprocess.run(command, cwd=REPO_ROOT, env=environment, check=True)
    if not dry_run:
        for name in FIGURE_NAMES:
            if not (output_dir / name).is_file():
                raise FileNotFoundError(f"The figure generator did not create {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=FIGURE_DIR,
                        help="Destination for the seven PDFs and auxiliary SVGs")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--results-root", type=Path,
                         help="Frozen results tree (default: repository results/)")
    sources.add_argument("--archive", type=Path, help="Frozen powerfit-80933a1 ZIP")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without creating or changing files")
    args = parser.parse_args()

    build_main_text_figures(output_dir=args.output_dir, results_root=args.results_root,
                            archive=args.archive, dry_run=args.dry_run)
    verb = "would generate" if args.dry_run else "generated"
    print(f"[figures] {verb} all seven PDFs in {args.output_dir.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
