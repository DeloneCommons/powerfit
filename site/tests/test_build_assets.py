"""Distinct PDF sources must never silently share one public SVG destination."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build


class FigureDestinationTests(unittest.TestCase):
    def test_existing_urls_are_preserved(self):
        paths = [Path('/paper/figures/overview.pdf'), Path('/paper/extra/detail.pdf')]
        self.assertEqual(build.figure_destinations(paths), {
            paths[0]: 'figures/overview.svg', paths[1]: 'figures/detail.svg'})

    def test_distinct_sources_with_same_basename_fail_before_conversion(self):
        paths = [Path('/paper/figures/result.pdf'), Path('/paper/extra/result.pdf')]
        with self.assertRaisesRegex(ValueError, 'Figure output collision.*result.svg'):
            build.figure_destinations(paths)

    def test_repeated_same_source_is_one_asset(self):
        path = Path('/paper/figures/result.pdf')
        self.assertEqual(build.figure_destinations([path, path]), {path: 'figures/result.svg'})


if __name__ == '__main__':
    unittest.main()
