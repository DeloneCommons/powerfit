#!/usr/bin/env python3
"""Create one manual-Zenodo ZIP from an exact Git tag and its built article PDF.

Run from a clean checkout at the tag after merging the release-preparation PR.
The source is exported by git archive; ignored or untracked files cannot
enter the snapshot. Only the freshly built manuscript PDF is added afterward.
No release, DOI, Zenodo deposit, or arXiv submission is created.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
TAG_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\Z")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True
    ).strip()


def check_tag_checkout(root: Path, tag: str) -> str:
    """Require an existing version tag, its exact HEAD, and clean tracked files."""
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"Expected a version tag such as v2.0.0, got {tag!r}")
    commit = _git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    if _git(root, "rev-parse", "HEAD") != commit:
        raise ValueError(f"Checkout HEAD must be exactly {tag} ({commit})")
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked files have local changes; use a clean checkout")
    return commit


def write_archive(root: Path, tag: str, pdf: Path, output: Path) -> tuple[str, str]:
    """Package the tagged Git tree plus one PDF; return commit and ZIP SHA256."""
    commit = check_tag_checkout(root, tag)
    if not pdf.is_file() or not pdf.read_bytes().startswith(b"%PDF-"):
        raise ValueError("Missing or invalid compiled manuscript PDF")
    prefix = f"powerfit-{tag}/"
    pdf_name = prefix + "manuscript/manuscript.pdf"
    required = {prefix + name for name in (
        "README.md", "LICENSE", "CITATION.cff", ".zenodo.json",
        "THIRD_PARTY_LICENSES.md", "manuscript/manuscript.tex",
    )}

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as td:
        staged = Path(td) / "archive.zip"
        subprocess.run(
            ["git", "-C", str(root), "archive", "--format=zip",
             f"--prefix={prefix}", f"--output={staged}", tag],
            check=True,
        )
        # Use a fixed timestamp for the sole added file. The Git entries are
        # already tied to the exact tagged commit by git archive.
        info = zipfile.ZipInfo(pdf_name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        with zipfile.ZipFile(staged, "a", allowZip64=True) as archive:
            if pdf_name in archive.namelist():
                raise ValueError("Tagged source unexpectedly already contains the PDF")
            archive.writestr(info, pdf.read_bytes())

        with zipfile.ZipFile(staged) as archive:
            names = archive.namelist()
            tracked = _git(root, "ls-tree", "-r", "--name-only", tag).splitlines()
            missing_tracked = {prefix + name for name in tracked} - set(names)
            if missing_tracked:
                raise ValueError(f"Missing tagged Git files: {sorted(missing_tracked)[:5]}")
            if len(names) != len(set(names)):
                raise ValueError("Duplicate ZIP entries")
            if not required.issubset(names):
                raise ValueError(f"Missing expected sources: {required - set(names)}")
            figure_pdfs = [name for name in names
                           if name.startswith(prefix + "manuscript/figures/")
                           and name.endswith(".pdf")]
            if len(figure_pdfs) != 7:
                raise ValueError(f"Expected seven manuscript figure PDFs, got {len(figure_pdfs)}")
            if archive.read(pdf_name) != pdf.read_bytes():
                raise ValueError("Embedded manuscript PDF differs from the build")
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity test failed")
        os.replace(staged, output)
    hasher = hashlib.sha256()
    with output.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            hasher.update(block)
    digest = hasher.hexdigest()
    return commit, digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="v2.0.0")
    parser.add_argument("--output", type=Path,
                        default=REPO_ROOT / "build/powerfit-v2.0.0.zip")
    args = parser.parse_args()
    check_tag_checkout(REPO_ROOT, args.tag)
    # Rebuild, rather than accidentally embedding a stale ignored PDF.
    subprocess.run(["bash", str(REPO_ROOT / "scripts/build_manuscript_pdfs.sh")],
                   cwd=REPO_ROOT, check=True)
    subprocess.run([sys.executable,
                    str(REPO_ROOT / "scripts/check_repo_consistency.py")],
                   cwd=REPO_ROOT, check=True)
    commit, digest = write_archive(REPO_ROOT, args.tag,
                                   REPO_ROOT / "manuscript/manuscript.pdf",
                                   args.output.resolve())
    print(f"Zenodo ZIP: {args.output.resolve()}")
    print(f"Git tag: {args.tag} ({commit})")
    print(f"SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
