#!/usr/bin/env python3
"""Validate all seven approved figures without overwriting canonical PDFs.

Build twice in temporary directories using the current Python executable.
Require byte-identical outputs between these same-environment runs. Compare
each PDF with its approved counterpart by bytes, or by page/text geometry and
a full-page 300-dpi Poppler rendering. Across rendering versions the only
pixel tolerance is one pixel of edge movement and 8/255 channel levels; no
region or fraction of the image is excluded. Text must match exactly and its
bounding boxes must agree within 0.25 pt.

All figures must be vector PDFs without Type 3 fonts, with every font embedded.

Requires the paper's Python plotting dependencies and Poppler utilities
(pdftoppm, pdftotext, pdffonts and pdfimages).
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageFilter

from build_manuscript_figures import FIGURE_DIR, FIGURE_NAMES, REPO_ROOT


POPPLER_TOOLS = ("pdftoppm", "pdftotext", "pdffonts", "pdfimages")
RENDER_DPI = 300
TEXT_TOLERANCE_PT = 0.25
CHANNEL_TOLERANCE = 8


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tool(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(f"{command[0]} failed for {command[-1]}:\n{result.stdout}{result.stderr}")
    return result.stdout


def pdf_layout(path: Path) -> tuple[tuple[float, float], list[tuple[str, tuple[float, ...]]]]:
    root = ET.fromstring(run_tool(["pdftotext", "-bbox", str(path), "-"]))
    pages = [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "page"]
    if len(pages) != 1:
        raise ValueError(f"{path.name}: expected one PDF page, found {len(pages)}")
    page = pages[0]
    size = (float(page.attrib["width"]), float(page.attrib["height"]))
    words = [(item.text or "", tuple(float(item.attrib[key]) for key in
                                    ("xMin", "yMin", "xMax", "yMax")))
             for item in page.iter() if item.tag.rsplit("}", 1)[-1] == "word"]
    return size, words


def validate_pdf(path: Path) -> None:
    """Reject unexpected raster content, Type 3 fonts or unembedded fonts."""
    if not path.read_bytes().startswith(b"%PDF-"):
        raise ValueError(f"{path.name}: not a PDF")
    pdf_layout(path)  # Also requires exactly one inspectable page.
    font_lines = run_tool(["pdffonts", str(path)]).splitlines()[2:]
    fonts = [line.split() for line in font_lines if line.strip()]
    if not fonts:
        raise ValueError(f"{path.name}: no inspectable text fonts")
    for fields in fonts:
        name = fields[0]
        if "Type 3" in " ".join(fields[1:-5]):
            raise ValueError(f"{path.name}: Type 3 font {name}")
        if fields[-5] != "yes":
            raise ValueError(f"{path.name}: unembedded font {name}")
    image_lines = run_tool(["pdfimages", "-list", str(path)]).splitlines()[2:]
    if any(line.split() and line.split()[0].isdigit() for line in image_lines):
        raise ValueError(f"{path.name}: unexpected raster image in a vector figure")


def compare_text_layout(reference: Path, generated: Path) -> None:
    reference_size, reference_words = pdf_layout(reference)
    generated_size, remaining = pdf_layout(generated)
    if not np.allclose(reference_size, generated_size, rtol=0, atol=0.001):
        raise ValueError(f"{reference.name}: page layout differs: {reference_size} vs {generated_size}")
    if len(reference_words) != len(remaining):
        raise ValueError(f"{reference.name}: visible text count differs: "
                         f"{len(reference_words)} vs {len(remaining)}")
    for label, box in reference_words:
        candidates = [(max(abs(a - b) for a, b in zip(box, other_box)), index)
                      for index, (other_label, other_box) in enumerate(remaining)
                      if other_label == label]
        if not candidates:
            raise ValueError(f"{reference.name}: visible text differs; missing {label!r}")
        distance, index = min(candidates)
        if distance > TEXT_TOLERANCE_PT:
            raise ValueError(f"{reference.name}: text layout for {label!r} differs by "
                             f"{distance:.4f} pt (limit {TEXT_TOLERANCE_PT} pt)")
        remaining.pop(index)


def render_difference(reference: Image.Image, generated: Image.Image) -> int:
    """Count pixels outside both images' local edge/antialiasing envelope."""
    a, b = np.asarray(reference, dtype=np.int16), np.asarray(generated, dtype=np.int16)
    mismatch = np.zeros(a.shape[:2], dtype=bool)
    for actual, other in ((a, generated), (b, reference)):
        low = np.asarray(other.filter(ImageFilter.MinFilter(3)), dtype=np.int16)
        high = np.asarray(other.filter(ImageFilter.MaxFilter(3)), dtype=np.int16)
        mismatch |= np.any((actual < low - CHANNEL_TOLERANCE)
                           | (actual > high + CHANNEL_TOLERANCE), axis=2)
    return int(mismatch.sum())


def compare_pdf(reference: Path, generated: Path, render_dir: Path) -> str:
    """Compare visible text and the entire rendered image; never mask a region."""
    validate_pdf(reference)
    validate_pdf(generated)
    if reference.read_bytes() == generated.read_bytes():
        return "byte-identical to approved PDF"
    compare_text_layout(reference, generated)
    render_dir.mkdir(parents=True, exist_ok=True)
    for label, path in (("approved", reference), ("generated", generated)):
        run_tool(["pdftoppm", "-r", str(RENDER_DPI), "-singlefile", "-png",
                  str(path), str(render_dir / label)])
    with Image.open(render_dir / "approved.png") as source_a, Image.open(render_dir / "generated.png") as source_b:
        a, b = source_a.convert("RGB"), source_b.convert("RGB")
    if a.size != b.size:
        raise ValueError(f"{reference.name}: rendered page dimensions differ")
    if np.array_equal(np.asarray(a), np.asarray(b)):
        return "pixel-identical at 300 dpi; visible text/layout agree"
    differences = render_difference(a, b)
    if differences:
        raise ValueError(f"{reference.name}: render differs in {differences:,} pixels outside "
                         "the 1-pixel / 8-channel-level rendering tolerance")
    return "visible text/layout and full-page rendering agree within the stated edge tolerance"


def output_hashes(directory: Path) -> dict[str, str]:
    pdfs = {path.name for path in directory.glob("*.pdf")}
    if pdfs != set(FIGURE_NAMES):
        raise ValueError(f"Expected exactly seven PDFs; missing={sorted(set(FIGURE_NAMES) - pdfs)}, "
                         f"unexpected={sorted(pdfs - set(FIGURE_NAMES))}")
    return {path.name: sha256(path) for path in sorted(directory.iterdir())
            if path.suffix in (".pdf", ".svg")}


def check_figures(
    *, reference_dir: Path = FIGURE_DIR, results_root: Path | None = None,
    verbose: bool = False,
) -> None:
    if missing := [name for name in POPPLER_TOOLS if not shutil.which(name)]:
        raise ValueError("Install Poppler utilities; missing: " + ", ".join(missing))
    reference_dir = reference_dir.resolve()
    before = {name: sha256(reference_dir / name) for name in FIGURE_NAMES}
    try:
        with TemporaryDirectory(prefix="powerfit-manuscript-figures-") as temporary:
            work = Path(temporary)
            environment = dict(os.environ)
            environment["MPLCONFIGDIR"] = str(work / "matplotlib")
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            builds = []
            for number in (1, 2):
                destination = work / f"run-{number}"
                command = [sys.executable, str(REPO_ROOT / "scripts/build_manuscript_figures.py"),
                           "--output-dir", str(destination)]
                if results_root is not None:
                    command += ["--results-root", str(results_root.resolve())]
                print(f"[figures] temporary build {number}/2 with {sys.executable}", flush=True)
                result = subprocess.run(command, cwd=REPO_ROOT, env=environment,
                                        capture_output=True, text=True)
                if verbose or result.returncode:
                    print(result.stdout + result.stderr, end="")
                if result.returncode:
                    raise ValueError(f"Temporary figure build {number} failed (exit {result.returncode})")
                builds.append(output_hashes(destination))
            if builds[0] != builds[1]:
                changed = sorted(name for name in builds[0].keys() | builds[1].keys()
                                 if builds[0].get(name) != builds[1].get(name))
                raise ValueError("Same-environment figure output is not deterministic: " + ", ".join(changed))
            print(f"[figures] both builds have identical bytes for all {len(builds[0])} PDF/SVG outputs")
            for name in FIGURE_NAMES:
                status = compare_pdf(reference_dir / name, work / "run-1" / name, work / "render" / name)
                print(f"[figures] {name}: {status}")
            print("[figures] vector-only PDFs; no Type 3 fonts; all fonts embedded")
    finally:
        after = {name: sha256(reference_dir / name) for name in FIGURE_NAMES}
        if before != after:
            raise ValueError("Canonical figure bytes changed during validation")
    print("[figures] PASS: all seven figures validated; approved PDFs unchanged")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-dir", type=Path, default=FIGURE_DIR,
                        help="Approved PDFs (default: repository manuscript/figures)")
    parser.add_argument("--results-root", type=Path,
                        help="Frozen results tree (default: repository results/)")
    parser.add_argument("--verbose", action="store_true", help="Show all generator output")
    args = parser.parse_args()
    try:
        check_figures(reference_dir=args.reference_dir, results_root=args.results_root,
                      verbose=args.verbose)
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"[figures] FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
