"""Independent completeness fixtures; no scientific code runs in these tests."""

import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/check_rerun_results.py"
SYNTHETIC = {
    "exact_recovery": 16, "noise_robustness": 144, "missing_data": 30,
    "missing_data_manuscript": 2470, "infeasible": 30, "active_set": 40,
    "periodic": 132, "model_mismatch": 2280, "supergraph_mismatch": 192,
}
MARGINS = ["J4_mask_transfer_refresh", "J4_mask_transfer_margin3_refresh",
           "J4_mask_transfer_margin7_refresh", "J4_mask_transfer_margin10_refresh"]
MODELS = ["voronoi", "recovered_powerfit"]


class RerunCompletenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # An explicit assertion makes the initial RED explain the missing feature.
        assert SOURCE.is_file(), "Read-only rerun completeness checker is missing"
        spec = importlib.util.spec_from_file_location("rerun_results", SOURCE)
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.results = self.root / "results"
        self.systems = [f"molecule_{i:03}" for i in range(100)]
        self.manifest = self.root / "systems.csv"
        self.csv(self.manifest, [{"system_key": key} for key in self.systems])
        self.addCleanup(patch.stopall)
        patch.object(self.checker, "MANIFEST_PATH", self.manifest).start()
        self.complete_fixture()

    def csv(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def read_csv(self, path):
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def update_json(self, relative, **changes):
        path = self.results / relative
        value = json.loads(path.read_text())
        value.update(changes)
        self.json(path, value)

    def complete_fixture(self):
        for name, count in SYNTHETIC.items():
            self.json(self.results / name / "metadata.json", {"n_runs": count})
            self.csv(self.results / name / "runs.csv", [
                {"seed": i, "status": "optimal", "converged": False,
                 "termination": "cycle_detected"} for i in range(count)])
        for name in ["J1_dataset_audit", "J2_true_support_ladder",
                     "J3_candidate_recovery_refresh", *MARGINS]:
            directory = self.results / "qtaim_main" / name
            summary = {"n_manifest_rows": 100, "n_processed_rows": 100, "n_skipped_rows": 0}
            rows = [{"system_key": key} for key in self.systems]
            if name.startswith("J2"):
                rows = [dict(row, fit_status_proatomic_powerfit="optimal",
                             fit_status_qtaim_ceiling="optimal") for row in rows]
            if name.startswith("J3"):
                summary.update(cutoffs_angstrom=[4, 4.5, 5], n_cutoff_runs=300)
                rows = [dict(row, cutoff_angstrom=cutoff, fit_status="optimal")
                        for row in rows for cutoff in [4, 4.5, 5]]
            if name.startswith("J4"):
                rows = [dict(row, model=model) for row in rows for model in MODELS]
            self.json(directory / "summary.json", summary)
            self.csv(directory / "molecule_level.csv", rows)
            (directory / "skipped_rows.csv").write_text("\n")
        directory = self.results / "qtaim_main/J4_local_diagnostic_validation"
        diagnostics = [{"model": model, "n_faces": 20, "n_visible_faces": 8,
                        "n_visibility_mismatches": 0, "max_abs_clearance_diff": 3e-15}
                       for model in MODELS]
        self.json(directory / "summary.json", {
            "n_models": 2, "total_faces": 40, "total_visible_faces": 16,
            "total_visibility_mismatches": 0, "max_abs_clearance_diff": 3e-15,
            "by_model": diagnostics})
        self.csv(directory / "summary.csv", diagnostics)
        directory = self.results / "qtaim_main/J4_box_margin_summary_refresh"
        self.json(directory / "summary.json", {"n_runs": 4, "labels": ["3A", "5A", "7A", "10A"]})
        self.csv(directory / "summary.csv", [
            {"label": label, "model": model, "subset": subset}
            for label in ["3A", "5A", "7A", "10A"] for model in MODELS
            for subset in ["all", "nonbonded", "visible_nonbonded_ranking"]])

    def errors(self):
        return self.checker.check_results(self.results)

    def test_complete_populations_and_legitimate_h_cycles_pass(self):
        self.assertEqual(self.errors(), [])

    def test_missing_synthetic_row_and_metadata_disagreement_are_rejected(self):
        self.csv(self.results / "exact_recovery/runs.csv", [{"status": "optimal"}] * 15)
        self.assertTrue(any("exact_recovery" in e and "16" in e for e in self.errors()))
        self.update_json("noise_robustness/metadata.json", n_runs=143)
        self.assertTrue(any("noise_robustness" in e and "n_runs" in e for e in self.errors()))

    def test_skipped_molecular_summary_and_nonempty_skip_file_are_rejected(self):
        self.update_json("qtaim_main/J2_true_support_ladder/summary.json", n_skipped_rows=1)
        self.assertTrue(any("J2" in e and "n_skipped_rows" in e for e in self.errors()))
        self.csv(self.results / "qtaim_main/J1_dataset_audit/skipped_rows.csv", [{"system_key": "absent"}])
        self.assertTrue(any("J1" in e and "skipped_rows.csv" in e for e in self.errors()))

    def test_same_length_duplicate_cannot_replace_a_missing_system_cutoff(self):
        path = self.results / "qtaim_main/J3_candidate_recovery_refresh/molecule_level.csv"
        rows = self.read_csv(path)
        rows[-1] = rows[0]
        self.csv(path, rows)
        self.assertTrue(any("J3" in e and "identit" in e for e in self.errors()))

    def test_missing_j4_model_population_is_rejected(self):
        path = self.results / "qtaim_main/J4_mask_transfer_margin7_refresh/molecule_level.csv"
        rows = self.read_csv(path)
        self.csv(path, [row for row in rows if row["model"] == "voronoi"])
        self.assertTrue(any("margin7" in e and "identit" in e for e in self.errors()))

    def test_failed_fit_is_rejected_without_requiring_outer_convergence(self):
        path = self.results / "qtaim_main/J2_true_support_ladder/molecule_level.csv"
        rows = self.read_csv(path)
        rows[0]["fit_status_qtaim_ceiling"] = "failed"
        self.csv(path, rows)
        self.assertTrue(any("J2" in e and "fit_status_qtaim_ceiling" in e for e in self.errors()))

    def test_j4a_nonfinite_or_excessive_difference_and_mismatch_are_rejected(self):
        relative = "qtaim_main/J4_local_diagnostic_validation/summary.json"
        for value in [float("nan"), float("inf"), 1e-8]:
            with self.subTest(value=value):
                self.update_json(relative, max_abs_clearance_diff=value)
                self.assertTrue(any("max_abs_clearance_diff" in e for e in self.errors()))
        self.update_json(relative, max_abs_clearance_diff=3e-15, total_visibility_mismatches=1)
        self.assertTrue(any("visibility_mismatches" in e for e in self.errors()))

    def test_j4a_missing_model_or_csv_disagreement_is_rejected(self):
        relative = "qtaim_main/J4_local_diagnostic_validation/summary.json"
        path = self.results / relative
        summary = json.loads(path.read_text())
        summary["by_model"] = summary["by_model"][:1]
        self.json(path, summary)
        self.assertTrue(any("J4_local" in e and "model" in e for e in self.errors()))

    def test_j4d_duplicate_population_and_wrong_cutoff_summary_are_rejected(self):
        relative = "qtaim_main/J4_box_margin_summary_refresh/summary.csv"
        path = self.results / relative
        rows = self.read_csv(path)
        rows[-1] = rows[0]
        self.csv(path, rows)
        self.assertTrue(any("box_margin" in e and "identit" in e for e in self.errors()))
        self.update_json("qtaim_main/J3_candidate_recovery_refresh/summary.json", cutoffs_angstrom=[4, 5])
        self.assertTrue(any("cutoffs_angstrom" in e for e in self.errors()))

    def test_missing_result_file_reports_its_population(self):
        (self.results / "periodic/runs.csv").unlink()
        self.assertTrue(any("periodic" in e and "runs.csv" in e for e in self.errors()))

    def test_failed_synthetic_fit_and_wrong_cutoff_run_count_are_rejected(self):
        path = self.results / "supergraph_mismatch/runs.csv"
        rows = self.read_csv(path)
        rows[0]["status"] = "failed"
        self.csv(path, rows)
        self.assertTrue(any("supergraph_mismatch" in e and "status" in e for e in self.errors()))
        self.update_json("qtaim_main/J3_candidate_recovery_refresh/summary.json", n_cutoff_runs=299)
        self.assertTrue(any("n_cutoff_runs" in e for e in self.errors()))

    def test_j4a_csv_nan_and_json_csv_disagreement_are_rejected(self):
        path = self.results / "qtaim_main/J4_local_diagnostic_validation/summary.csv"
        rows = self.read_csv(path)
        rows[0]["max_abs_clearance_diff"] = "nan"
        self.csv(path, rows)
        self.assertTrue(any("finite" in e for e in self.errors()))
        rows[0]["max_abs_clearance_diff"] = "4e-15"
        self.csv(path, rows)
        self.assertTrue(any("disagree" in e for e in self.errors()))

    def test_j4a_zero_face_population_is_rejected(self):
        relative = "qtaim_main/J4_local_diagnostic_validation/summary.json"
        summary = json.loads((self.results / relative).read_text())
        summary["by_model"][0]["n_faces"] = 0
        self.json(self.results / relative, summary)
        self.assertTrue(any("population" in e for e in self.errors()))

    def test_real_frozen_tree_passes(self):
        with patch.object(self.checker, "MANIFEST_PATH", ROOT / "data/qtaim_main/systems_final.csv"):
            self.assertEqual(self.checker.check_results(ROOT / "results"), [])


class RerunPreflightTests(unittest.TestCase):
    def run_preflight(self, imported, distributed):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            wrapper = root / "scripts/rerun_paper_results.sh"
            wrapper.write_bytes((ROOT / "scripts/rerun_paper_results.sh").read_bytes())
            package = root / "pyvoro2"
            package.mkdir()
            (package / "__init__.py").write_text(f"__version__ = {imported!r}\n")
            metadata = root / f"pyvoro2-{distributed}.dist-info"
            metadata.mkdir()
            (metadata / "METADATA").write_text(f"Name: pyvoro2\nVersion: {distributed}\n")
            runner = root / "experiments/runners/run_exact_recovery.py"
            runner.parent.mkdir(parents=True)
            runner.write_text("raise SystemExit('FIRST_SCIENTIFIC_COMMAND')\n")
            return subprocess.run(["bash", str(wrapper)], capture_output=True, text=True,
                                  env=dict(os.environ, PYTHON=sys.executable, PYTHONPATH=str(root),
                                           PYTHONDONTWRITEBYTECODE="1"))

    def test_incompatible_import_or_distribution_stops_before_science(self):
        for imported, distributed in [("0.6.2", "0.6.3"), ("0.6.3", "0.6.2")]:
            with self.subTest(imported=imported, distributed=distributed):
                result = self.run_preflight(imported, distributed)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("FIRST_SCIENTIFIC_COMMAND", result.stderr)
                self.assertIn("0.6.3", result.stdout + result.stderr)

    def test_pinned_import_and_distribution_report_interpreter_then_start_science(self):
        result = self.run_preflight("0.6.3", "0.6.3")
        self.assertIn("FIRST_SCIENTIFIC_COMMAND", result.stderr)
        self.assertIn(sys.executable, result.stdout)
        self.assertIn("pyvoro2", result.stdout)


if __name__ == "__main__":
    unittest.main()
