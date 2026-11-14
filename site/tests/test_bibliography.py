"""DOI metadata parsing follows BibTeX field boundaries, not line layout."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bibliography import source_dois


class BibliographyTests(unittest.TestCase):
    def parse(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'refs.bib'
            path.write_text(source)
            return source_dois(path)

    def test_single_line_entry(self):
        self.assertEqual(self.parse('@article{Example, title={Example}, doi={10.1234/example}}'),
                         {'example': '10.1234/example'})

    def test_doi_after_another_field_with_nested_braces_and_quotes(self):
        source = '@article{Example,\n title={A {nested, doi={fake}} title}, year=2026, doi="10.1234/example",\n note="A comma, and {a protected \\"quote\\"}",\n}'
        self.assertEqual(self.parse(source), {'example': '10.1234/example'})

    def test_missing_doi_is_distinct_from_text_mentioning_doi(self):
        self.assertEqual(self.parse('@book{Example, title="A title, doi={not a field}", year={2026}}'),
                         {'example': None})

    def test_unsupported_or_malformed_doi_fails_explicitly(self):
        for value in ('prefix # {suffix}', '{10.1234/one} # "two"', 'macro',
                      '{10.1234/unclosed', '"10.1234/unclosed', '{bad-doi}',
                      '{10.1234/one}, doi={10.1234/two}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.parse('@article{Example, title={Example}, doi=' + value + '}')


if __name__ == '__main__':
    unittest.main()
