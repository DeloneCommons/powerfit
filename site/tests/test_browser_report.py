"""Browser expectations must come from a successful, current source report."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser_check


class BrowserReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.article = root / 'article.html'
        self.article.write_text('<article><math>x</math></article>')
        self.report = root / 'source-validation.json'
        self.expected = {
            'math': 3, 'figures': 0, 'tables': 0, 'bibliography': 0,
            'toc_targets': ['section-one'], 'reference_targets': [],
            'bibliography_targets': [], 'capture_targets': ['section-one'],
            'contrast_targets': [],
        }
        self.record = {'schema_version': 1, 'valid': True,
                       'article_sha256': hashlib.sha256(self.article.read_bytes()).hexdigest(),
                       'browser': self.expected}
        self.save()

    def save(self):
        self.report.write_text(json.dumps(self.record))

    def load(self):
        self.assertTrue(hasattr(browser_check, 'load_browser_expectations'),
                        'trusted browser report loader is not implemented')
        return browser_check.load_browser_expectations(self.report, self.article)

    def test_expected_counts_are_report_values_even_when_dom_disagrees(self):
        self.assertEqual(self.load(), self.expected)
        self.assertEqual(self.load()['math'], 3)

    def test_missing_report_fails(self):
        self.report.unlink()
        with self.assertRaisesRegex(ValueError, 'source-validation report'):
            self.load()

    def test_unsuccessful_or_unknown_report_fails(self):
        for key, value in [('valid', False), ('valid', 'true'), ('schema_version', 2)]:
            with self.subTest(key=key, value=value):
                original = self.record[key]
                self.record[key] = value
                self.save()
                with self.assertRaisesRegex(ValueError, 'source-validation report'):
                    self.load()
                self.record[key] = original

    def test_changed_article_cannot_use_a_stale_report(self):
        self.article.write_text('<article>changed</article>')
        with self.assertRaisesRegex(ValueError, 'stale|hash'):
            self.load()

    def test_missing_or_malformed_expected_counts_fail(self):
        for field in ('math', 'figures', 'tables', 'bibliography'):
            for bad in (-1, True, '3', None):
                with self.subTest(field=field, bad=bad):
                    self.record['browser'][field] = bad
                    self.save()
                    with self.assertRaisesRegex(ValueError, field):
                        self.load()
            self.record['browser'][field] = 0
        del self.record['browser']['math']
        self.save()
        with self.assertRaisesRegex(ValueError, 'math'):
            self.load()

    def test_missing_or_malformed_target_lists_fail(self):
        for field in ('toc_targets', 'reference_targets', 'bibliography_targets', 'capture_targets', 'contrast_targets'):
            for bad in (None, 'S1', [''], [False], ['same', 'same']):
                with self.subTest(field=field, bad=bad):
                    self.record['browser'][field] = bad
                    self.save()
                    with self.assertRaisesRegex(ValueError, field):
                        self.load()
            self.record['browser'][field] = []


if __name__ == '__main__':
    unittest.main()
