"""Exercise frozen figure inputs through both supported source transports."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import plot_editorial_figures as editorial
import plot_experiment_g as experiment_g


SOURCE_FILES = (
    "results/missing_data_manuscript/runs.csv",
    "results/missing_data_manuscript/manuscript_analysis/summary.csv",
    "results/missing_data_manuscript/metadata.json",
    "results/model_mismatch/runs.csv",
    "results/model_mismatch/metadata.json",
    "experiments/analysis/plot_missing_data_manuscript.py",
)


class FrozenFigureSources(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def load(self, loader, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return loader(*args, **kwargs)

    def copy_results(self):
        for relative in SOURCE_FILES:
            destination = self.directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        return self.directory / "results"

    def make_archive(self, prefix="", source_root=ROOT):
        path = self.directory / "frozen.zip"
        with ZipFile(path, "w") as archive:
            for relative in SOURCE_FILES:
                archive.write(source_root / relative, prefix + relative)
        return path

    def test_local_and_bare_or_prefixed_zip_sources_are_identical(self):
        local_c = self.load(editorial.load_profiles, results_root=ROOT / "results")
        local_g = self.load(experiment_g.load_runs, results_root=ROOT / "results")
        self.assertEqual(set(local_c), {2, 3})
        self.assertEqual([len(local_c[dim]) for dim in (2, 3)], [19, 19])
        self.assertEqual(len(local_g.runs), 2160)
        self.assertEqual(local_g.source_sha256,
                         "8af39990eb3f1931a79f08099ddfea3b42974121ebd0c25bf71a3b0101af0a5c")
        for prefix in ("", "powerfit-80933a1/"):
            with self.subTest(prefix=prefix):
                archive = self.make_archive(prefix)
                archived_c = self.load(editorial.load_profiles, archive)
                archived_g = self.load(experiment_g.load_runs, archive)
                for dimension in (2, 3):
                    pd.testing.assert_frame_equal(local_c[dimension], archived_c[dimension], check_exact=True)
                pd.testing.assert_frame_equal(local_g.runs, archived_g.runs, check_exact=True)
                self.assertEqual(local_g.source_sha256, archived_g.source_sha256)

    def test_default_results_are_repo_relative_from_another_directory(self):
        previous = Path.cwd()
        try:
            os.chdir(self.directory)
            profiles = self.load(editorial.load_profiles)
            runs = self.load(experiment_g.load_runs)
        finally:
            os.chdir(previous)
        self.assertEqual(len(profiles[2]), 19)
        self.assertEqual(len(runs.runs), 2160)

    def test_changed_frozen_csv_is_rejected_for_local_and_zip_sources(self):
        results = self.copy_results()
        for relative, loader in (
            ("results/missing_data_manuscript/runs.csv", editorial.load_profiles),
            ("results/missing_data_manuscript/manuscript_analysis/summary.csv", editorial.load_profiles),
            ("results/model_mismatch/runs.csv", experiment_g.load_runs),
        ):
            with self.subTest(source=relative):
                source = self.directory / relative
                original = source.read_bytes()
                # Even a CSV-preserving edit must not replace the frozen source.
                source.write_bytes(original + b"\n")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    self.load(loader, results_root=results)
                archive = self.make_archive("powerfit-80933a1/", self.directory)
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    self.load(loader, archive)
                source.write_bytes(original)

    def test_frozen_population_metadata_still_validated_locally(self):
        results = self.copy_results()
        for relative, loader in (
            ("missing_data_manuscript/metadata.json", editorial.load_profiles),
            ("model_mismatch/metadata.json", experiment_g.load_runs),
        ):
            with self.subTest(source=relative):
                path = results / relative
                metadata = json.loads(path.read_text())
                metadata["n_runs"] -= 1
                path.write_text(json.dumps(metadata))
                with self.assertRaises(ValueError):
                    self.load(loader, results_root=results)

    def test_archive_and_results_root_are_mutually_exclusive(self):
        archive = self.make_archive()
        for loader in (editorial.load_profiles, experiment_g.load_runs):
            with self.subTest(loader=loader.__name__):
                with self.assertRaisesRegex(ValueError, "either"):
                    self.load(loader, archive, results_root=ROOT / "results")

    def test_ambiguous_archive_members_are_rejected(self):
        archive_path = self.make_archive()
        with ZipFile(archive_path, "a") as archive:
            for relative in (SOURCE_FILES[0], SOURCE_FILES[3]):
                archive.write(ROOT / relative, "duplicate/" + relative)
        for loader in (editorial.load_profiles, experiment_g.load_runs):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(ValueError):
                    self.load(loader, archive_path)


if __name__ == "__main__":
    unittest.main()
