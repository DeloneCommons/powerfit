"""Offline regression checks for the manual Zenodo source/PDF package."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_zenodo_archive.py"
spec = importlib.util.spec_from_file_location("build_zenodo_archive", SCRIPT)
packager = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(packager)


class ZenodoArchiveTests(unittest.TestCase):
    def test_versioned_git_tree_and_pdf_are_the_only_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.org"], check=True)
            for name in ("README.md", "LICENSE", "CITATION.cff",
                         ".zenodo.json", "THIRD_PARTY_LICENSES.md",
                         "manuscript/manuscript.tex"):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("tracked\n")
            for i in range(7):
                fig = root / f"manuscript/figures/figure_{i}.pdf"
                fig.parent.mkdir(parents=True, exist_ok=True)
                fig.write_bytes(b"%PDF-1.4 figure")
            (root / ".gitignore").write_text("manuscript/manuscript.pdf\nbuild/\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            subprocess.run(["git", "-C", str(root), "tag", "v2.0.0"], check=True)
            pdf = root / "manuscript/manuscript.pdf"
            pdf.write_bytes(b"%PDF-1.4 built manuscript")
            (root / "untracked.txt").write_text("not in archive")
            output = root / "build/powerfit-v2.0.0.zip"
            commit, digest = packager.write_archive(root, "v2.0.0", pdf, output)
            self.assertEqual(commit, packager._git(root, "rev-parse", "HEAD"))
            self.assertEqual(len(digest), 64)
            with zipfile.ZipFile(output) as z:
                names = z.namelist()
                self.assertIn("powerfit-v2.0.0/manuscript/manuscript.pdf", names)
                self.assertEqual(z.read("powerfit-v2.0.0/manuscript/manuscript.pdf"), pdf.read_bytes())
                self.assertNotIn("powerfit-v2.0.0/untracked.txt", names)
            (root / "README.md").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "Tracked files have local changes"):
                packager.write_archive(root, "v2.0.0", pdf, output)


if __name__ == "__main__":
    unittest.main()
