"""Behavior checks for nested manuscript sources and portable source bundles."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class ManuscriptBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "manuscript"
        self.root.mkdir()
        (self.root / "sections").mkdir()
        (self.root / "appendices").mkdir()
        (self.root / "figures").mkdir()
        (self.root / "manuscript.tex").write_text(
            r"\documentclass{article}" "\n"
            r"\input{sections/body}" "\n"
            r"\input{appendices/proof}" "\n"
            r"\bibliographystyle{plain}\bibliography{refs}" "\n"
        )
        (self.root / "sections/body.tex").write_text(
            r"\section{Body}\label{sec:body}\cite{sample}" "\n"
            r"\includegraphics{figures/example.pdf}" "\n"
            r"% \input{missing-commented-file}" "\n"
        )
        (self.root / "appendices/proof.tex").write_text(r"See \ref{sec:body}.")
        (self.root / "refs.bib").write_text("@misc{sample, title={Example}}\n")
        (self.root / "figures/example.pdf").write_bytes(b"%PDF-fixture\n")

    def checker(self):
        self.assertTrue((SCRIPTS / "check_manuscript.py").is_file(),
                        "the revised manuscript source checker is not implemented")
        import check_manuscript
        return check_manuscript

    def test_nested_dependencies_are_resolved_from_manuscript_root(self):
        files = self.checker().collect_dependencies(self.root)
        self.assertEqual({p.relative_to(self.root).as_posix() for p in files}, {
            "manuscript.tex", "sections/body.tex", "appendices/proof.tex",
            "refs.bib", "figures/example.pdf",
        })

    def test_missing_nested_source_is_rejected(self):
        (self.root / "appendices/proof.tex").unlink()
        with self.assertRaisesRegex(ValueError, "appendices/proof"):
            self.checker().collect_dependencies(self.root)

    def test_source_cannot_escape_the_bundle(self):
        (self.root.parent / "private.tex").write_text("private")
        (self.root / "sections/body.tex").write_text(r"\input{../private}")
        with self.assertRaisesRegex(ValueError, "outside|escape"):
            self.checker().collect_dependencies(self.root)

    def test_recursive_input_is_reported(self):
        (self.root / "sections/body.tex").write_text(r"\input{manuscript}")
        with self.assertRaisesRegex(ValueError, "[Cc]ycl"):
            self.checker().collect_dependencies(self.root)

    def test_extensionless_input_rejects_symlink_to_private_file(self):
        private = self.root.parent / "private.tex"
        private.write_text("Private sentinel")
        body = self.root / "sections/body.tex"
        body.unlink()
        body.symlink_to(private)
        with self.assertRaisesRegex(ValueError, "outside|escape|[Ss]ymbolic"):
            self.checker().collect_dependencies(self.root)

    def test_absolute_source_path_is_not_portable(self):
        body = self.root / "sections/body.tex"
        (self.root / "manuscript.tex").write_text(r"\input{" + str(body) + "}")
        with self.assertRaisesRegex(ValueError, "[Aa]bsolute"):
            self.checker().collect_dependencies(self.root)

    def test_missing_citation_and_reference_are_reported(self):
        (self.root / "appendices/proof.tex").write_text(r"\ref{absent}\cite{unknown}")
        errors = self.checker().check_sources(self.root)
        self.assertTrue(any("absent" in e for e in errors), errors)
        self.assertTrue(any("unknown" in e for e in errors), errors)

    def test_duplicate_labels_are_rejected(self):
        (self.root / "appendices/proof.tex").write_text(r"\label{sec:body}")
        self.assertTrue(any("duplicate" in e.lower()
                            for e in self.checker().check_sources(self.root)))

    def cam_support(self):
        main = self.root / "manuscript.tex"
        main.write_text(main.read_text().replace(
            r"\documentclass{article}",
            r"\documentclass[pdflatex,sn-mathphys-ay]{sn-jnl}"))
        # The class selects its style internally; the wrapper has no such command.
        main.write_text(main.read_text().replace(r"\bibliographystyle{plain}", ""))
        (self.root / "sn-jnl.cls").write_bytes(b"% Official class fixture\r")
        (self.root / "sn-mathphys-ay.bst").write_text("% Author/year style fixture\n")
        (self.root / "TEMPLATE_PROVENANCE.md").write_text("Publisher provenance\n")
        (self.root / "CAM_SYNC.md").write_text("Pinned source baseline\n")
        support = self.root / "tex-support"
        support.mkdir()
        (support / "README.md").write_text("Upstream license notices\n")

    def test_class_selected_author_year_style_is_bundled_with_notices(self):
        self.cam_support()
        paths = {p.relative_to(self.root).as_posix()
                 for p in self.checker().collect_dependencies(self.root)}
        self.assertIn("sn-jnl.cls", paths)
        self.assertIn("sn-mathphys-ay.bst", paths)
        self.assertIn("TEMPLATE_PROVENANCE.md", paths)
        self.assertIn("CAM_SYNC.md", paths)
        self.assertIn("tex-support/README.md", paths)

    def test_missing_pinned_cam_support_is_rejected(self):
        self.cam_support()
        for name in ("sn-jnl.cls", "sn-mathphys-ay.bst", "TEMPLATE_PROVENANCE.md",
                     "CAM_SYNC.md", "tex-support/README.md"):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, name):
                    self.checker().collect_dependencies(self.root)
                path.write_bytes(original)

    def test_cam_bundle_preserves_publisher_bytes_and_excludes_private_material(self):
        self.cam_support()
        (self.root / "manuscript.bbl").write_text(
            r"\bibitem[Author(2026)]{sample} Example")
        (self.root / "cover-letter.md").write_text("Private sentinel")
        (self.root / "elsarticle.cls").write_text("Stale class")
        (self.root / "manuscript.pdf").write_bytes(b"%PDF-review-output")
        import make_arxiv_bundle
        output = self.root.parent / "cam.zip"
        make_arxiv_bundle.write_bundle(self.root, output)
        first = output.read_bytes()
        make_arxiv_bundle.write_bundle(self.root, output)
        self.assertEqual(output.read_bytes(), first)
        with zipfile.ZipFile(output) as archive:
            self.assertIn("sn-mathphys-ay.bst", archive.namelist())
            self.assertIn("TEMPLATE_PROVENANCE.md", archive.namelist())
            self.assertIn("CAM_SYNC.md", archive.namelist())
            self.assertEqual(archive.read("sn-jnl.cls"), b"% Official class fixture\r")
            self.assertNotIn("cover-letter.md", archive.namelist())
            self.assertNotIn("elsarticle.cls", archive.namelist())
            self.assertNotIn("manuscript.pdf", archive.namelist())

    def test_missing_or_stale_bibliography_is_rejected(self):
        checker = self.checker()
        self.assertTrue(any(".bbl" in e for e in checker.check_bibliography(self.root)))
        (self.root / "manuscript.bbl").write_text(r"\bibitem{obsolete} Old item")
        self.assertTrue(any("sample" in e for e in checker.check_bibliography(self.root)))
        (self.root / "manuscript.bbl").write_text(r"\bibitem{sample} Example")
        self.assertEqual(checker.check_bibliography(self.root), [])

    def test_cam_layout_notices_are_allowed_without_hiding_build_errors(self):
        self.cam_support()
        (self.root / "manuscript.bbl").write_text(r"\bibitem{sample} Example")
        (self.root / "manuscript.blg").write_text("")
        (self.root / "manuscript.log").write_text(
            "Underfull \\hbox (badness 6559) in paragraph at lines 60--63\n"
            "Underfull \\vbox (badness 10000) has occurred while \\output is active []\n"
            "Package hyperref Warning: Difference (2) between bookmark levels is greater\n")
        self.assertEqual(self.checker().check_built(self.root), ["Missing manuscript.pdf"])
        for diagnostic in (
            "LaTeX Warning: Reference `missing' on page 1 undefined",
            "Package natbib Warning: Citation `sample' on page 1 undefined",
            "Overfull \\hbox (1.0pt too wide) in paragraph",
            "Package hyperref Warning: Token not allowed in a PDF string",
        ):
            with self.subTest(diagnostic=diagnostic):
                (self.root / "manuscript.log").write_text(diagnostic + "\n")
                self.assertTrue(any(diagnostic in error
                                    for error in self.checker().check_built(self.root)))
        (self.root / "manuscript.log").write_text("")
        (self.root / "manuscript.blg").write_text("Warning--missing publisher in sample\n")
        self.assertTrue(any("missing publisher" in error
                            for error in self.checker().check_built(self.root)))

    def test_layout_notice_allowance_is_limited_to_the_cam_class(self):
        (self.root / "manuscript.bbl").write_text(r"\bibitem{sample} Example")
        (self.root / "manuscript.blg").write_text("")
        (self.root / "manuscript.log").write_text("Underfull \\hbox (badness 6559)\n")
        self.assertTrue(any("Underfull" in error
                            for error in self.checker().check_built(self.root)))

    @unittest.skipUnless(all(shutil.which(tool) for tool in (
        "latexmk", "pdflatex", "bibtex", "kpsewhich", "pdfinfo", "pdffonts")),
        "TeX and Poppler tools are required for the publisher-migration build")
    def test_build_refreshes_legacy_publisher_auxiliaries(self):
        self.cam_support()
        for name in ("sn-jnl.cls", "sn-mathphys-ay.bst"):
            shutil.copyfile(SCRIPTS.parent / "manuscript" / name, self.root / name)
        # Seed a genuine latexmk cache for a publisher style that is then removed.
        plain = subprocess.check_output(["kpsewhich", "plain.bst"], text=True).strip()
        shutil.copyfile(plain, self.root / "retired.bst")
        (self.root / "manuscript.tex").write_text(
            r"\documentclass{article}\usepackage{lmodern}" "\n"
            r"\begin{document}Old citation \cite{obsolete}." "\n"
            r"\bibliographystyle{retired}\bibliography{refs}\end{document}" "\n")
        (self.root / "refs.bib").write_text(
            "@book{obsolete, author={Author, Alice}, title={Old Example}, "
            "year={2025}, publisher={Sample Press}}\n")
        legacy = subprocess.run(
            ["latexmk", "-norc", "-pdf", "-bibtex", "-interaction=nonstopmode",
             "-halt-on-error", "manuscript.tex"],
            cwd=self.root, capture_output=True, text=True, timeout=120)
        self.assertEqual(legacy.returncode, 0, legacy.stdout + legacy.stderr)
        (self.root / "retired.bst").unlink()
        (self.root / "manuscript.tex").write_text(
            r"\documentclass[pdflatex,sn-mathphys-ay]{sn-jnl}" "\n"
            r"\usepackage[T1]{fontenc}\usepackage{lmodern}\usepackage{amsmath,xcolor}" "\n"
            r"\begin{document}A source-build example \citep{sample}." "\n"
            r"\bibliography{refs}\end{document}" "\n")
        (self.root / "refs.bib").write_text(
            "@book{sample, author={Author, Alice}, title={An Example}, "
            "year={2026}, publisher={Sample Press}, address={Sample City}}\n")
        scripts = self.root.parent / "scripts"
        scripts.mkdir()
        for name in ("build_manuscript_pdfs.sh", "check_manuscript.py"):
            shutil.copyfile(SCRIPTS / name, scripts / name)
        shutil.copyfile(SCRIPTS.parent / ".latexmkrc", self.root.parent / ".latexmkrc")
        result = subprocess.run(
            ["bash", str(scripts / "build_manuscript_pdfs.sh")],
            cwd=self.root.parent, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.root / "manuscript.pdf").is_file())
        self.assertIn("sn-mathphys-ay", (self.root / "manuscript.aux").read_text())
        self.assertNotIn("obsolete", (self.root / "manuscript.bbl").read_text())

    def test_archive_preserves_paths_and_excludes_unreferenced_material(self):
        self.checker()
        self.assertTrue((SCRIPTS / "make_arxiv_bundle.py").is_file(),
                        "the nested arXiv source packager is not implemented")
        import make_arxiv_bundle
        (self.root / "manuscript.bbl").write_text(r"\bibitem{sample} Example")
        (self.root / "private-notes.md").write_text("Do not publish")
        (self.root / "figures/candidate.pdf").write_bytes(b"excluded")
        output = self.root.parent / "submission.zip"
        make_arxiv_bundle.write_bundle(self.root, output)
        with zipfile.ZipFile(output) as archive:
            names = set(archive.namelist())
            self.assertIn("sections/body.tex", names)
            self.assertIn("appendices/proof.tex", names)
            self.assertIn("manuscript.bbl", names)
            self.assertNotIn("private-notes.md", names)
            self.assertNotIn("figures/candidate.pdf", names)
            self.assertEqual(archive.read("sections/body.tex"),
                             (self.root / "sections/body.tex").read_bytes())


if __name__ == "__main__":
    unittest.main()
