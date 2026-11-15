"""Numerical evidence checks, including independent aggregation fixtures."""

import csv
import importlib.util
import math
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/check_manuscript_tables.py"
sys.path.insert(0, str(ROOT / "scripts"))


def load_checker():
    # An explicit assertion gives a meaningful first RED before the new module exists.
    if not SOURCE.is_file():
        raise AssertionError("The current inline-table checker is not implemented")
    spec = importlib.util.spec_from_file_location("manuscript_tables", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_rows(relative):
    with (ROOT / "results" / relative).open(newline="") as stream:
        return list(csv.DictReader(stream))


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.checker = load_checker()

    def test_pooled_rmse_weights_edges_not_system_means(self):
        # Four errors of 3 from one system and one zero from another give
        # sqrt(36/5); averaging their two system RMS values would give 1.5.
        self.assertAlmostEqual(self.checker.pooled_rmse([3, 3, 3, 3, 0]), math.sqrt(7.2))
        self.assertAlmostEqual(self.checker.pooled_rmse([-3, 4]), math.sqrt(12.5))

    def test_ap_preserves_input_order_for_equal_scores(self):
        self.assertAlmostEqual(self.checker.average_precision([False, True, True], [2, 2, 1]), 7 / 12)
        self.assertAlmostEqual(self.checker.average_precision([True, False, True], [2, 2, 1]), 5 / 6)
        self.assertAlmostEqual(self.checker.average_precision([True, False, True], [2, 2, 3], descending=False), 5 / 6)

    def test_empty_and_nonfinite_metric_populations_are_rejected(self):
        for values in ([], [float("nan")], [float("inf")]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.checker.pooled_rmse(values)
        with self.assertRaises(ValueError):
            self.checker.average_precision([False], [1])
        with self.assertRaises(ValueError):
            self.checker.average_precision([True], [float("nan")])

    def test_duplicate_and_missing_method_pairs_are_rejected(self):
        for study, relative in (("E", "active_set/runs.csv"), ("H", "supergraph_mismatch/runs.csv")):
            rows = read_rows(relative)
            with self.subTest(study=study):
                with self.assertRaisesRegex(ValueError, "duplicate.*pair"):
                    self.checker.refinement_metrics(rows + [rows[0]], study)
                with self.assertRaisesRegex(ValueError, "missing.*method|incomplete.*pair"):
                    self.checker.refinement_metrics(rows[1:], study)

    def test_configuration_is_part_of_refinement_pair_identity(self):
        rows = read_rows("active_set/runs.csv")[:2]
        rows[1]["true_row_noise_sigma"] = "0.006"
        with self.assertRaisesRegex(ValueError, "missing.*method|incomplete.*pair"):
            self.checker.refinement_metrics(rows, "E")

    def test_refinement_counts_use_unrounded_changes_and_tolerance(self):
        rows = read_rows("active_set/runs.csv")[:2]
        rows[0].update(true_realized_separator_rmse="0.1", selected_pair_f1="0.5")
        rows[1].update(true_realized_separator_rmse="0.09999999999", selected_pair_f1="0.5000000000001")
        scores = self.checker.refinement_metrics(rows, "E")
        self.assertEqual(scores["RMSE"][2:], [1, 0, 0])
        self.assertEqual(scores["F1"][2:], [0, 1, 0])

    def test_j2_uses_raw_length_errors_and_includes_system_identity(self):
        rows = []
        for system, error, bonded in (("a", "3", True), ("b", "4", False)):
            rows.append(dict(system_key=system, atom_i="1", atom_j="2", is_bonded=str(bonded),
                             is_nonbonded=str(not bonded), err_midpoint_angstrom=error,
                             err_proatomic_angstrom=error, err_proatomic_powerfit_angstrom=error,
                             err_qtaim_ceiling_angstrom=error, err_proatomic_fraction="100", bond_length_angstrom="100"))
        metrics = self.checker.j2_metrics(rows)
        self.assertAlmostEqual(metrics["All"][1], math.sqrt(12.5))
        self.assertEqual(metrics["Bonded"], [3.0] * 4)
        self.assertEqual(metrics["Nonbonded"], [4.0] * 4)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.checker.j2_metrics(rows + [rows[0]])

    def test_j3_counts_whole_realized_graph_and_checks_reference_identity(self):
        def row(i, **fields):
            return dict(system_key="m", atom_i="1", atom_j=str(i), **fields)
        candidates = [row(2, is_qtaim_edge="True")]
        selected = [row(2, is_qtaim_edge="True", intersection_inside="True", err_recovered_angstrom="3"),
                    row(3, is_qtaim_edge="False", intersection_inside="True", err_recovered_angstrom="")]
        reference = [row(2, intersection_inside="True", err_recovered_angstrom="3")]
        self.assertEqual(self.checker.j3_metrics(candidates, selected, reference), [1, 2, 2, 3.0, 0.5, 1.0])
        reference[0]["atom_j"] = "4"
        with self.assertRaisesRegex(ValueError, "reference|identity"):
            self.checker.j3_metrics(candidates, selected, reference)

    def test_j3_pools_nonvisible_reference_errors_before_visibility_filtering(self):
        candidates = [dict(system_key="m", atom_i="1", atom_j=str(j), is_qtaim_edge="True")
                      for j in (2, 3)]
        reference = [dict(candidates[0], intersection_inside="True", err_recovered_angstrom="3"),
                     dict(candidates[1], intersection_inside="False", err_recovered_angstrom="4")]
        selected = [*reference, dict(system_key="m", atom_i="1", atom_j="4",
                                    is_qtaim_edge="False", intersection_inside="True")]
        # RMS includes errors 3 and 4, although only the first reference is visible.
        self.assertEqual(self.checker.j3_metrics(candidates, selected, reference),
                         [2, 3, 2, math.sqrt(12.5), 0.5, 0.5])

    def test_j3_rejects_an_unknown_system_in_the_whole_selected_graph(self):
        candidate = dict(system_key="known", atom_i="1", atom_j="2", is_qtaim_edge="True")
        reference = dict(candidate, intersection_inside="True", err_recovered_angstrom="3")
        selected = [reference, dict(system_key="unknown", atom_i="1", atom_j="3",
                                    is_qtaim_edge="False", intersection_inside="True")]
        with self.assertRaisesRegex(ValueError, "system.*population|population.*system"):
            self.checker.j3_metrics([candidate], selected, [reference])


class TableLocationTests(unittest.TestCase):
    def setUp(self):
        self.checker = load_checker()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def table(self, label="tab:reviewed", value="1.25"):
        return (r"\begin{table}\begin{tabular}{lr}\midrule "
                + f"A & {value}" + r" \\\bottomrule\end{tabular}"
                + rf"\label{{{label}}}\end{{table}}")

    def test_label_after_tabular_selects_its_owning_table(self):
        path = self.write("table.tex", self.table() + self.table("tab:other", "9.99"))
        self.assertEqual(self.checker.literal_rows(path, "tab:reviewed"), [["A", "1.25"]])

    def test_nested_active_inputs_and_orphan_duplicate_are_resolved(self):
        self.write("manuscript.tex", r"\input{chapter}")
        self.write("chapter.tex", r"\input{relocated/reviewed}")
        self.write("relocated/reviewed.tex", self.table())
        self.write("orphan.tex", self.table(value="9.99"))
        self.assertEqual(self.checker.literal_rows(self.root, "tab:reviewed"), [["A", "1.25"]])

    def test_commented_labels_and_inputs_do_not_count(self):
        self.write("manuscript.tex", "%\\input{absent}\n" + self.table() + "\n%\\label{tab:reviewed}\n")
        self.assertEqual(self.checker.literal_rows(self.root, "tab:reviewed"), [["A", "1.25"]])

    def test_orphan_table_cannot_satisfy_a_missing_active_label(self):
        self.write("manuscript.tex", "Ordinary text.\n")
        self.write("orphan.tex", self.table())
        with self.assertRaisesRegex(ValueError, "exactly one.*tab:reviewed"):
            self.checker.literal_rows(self.root, "tab:reviewed")

    def test_duplicate_active_labels_and_repeated_inputs_are_ambiguous(self):
        self.write("one.tex", self.table())
        self.write("two.tex", self.table())
        for inputs in (r"\input{one}\input{two}", r"\input{one}\input{one}"):
            with self.subTest(inputs=inputs):
                self.write("manuscript.tex", inputs)
                with self.assertRaisesRegex(ValueError, "exactly one.*tab:reviewed"):
                    self.checker.literal_rows(self.root, "tab:reviewed")

    def test_label_outside_a_table_does_not_capture_the_next_table(self):
        path = self.write("table.tex", r"\label{tab:reviewed}" + self.table("tab:other"))
        with self.assertRaisesRegex(ValueError, "enclosing table"):
            self.checker.literal_rows(path, "tab:reviewed")

    def test_labelled_empty_table_does_not_capture_the_next_tabular(self):
        path = self.write("table.tex", r"\begin{table}\label{tab:reviewed}\end{table}" + self.table("tab:other"))
        with self.assertRaisesRegex(ValueError, "tabular"):
            self.checker.literal_rows(path, "tab:reviewed")

    def test_unbalanced_environments_are_rejected(self):
        for bad in (self.table().replace(r"\end{table}", ""),
                    self.table().replace(r"\end{tabular}", r"\end{table}")):
            with self.subTest(bad=bad):
                path = self.write("table.tex", bad)
                with self.assertRaisesRegex(ValueError, "unbalanced"):
                    self.checker.literal_rows(path, "tab:reviewed")

    def test_input_cycle_is_rejected(self):
        self.write("manuscript.tex", r"\input{again}")
        self.write("again.tex", r"\input{manuscript}")
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            self.checker.literal_rows(self.root, "tab:reviewed")


class InlineTableTests(unittest.TestCase):
    def setUp(self):
        self.checker = load_checker()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        manuscript = self.root / "manuscript"
        manuscript.mkdir()
        # Existing corruption fixtures copy these source directories below.
        # Supply their authoritative active tree without introducing orphans.
        (manuscript / "manuscript.tex").write_text(
            r"\input{sections/06_experiments}\input{sections/07_molecular}\input{appendices/appendix_e}")

    def test_frozen_csvs_agree_with_all_four_real_tables(self):
        self.assertEqual(self.checker.check_tables(ROOT / "results", ROOT / "manuscript"), [])

    def test_all_reviewed_tables_can_move_to_new_active_source_paths(self):
        manuscript = self.root / "relocated-manuscript"
        manuscript.mkdir()
        moved = []
        for index, relative in enumerate(("sections/06_experiments.tex", "sections/07_molecular.tex", "appendices/appendix_e.tex")):
            target = manuscript / f"renamed-{index}.tex"
            original = (ROOT / "manuscript" / relative).read_text()
            text = original
            for label in ("tab:refinement-paired", "tab:molecular-fits", "tab:molecular-clearance-ranking", "tab:molecular-candidates"):
                marker = rf"\label{{{label}}}"
                if marker in text:
                    self.assertEqual(text.count(marker), 1)
                    text = text.replace(marker, "")
                    position = original.index(marker)
                    # Move the label to after its tabular while retaining its
                    # enclosing table and every independently checked number.
                    end = text.index(r"\end{tabular}", position) + len(r"\end{tabular}")
                    text = text[:end] + marker + text[end:]
            target.write_text(text)
            moved.append(rf"\input{{{target.stem}}}")
        (manuscript / "manuscript.tex").write_text("\n".join(moved))
        self.assertEqual(self.checker.check_tables(ROOT / "results", manuscript), [])

    def test_changed_tex_number_reports_table_row_and_column(self):
        manuscript = self.root / "manuscript"
        shutil.copytree(ROOT / "manuscript" / "sections", manuscript / "sections")
        shutil.copytree(ROOT / "manuscript" / "appendices", manuscript / "appendices")
        path = manuscript / "sections/07_molecular.tex"
        path.write_text(path.read_text().replace("All & 0.1332", "All & 0.1333"))
        errors = self.checker.check_tables(ROOT / "results", manuscript)
        self.assertTrue(any("tab:molecular-fits" in e and "All" in e and "Midpoint" in e for e in errors), errors)

    def test_missing_table_label_is_rejected(self):
        manuscript = self.root / "manuscript"
        shutil.copytree(ROOT / "manuscript" / "sections", manuscript / "sections")
        shutil.copytree(ROOT / "manuscript" / "appendices", manuscript / "appendices")
        path = manuscript / "sections/06_experiments.tex"
        path.write_text(path.read_text().replace(r"\label{tab:refinement-paired}", ""))
        errors = self.checker.check_tables(ROOT / "results", manuscript)
        self.assertTrue(any("tab:refinement-paired" in e for e in errors), errors)

    def test_population_loss_is_rejected_even_if_rounded_scores_could_agree(self):
        results = self.root / "results"
        for directory in ("active_set", "supergraph_mismatch", "qtaim_main"):
            (results / directory).mkdir(parents=True)
        for relative in ("active_set/runs.csv", "supergraph_mismatch/runs.csv",
                         "qtaim_main/J2_true_support_ladder", "qtaim_main/J3_candidate_recovery_refresh"):
            (results / relative).symlink_to(ROOT / "results" / relative, target_is_directory=not relative.endswith("csv"))
        target = results / "qtaim_main/J4_mask_transfer_refresh/edge_level.csv"
        target.parent.mkdir()
        rows = read_rows("qtaim_main/J4_mask_transfer_refresh/edge_level.csv")
        drop = next(i for i, row in enumerate(rows) if row["model"] == "voronoi" and row["keep_visible"] == "True" and row["is_nonbonded"] == "True")
        del rows[drop]
        with target.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        errors = self.checker.check_tables(results, ROOT / "manuscript")
        self.assertTrue(any("tab:molecular-clearance-ranking" in e and "population" in e for e in errors), errors)

    def test_j4b_rejects_unknown_system_on_eligible_negative_in_each_model(self):
        results = self.root / "results"
        for directory in ("active_set", "supergraph_mismatch", "qtaim_main"):
            (results / directory).mkdir(parents=True)
        for relative in ("active_set/runs.csv", "supergraph_mismatch/runs.csv",
                         "qtaim_main/J2_true_support_ladder", "qtaim_main/J3_candidate_recovery_refresh"):
            (results / relative).symlink_to(ROOT / "results" / relative, target_is_directory=not relative.endswith("csv"))
        target = results / "qtaim_main/J4_mask_transfer_refresh/edge_level.csv"
        target.parent.mkdir()
        for model in ("voronoi", "recovered_powerfit"):
            with self.subTest(model=model):
                rows = read_rows("qtaim_main/J4_mask_transfer_refresh/edge_level.csv")
                row = next(row for row in rows if row["model"] == model and row["keep_visible"] == "True"
                           and row["is_nonbonded"] == "True" and row["is_qtaim_edge"] == "False")
                row["system_key"] = "not_in_100_system_manifest"
                with target.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                errors = self.checker.check_tables(results, ROOT / "manuscript")
                self.assertTrue(any("tab:molecular-clearance-ranking" in error and "system" in error
                                    and "not_in_100_system_manifest" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
