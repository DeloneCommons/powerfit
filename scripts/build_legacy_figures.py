#!/usr/bin/env python3
"""Regenerate historical figures into build/legacy/, away from canonical assets.

This preserves the original pre-revision figure build. Its outputs are not
inputs to the canonical manuscript. No archived results are overwritten.

The expensive molecular and experiment runs are not repeated here.  The
lightweight manuscript-facing schematics and summary plots are redrawn from
frozen source scripts or archived CSV outputs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
FIGURE_DIR = REPO_ROOT / "build" / "legacy" / "figures"
ANALYSIS_DIR = REPO_ROOT / "build" / "legacy" / "analysis"


def _run(cmd: Sequence[str], *, dry_run: bool = False) -> None:
    display = " ".join(str(part) for part in cmd)
    print(f"[figures] {display}", flush=True)
    if dry_run:
        return
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def build_main_text_figures(*, dry_run: bool = False) -> None:
    if not dry_run:
        FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    _run(
        [
            sys.executable,
            "scripts/make_workflow_schematic.py",
            "--figure-path",
            str(FIGURE_DIR / "figure_powerfit_workflow_overview.png"),
        ],
        dry_run=dry_run,
    )
    _run(
        [
            sys.executable,
            "experiments/analysis/plot_missing_data_manuscript.py",
            "--figure-path",
            str(FIGURE_DIR / "figure_C_missing_data_composite.png"),
            "--output-dir",
            str(ANALYSIS_DIR),
        ],
        dry_run=dry_run,
    )

    # J2 is summarized in Table J23 rather than as a main-text figure.  J4 is
    # redrawn from archived summaries so that the manuscript figure shows the
    # current geometry-first and precision--recall views without rerunning
    # molecular pipelines.

    _run(
        [
            sys.executable,
            "scripts/make_j4_geometry_cases.py",
            "--output-pdf",
            str(FIGURE_DIR / "figure_J4_geometry_cases.pdf"),
            "--output-png",
            str(FIGURE_DIR / "figure_J4_geometry_cases.png"),
        ],
        dry_run=dry_run,
    )
    _run(
        [
            sys.executable,
            "scripts/make_j4_mask_transfer_figure.py",
            "--output-pdf",
            str(FIGURE_DIR / "figure_J4_mask_transfer.pdf"),
            "--output-png",
            str(FIGURE_DIR / "figure_J4_mask_transfer.png"),
        ],
        dry_run=dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands/copies without modifying files.",
    )
    args = parser.parse_args()

    build_main_text_figures(dry_run=args.dry_run)
    verb = "would refresh" if args.dry_run else "refreshed"
    print(f"[figures] {verb} historical figures in {FIGURE_DIR.relative_to(REPO_ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
