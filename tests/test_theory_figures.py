"""Independent geometric checks of explanatory figures, not experiments."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from PIL import Image


SOURCE = Path(__file__).resolve().parents[1] / "scripts/plot_theory_figures.py"
SPEC = importlib.util.spec_from_file_location("theory_figures", SOURCE)
figures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(figures)


class RealizationConstruction(unittest.TestCase):
    def test_realization_vector_exports_render(self):
        figures.configure_style()
        with TemporaryDirectory() as tmp:
            figures.draw_realization(Path(tmp))
            self.assertTrue((Path(tmp) / "figure_04_realization.pdf").read_bytes().startswith(b"%PDF"))
            svg = (Path(tmp) / "figure_04_realization.svg").read_text()
            self.assertIn("<svg", svg)
            self.assertNotIn("<image", svg)

    def test_pair_face_intervals_and_connector_gaps(self):
        points = np.array([[0., 0.], [2., 0.], [1., 1.], [1., -1.]])
        for weights, expected, gaps in [
            ([0., 0., 1., 1.], None, [-1., -1.]),
            ([0., 0., 1., -3.], (-1.5, -0.5), [-1., 3.]),
            ([0., 0., -1., -1.], (-0.5, 0.5), [1., 1.]),
        ]:
            with self.subTest(weights=weights):
                weights = np.array(weights)
                q, direction, interval = figures.pair_face(points, weights, 0, 1)
                np.testing.assert_allclose(q, [1., 0.], atol=1e-14)
                np.testing.assert_allclose(direction, [0., 1.], atol=1e-14)
                self.assertEqual(interval, expected)
                powers = ((points - q) ** 2).sum(axis=1) - weights
                np.testing.assert_allclose(powers[2:] - powers[0], gaps)

    def test_degenerate_singleton_remains_distinct_from_an_edge(self):
        points = np.array([[0., 0.], [2., 0.], [1., 1.], [1., -1.]])
        _, _, interval = figures.pair_face(points, np.array([0., 0., 1., -1.]), 0, 1)
        self.assertEqual(interval, (-0.5, -0.5))

    def test_cell_fill_is_the_power_minimum_partition(self):
        points = np.array([[0., 0.], [2., 0.], [1., 1.], [1., -1.]])
        window = (-0.6, 2.6, -1.9, 1.4)
        expected_area = (window[1] - window[0]) * (window[3] - window[2])
        for weights in [[0., 0., 1., 1.], [0., 0., 1., -3.], [0., 0., -1., -1.]]:
            weights = np.array(weights)
            cells = figures.power_cells(points, weights, window)
            total_area = 0.
            for i, poly in enumerate(cells):
                self.assertGreaterEqual(len(poly), 3)
                # Power differences are affine: vertex checks certify the whole polygon.
                powers = ((poly[:, None, :] - points) ** 2).sum(axis=2) - weights
                self.assertTrue(np.all(powers[:, [i]] <= powers + 1e-12))
                area = 0.5 * abs(np.dot(poly[:, 0], np.roll(poly[:, 1], 1))
                                 - np.dot(poly[:, 1], np.roll(poly[:, 0], 1)))
                self.assertGreater(area, 0.)
                total_area += area
            self.assertAlmostEqual(total_area, expected_area, places=12)

    def test_displaced_face_contains_p4_but_not_cell4(self):
        points = np.array([[0., 0.], [2., 0.], [1., 1.], [1., -1.]])
        powers = ((points - points[3]) ** 2).sum(axis=1) - np.array([0., 0., 1., -3.])
        np.testing.assert_array_equal(powers, [2., 2., 3., 3.])

    def test_centered_clearance_and_asymmetric_face(self):
        points = np.array([[0., 0.], [2., 0.], [1., 1.], [1., -1.]])
        q, direction, interval = figures.pair_face(points, np.array([0., 0., -1., -1.]), 0, 1)
        self.assertEqual(min(-interval[0], interval[1]), 0.5)
        for t in [-0.5, 0., 0.5]:
            x = q + t * direction
            powers = ((points - x) ** 2).sum(axis=1) - np.array([0., 0., -1., -1.])
            self.assertLessEqual(powers[0], min(powers) + 1e-14)
        # A shifted endpoint cannot be used to equate clearance with half-length.
        _, _, asymmetric = figures.pair_face(points, np.array([0., 0., -3., -1.]), 0, 1)
        self.assertEqual(min(-asymmetric[0], asymmetric[1]), 0.5)
        self.assertEqual((asymmetric[1] - asymmetric[0]) / 2, 1.0)


class SeparatorConstruction(unittest.TestCase):
    def test_two_site_positions_and_weight_shift(self):
        points = np.array([[0., 0.], [2., 0.]])
        for weights, x in [([0., 0.], 1.), ([0., 2.], 0.5), ([7., 9.], 0.5)]:
            weights = np.array(weights)
            q, direction, interval = figures.pair_face(points, weights, 0, 1)
            np.testing.assert_array_equal(q, [x, 0.])
            self.assertEqual(interval, (-np.inf, np.inf))
            self.assertEqual((2 * (x / 2) - 1) * 4, weights[0] - weights[1])
            for s in [-2., 0., 2.]:
                powers = ((points - (q + s * direction)) ** 2).sum(axis=1) - weights
                self.assertEqual(powers[0], powers[1])

    def test_separator_vector_exports_render(self):
        figures.configure_style()
        with TemporaryDirectory() as tmp:
            figures.draw_separators(Path(tmp))
            self.assertTrue((Path(tmp) / "figure_02_separators.pdf").read_bytes().startswith(b"%PDF"))
            self.assertNotIn("<image", (Path(tmp) / "figure_02_separators.svg").read_text())


class CycleConstruction(unittest.TestCase):
    def test_orientation_signed_cycle_and_least_squares(self):
        edges, targets, traversal = figures.cycle_data()
        self.assertEqual(edges, [(0, 1), (1, 2), (0, 2)])
        np.testing.assert_array_equal(targets, [0., 0., 1.])
        np.testing.assert_array_equal(traversal, [1., 1., -1.])
        incidence = np.zeros((3, 3))
        for r, (i, j) in enumerate(edges):
            incidence[i, r], incidence[j, r] = 1, -1
        np.testing.assert_array_equal(incidence @ traversal, np.zeros(3))
        self.assertEqual(traversal @ targets, -1.)
        # Independently check the unchanged later prose's equal-rho compromise.
        w = np.array([2/3, 1/3, 0.])
        residuals = incidence.T @ w - targets
        np.testing.assert_allclose(residuals, [1/3, 1/3, -1/3], atol=1e-14)
        np.testing.assert_allclose(incidence @ residuals, np.zeros(3), atol=1e-14)

    def test_cycle_vector_exports_render(self):
        figures.configure_style()
        with TemporaryDirectory() as tmp:
            figures.draw_cycle(Path(tmp))
            self.assertTrue((Path(tmp) / "figure_03_cycle.pdf").read_bytes().startswith(b"%PDF"))
            self.assertNotIn("<image", (Path(tmp) / "figure_03_cycle.svg").read_text())


class WorkflowConstruction(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pdftoppm"), "Poppler pdftoppm is needed for rendered parity")
    def test_workflow_render_matches_canonical_pdf(self):
        figures.configure_style()
        with TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            figures.draw_workflow(temporary)
            canonical = SOURCE.parents[1] / "manuscript/figures/figure_05_workflow.pdf"
            for label, source in (("approved", canonical),
                                  ("generated", temporary / canonical.name)):
                subprocess.run(["pdftoppm", "-r", "300", "-singlefile", "-png",
                                str(source), str(temporary / label)],
                               check=True, capture_output=True)
            with Image.open(temporary / "approved.png") as a, Image.open(temporary / "generated.png") as b:
                np.testing.assert_array_equal(np.asarray(a), np.asarray(b))

    @unittest.skipUnless(shutil.which("pdffonts"), "Poppler pdffonts is needed")
    def test_canonical_workflow_embeds_every_font(self):
        canonical = SOURCE.parents[1] / "manuscript/figures/figure_05_workflow.pdf"
        result = subprocess.run(["pdffonts", str(canonical)],
                                check=True, capture_output=True, text=True)
        rows = [line.split() for line in result.stdout.splitlines()[2:] if line.strip()]
        self.assertTrue(rows)
        self.assertEqual([row[0] for row in rows if row[-5] != "yes"], [])

    @unittest.skipUnless(shutil.which("pdftotext"), "Poppler pdftotext is needed")
    def test_canonical_workflow_has_no_hidden_old_header(self):
        canonical = SOURCE.parents[1] / "manuscript/figures/figure_05_workflow.pdf"
        result = subprocess.run(["pdftotext", str(canonical), "-"],
                                check=True, capture_output=True, text=True)
        self.assertIn("Connector diagnostics", " ".join(result.stdout.split()))
        self.assertNotIn("Separate checks", result.stdout)
        self.assertNotIn("(§4)", result.stdout)

    def test_feedback_does_not_touch_separate_diagnostic_boxes(self):
        # Crossing a diagnostic box would visually imply that it drives updates.
        boxes = [(3.65, 5.50, 2.44, 3.00), (3.65, 5.50, 1.67, 2.27)]
        for route in figures.workflow_routes():
            if route["kind"] != "feedback":
                continue
            for a, b in zip(route["points"], route["points"][1:]):
                for xmin, xmax, ymin, ymax in boxes:
                    hit = (max(min(a[0], b[0]), xmin) <= min(max(a[0], b[0]), xmax)
                           and max(min(a[1], b[1]), ymin) <= min(max(a[1], b[1]), ymax))
                    self.assertFalse(hit, (route["source"], route["target"], a, b))

    def test_matching_scope_and_feedback_sources(self):
        routes = figures.workflow_routes()
        pairs = {(r["source"], r["target"]) for r in routes}
        self.assertTrue({("observations", "fit"), ("observations", "matching"),
                         ("weights", "residuals"), ("weights", "connector"),
                         ("active", "fit")} <= pairs)
        self.assertEqual({r["source"] for r in routes if r["target"] == "streaks"}, {"matching"})
        self.assertEqual({(r["source"], r["target"]) for r in routes if r["kind"] == "feedback"},
                         {("matching", "streaks"), ("streaks", "active"), ("active", "fit")})
        self.assertFalse(any(r["source"] in ("residuals", "connector", "outputs")
                             for r in routes))

    def test_workflow_vector_exports_render(self):
        figures.configure_style()
        with TemporaryDirectory() as tmp:
            figures.draw_workflow(Path(tmp))
            self.assertTrue((Path(tmp) / "figure_05_workflow.pdf").read_bytes().startswith(b"%PDF"))
            self.assertNotIn("<image", (Path(tmp) / "figure_05_workflow.svg").read_text())


if __name__ == "__main__":
    unittest.main()
