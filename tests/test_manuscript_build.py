"""Behavior checks for nested manuscript sources and portable source bundles."""
from __future__ import annotations

import importlib.util
from pathlib import Path
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

    def test_pinned_class_source_support_is_bundled(self):
        main = self.root / "manuscript.tex"
        main.write_text(main.read_text().replace("{article}", "{elsarticle}"))
        (self.root / "elsarticle.cls").write_text("test class")
        support = self.root / "tex-support"
        support.mkdir()
        for name in ["README.md", "README.upstream", "elsarticle.dtx", "elsarticle.ins"]:
            (support / name).write_text("upstream support")
        paths = {p.relative_to(self.root).as_posix()
                 for p in self.checker().collect_dependencies(self.root)}
        self.assertIn("tex-support/elsarticle.dtx", paths)
        self.assertIn("tex-support/README.md", paths)

    def test_missing_or_stale_bibliography_is_rejected(self):
        checker = self.checker()
        self.assertTrue(any(".bbl" in e for e in checker.check_bibliography(self.root)))
        (self.root / "manuscript.bbl").write_text(r"\bibitem{obsolete} Old item")
        self.assertTrue(any("sample" in e for e in checker.check_bibliography(self.root)))
        (self.root / "manuscript.bbl").write_text(r"\bibitem{sample} Example")
        self.assertEqual(checker.check_bibliography(self.root), [])

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
