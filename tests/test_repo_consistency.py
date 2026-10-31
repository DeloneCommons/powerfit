"""Integrity checks against small, independent repository fixtures."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts/check_repo_consistency.py"
SPEC = importlib.util.spec_from_file_location("repo_consistency", SOURCE)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)

PROTECTED_DIRECTORIES = [
    "experiments", "results", "data", "environments", "external_software",
    "scripts/qtaim",
]
PROTECTED_FILES = ["scripts/_figure_io.py"]


class RepositoryFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(checker, "REPO_ROOT", self.root).start()
        for directory in PROTECTED_DIRECTORIES:
            self.write(f"{directory}/frozen.txt", "original scientific artifact\n")
        self.write("scripts/_figure_io.py", "# Original figure helper.\n")

    def write(self, relative, text):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def manifest(self):
        files = {}
        for directory in PROTECTED_DIRECTORIES:
            for path in (self.root / directory).rglob("*"):
                if path.is_file():
                    files[path.relative_to(self.root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        for relative in PROTECTED_FILES:
            files[relative] = hashlib.sha256((self.root / relative).read_bytes()).hexdigest()
        payload = {
            "schema_version": 1,
            "baseline_commit": "80933a14c57d4766bd2c03b2990d949a452031fc",
            "protected_directories": PROTECTED_DIRECTORIES,
            "protected_files": PROTECTED_FILES,
            "files": files,
        }
        self.write("scripts/frozen_artifacts.sha256.json", json.dumps(payload))
        return payload

    def frozen_problems(self):
        function = getattr(checker, "_check_frozen_artifacts", None)
        self.assertTrue(callable(function), "The frozen artifact validator must be available")
        return function()

    def complete_fixture(self):
        self.write("environments/requirements-py313.txt", "numpy\nscipy\npandas\nmatplotlib\npyyaml\njinja2\nrdkit\ntqdm\n")
        self.write("environments/requirements-qtaim.txt", "pyscf\ngeometric\nrdkit\nscipy\npandas\ntqdm\n")
        for manifest, artifact in [
            ("pyvoro2-version.txt", "pinned.whl"),
            ("multiwfn-version.txt", "Multiwfn_noGUI"),
        ]:
            self.write(f"external_software/{artifact}", "pinned artifact\n")
            digest = hashlib.sha256(b"pinned artifact\n").hexdigest()
            self.write(f"external_software/{manifest}", f"artifact file: {artifact}\nsha256: {digest}\n")
        self.write("scripts/check_manuscript.py", "print('Manuscript source checks passed.')\n")
        self.manifest()
        shutil.copyfile(SOURCE, self.root / "scripts/check_repo_consistency.py")

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts/check_repo_consistency.py"), *arguments],
            cwd=self.root, text=True, capture_output=True, check=False,
        )


class FrozenArtifactChecks(RepositoryFixture):
    def test_unchanged_source_archive_passes_without_git(self):
        self.manifest()
        self.assertFalse((self.root / ".git").exists())
        self.assertEqual(self.frozen_problems(), [])

    def test_changed_scientific_bytes_are_reported(self):
        self.manifest()
        self.write("results/frozen.txt", "modified scientific artifact\n")
        problems = self.frozen_problems()
        self.assertEqual([problem.path for problem in problems], ["results/frozen.txt"])
        self.assertIn("digest mismatch", problems[0].detail)

    def test_missing_baseline_file_is_reported(self):
        self.manifest()
        (self.root / "experiments/frozen.txt").unlink()
        problems = self.frozen_problems()
        self.assertEqual([problem.path for problem in problems], ["experiments/frozen.txt"])
        self.assertIn("missing", problems[0].detail)

    def test_added_scientific_file_is_reported(self):
        self.manifest()
        self.write("data/new_measurements.csv", "value\n42\n")
        problems = self.frozen_problems()
        self.assertEqual([problem.path for problem in problems], ["data/new_measurements.csv"])
        self.assertIn("unexpected", problems[0].detail)

    def test_python_cache_does_not_change_the_scientific_snapshot(self):
        self.manifest()
        self.write("experiments/__pycache__/runner.cpython-313.pyc", "cache")
        self.write("scripts/qtaim/__pycache__/analysis.cpython-313.pyc", "cache")
        self.assertEqual(self.frozen_problems(), [])

    def test_symlink_cannot_replace_a_frozen_file_even_with_identical_bytes(self):
        self.manifest()
        target = self.write("unprotected-copy.txt", "original scientific artifact\n")
        frozen = self.root / "data/frozen.txt"
        frozen.unlink()
        frozen.symlink_to(target)
        problems = self.frozen_problems()
        self.assertTrue(any(problem.path == "data/frozen.txt" and "symlink" in problem.detail for problem in problems))

    def test_invalid_manifest_paths_and_digests_are_rejected(self):
        for relative, digest in [("../outside.txt", "0" * 64), ("results/frozen.txt", "not-a-hash")]:
            with self.subTest(relative=relative):
                payload = self.manifest()
                payload["files"][relative] = digest
                self.write("scripts/frozen_artifacts.sha256.json", json.dumps(payload))
                problems = self.frozen_problems()
                self.assertTrue(any(problem.path == "scripts/frozen_artifacts.sha256.json" and "invalid" in problem.detail for problem in problems))


class RepositoryIntegrationChecks(RepositoryFixture):
    def test_generated_outputs_are_excluded_but_source_links_and_paths_are_checked(self):
        leaked = "/" + "home/example/private/results.csv"
        for directory in ["build", ".smoke", ".venv", ".git", "scripts/__pycache__"]:
            self.write(f"{directory}/REPORT.md", f"[missing](absent.txt)\n{leaked}\n")
        self.assertEqual(checker._check_markdown_links(), [])
        self.assertEqual(checker._check_absolute_paths(), [])
        self.write("README.md", f"[missing](absent.txt)\n{leaked}\n")
        self.assertEqual([problem.path for problem in checker._check_markdown_links()], ["README.md"])
        self.assertEqual([problem.path for problem in checker._check_absolute_paths()], ["README.md"])

    def test_manuscript_failure_is_reported_by_the_repository_audit(self):
        self.complete_fixture()
        self.write("scripts/check_manuscript.py", "raise SystemExit('missing sections/results.tex')\n")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing sections/results.tex", result.stdout)

    def test_skip_frozen_allows_an_explicit_rerun_without_updating_the_manifest(self):
        self.complete_fixture()
        manifest = (self.root / "scripts/frozen_artifacts.sha256.json").read_bytes()
        self.write("results/frozen.txt", "explicit rerun results\n")
        ordinary = self.run_cli()
        skipped = self.run_cli("--skip-frozen")
        self.assertNotEqual(ordinary.returncode, 0)
        self.assertEqual(skipped.returncode, 0, skipped.stdout + skipped.stderr)
        self.assertIn("skipped", skipped.stdout.lower())
        self.assertEqual((self.root / "scripts/frozen_artifacts.sha256.json").read_bytes(), manifest)

    def test_skip_frozen_still_enforces_pinned_binary_digests(self):
        self.complete_fixture()
        self.write("external_software/pinned.whl", "changed binary\n")
        result = self.run_cli("--skip-frozen")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bundled pyvoro2 wheel digest mismatch", result.stdout)


if __name__ == "__main__":
    unittest.main()
