"""Exercise frozen local figure inputs and their integrity checks."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest


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

    def test_local_sources_retain_frozen_populations_and_hash(self):
        local_c = self.load(editorial.load_profiles, results_root=ROOT / "results")
        local_g = self.load(experiment_g.load_runs, results_root=ROOT / "results")
        self.assertEqual(set(local_c), {2, 3})
        self.assertEqual([len(local_c[dim]) for dim in (2, 3)], [19, 19])
        self.assertEqual(len(local_g.runs), 2160)
        self.assertEqual(local_g.source_sha256,
                         "8af39990eb3f1931a79f08099ddfea3b42974121ebd0c25bf71a3b0101af0a5c")

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

    def test_changed_frozen_csv_is_rejected(self):
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


if __name__ == "__main__":
    unittest.main()
