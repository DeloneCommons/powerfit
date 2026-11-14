"""DOI metadata parsing follows BibTeX field boundaries, not line layout."""
import sys
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from lxml import etree, html
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bibliography import source_dois, validate_bibliography_dois

ROOT = Path(__file__).resolve().parents[2]
ESCAPED_DELIMITER_FIXTURE = r'''@article{Example,
  author={Author, Alice},
  title={A normal title},
  journal={A journal},
  year={2026},
  file={A \},
  doi={10.1234/example},
  annotation={B \{C}}
}'''


class BibliographyTests(unittest.TestCase):
    def parse(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'refs.bib'
            path.write_text(source)
            return source_dois(path)

    def test_single_line_entry(self):
        self.assertEqual(self.parse('@article{Example, title={Example}, doi={10.1234/example}}'),
                         {'example': '10.1234/example'})

    def test_escaped_delimiter_fixture_retains_doi(self):
        self.assertEqual(self.parse(ESCAPED_DELIMITER_FIXTURE), {'example': '10.1234/example'})

    def test_springer_bibtex_recognizes_escaped_delimiter_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'fixture.bib').write_text(ESCAPED_DELIMITER_FIXTURE)
            (root / 'fixture.aux').write_text(
                '\\relax\n\\citation{Example}\n\\bibstyle{sn-mathphys-ay}\n\\bibdata{fixture}\n')
            shutil.copy2(ROOT / 'manuscript/sn-mathphys-ay.bst', root / 'sn-mathphys-ay.bst')
            result = subprocess.run(['bibtex', 'fixture'], cwd=root, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertNotIn('Warning--', result.stdout)
            self.assertIn(r'\doiurl{10.1234/example}', (root / 'fixture.bbl').read_text())

    def test_fixture_doi_cannot_be_omitted_from_rendered_entry(self):
        metadata = self.parse(ESCAPED_DELIMITER_FIXTURE)
        xid = '{http://www.w3.org/XML/1998/namespace}id'
        entry = etree.Element('bibitem', key='Example', **{xid: 'bib.example'})
        page = html.fromstring('<article><ul><li id="bib.example"><a href="https://doi.org/10.1234/example">https://doi.org/10.1234/example</a></li></ul></article>')
        self.assertEqual(validate_bibliography_dois(page, [entry], metadata, xid), [])
        link = page.xpath('//a')[0]
        link.getparent().remove(link)
        self.assertEqual(validate_bibliography_dois(page, [entry], metadata, xid),
                         ['DOI link inventory differs from refs.bib: example'])

    def test_nearby_backslashes_braces_quotes_and_comments(self):
        for field in (r'file="A \",', r'file={A \\},', r'file={Set \{C\}, nested {text}},',
                      r'file="A {protected \"quote\"}, comma",'):
            with self.subTest(field=field):
                source = ESCAPED_DELIMITER_FIXTURE.replace(r'file={A \},', field)
                source = '% @article{Ignored, doi={10.1234/ignored}}\n' + source
                self.assertEqual(self.parse(source), {'example': '10.1234/example'})

    def test_crossref_inheritance_fails_explicitly(self):
        source = '@inproceedings{Child, title={Child}, crossref={Parent}}\n@proceedings{Parent, doi={10.1234/inherited}}'
        with self.assertRaisesRegex(ValueError, 'crossref'):
            self.parse(source)

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
