"""Integration checks for the canonical figure build and comparison gate."""

from contextlib import redirect_stdout
import hashlib
import importlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
FIGURES = {
    "figure_02_separators.pdf", "figure_03_cycle.pdf", "figure_04_realization.pdf",
    "figure_05_workflow.pdf", "figure_C_identifiability.pdf",
    "figure_E_bcp_projection.pdf", "figure_G_mismatch.pdf",
}


def canonical_hashes():
    return {name: hashlib.sha256((ROOT / "manuscript/figures" / name).read_bytes()).hexdigest()
            for name in FIGURES}


class CanonicalFigureBuild(unittest.TestCase):
    def test_wrapper_builds_all_seven_elsewhere_without_changing_canonical_pdfs(self):
        before = canonical_hashes()
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "generated"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/build_manuscript_figures.py"),
                "--output-dir", str(output), "--results-root", str(ROOT / "results"),
            ], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({p.name for p in output.glob("*.pdf")}, FIGURES)
            self.assertEqual(canonical_hashes(), before)

    def test_wrapper_rejects_retired_archive_option(self):
        with TemporaryDirectory() as tmp:
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/build_manuscript_figures.py"),
                "--archive", "retired.zip", "--dry-run",
            ], cwd=tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("unrecognized arguments: --archive", result.stderr)

    def test_dry_run_does_not_create_the_output_directory(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "uncreated"
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts/build_manuscript_figures.py"),
                "--output-dir", str(output), "--dry-run",
            ], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(output.exists())


@unittest.skipUnless(all(shutil.which(tool) for tool in
                        ("pdftoppm", "pdftotext", "pdffonts", "pdfimages")),
                     "Poppler is needed for PDF validation")
class FigureComparison(unittest.TestCase):
    def setUp(self):
        self.checker = importlib.import_module("check_manuscript_figures")
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def draw(self, name, *, label="Frozen values", color="#2166AC", offset=0., fonttype=42,
             raster=False, title="Reference", corefonts=False):
        path = self.directory / name
        with matplotlib.rc_context({"pdf.fonttype": fonttype, "pdf.use14corefonts": corefonts,
                                    "font.family": "Times" if corefonts else "DejaVu Sans"}):
            figure = plt.figure(figsize=(2., 1.5))
            axes = figure.add_axes([0, 0, 1, 1])
            axes.set(xlim=(0, 1), ylim=(0, 1))
            axes.axis("off")
            axes.text(.1, .8, label, fontsize=10.)
            axes.plot([.1, .9], [.2 + offset, .6 + offset], color=color, linewidth=2.)
            if raster:
                axes.imshow([[0, 1], [1, 0]], extent=(.5, .8, .1, .3))
            figure.savefig(path, metadata={"Title": title, "CreationDate": None, "ModDate": None})
            plt.close(figure)
        return path

    def compare(self, a, b):
        with redirect_stdout(io.StringIO()):
            return self.checker.compare_pdf(a, b, self.directory / "rendered")

    def test_metadata_changes_do_not_fail_identical_rendering(self):
        a = self.draw("reference.pdf")
        b = self.draw("rebuilt.pdf", title="Different metadata")
        self.assertNotEqual(a.read_bytes(), b.read_bytes())
        self.compare(a, b)

    def test_changed_visible_text_is_rejected(self):
        a = self.draw("reference.pdf")
        b = self.draw("rebuilt.pdf", label="Different values")
        with self.assertRaisesRegex(ValueError, "text|layout"):
            self.compare(a, b)

    def test_changed_plot_geometry_or_color_is_rejected(self):
        a = self.draw("reference.pdf")
        for changes in ({"offset": .06}, {"color": "#BB4B13"}):
            with self.subTest(changes=changes):
                b = self.draw("rebuilt.pdf", **changes)
                with self.assertRaisesRegex(ValueError, "render"):
                    self.compare(a, b)

    def test_unembedded_times_header_is_rejected_even_for_workflow(self):
        path = self.draw("figure_05_workflow.pdf", label="Connector diagnostics", corefonts=True)
        with self.assertRaisesRegex(ValueError, "unembedded font Times-Roman"):
            self.checker.validate_pdf(path)

    @unittest.skipUnless(shutil.which("pdfinfo"), "Poppler pdfinfo is needed")
    def test_article_checker_rejects_unembedded_times(self):
        checker = importlib.import_module("check_manuscript")
        self.draw("manuscript.pdf", label="Connector diagnostics", corefonts=True)
        (self.directory / "manuscript.tex").write_text("A minimal article.\n")
        for suffix in (".log", ".blg", ".bbl"):
            (self.directory / ("manuscript" + suffix)).write_text("")
        errors = checker.check_built(self.directory)
        self.assertTrue(any("unembedded PDF font:" in error and "Times-Roman" in error
                            for error in errors), errors)

    def test_type3_fonts_and_raster_content_are_rejected(self):
        for changes in ({"fonttype": 3}, {"raster": True}):
            with self.subTest(changes=changes):
                path = self.draw("invalid.pdf", **changes)
                with self.assertRaisesRegex(ValueError, "Type 3|raster"):
                    self.checker.validate_pdf(path)


if __name__ == "__main__":
    unittest.main()
