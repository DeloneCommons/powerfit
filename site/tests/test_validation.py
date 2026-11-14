"""Mutate a real built article: validation must reject silent scientific loss."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from lxml import html
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate import validate
ROOT = Path(__file__).resolve().parents[2]

class ContentIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / 'build/site/article.html').is_file():
            raise RuntimeError('Build the actual website before running its integration tests')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / 'site'
        shutil.copytree(ROOT / 'build/site', self.site)
        self.work = Path(self.temp.name) / 'work'
        self.work.mkdir()
        for name in ('article.html', 'article.xml', 'manuscript.aux', 'manuscript.bbl'):
            shutil.copy2(ROOT / 'build/site-work' / name, self.work / name)

    def check(self):
        return validate(self.site, self.work, ROOT / 'manuscript')

    def mutate(self, xpath, operation=None):
        path = self.site / 'article.html'
        doc = html.parse(str(path))
        node = doc.xpath(xpath)[0]
        if operation:
            operation(node)
        else:
            node.getparent().remove(node)
        path.write_bytes(html.tostring(doc, encoding='utf-8', doctype='<!doctype html>'))

    def test_complete_generated_site_passes(self):
        self.assertEqual(self.check(), [])

    def test_loss_of_scientific_content_is_rejected(self):
        mutations = {
            'appendix': '//*[@id="A5"]',
            'proof': '//*[contains(concat(" ",@class," ")," ltx_proof ")]',
            'figure': '//figure[contains(@class,"ltx_figure")]',
            'table': '//figure[contains(@class,"ltx_table")]',
            'bibliography': '//li[@class="ltx_bibitem"]',
            'equation': '//table[@id="S2.E2"]',
            'paragraph': '//*[@id="S1.p1"]',
            'math': '//math[@id="S1.p2.m1"]',
        }
        original = (self.site / 'article.html').read_bytes()
        for label, xpath in mutations.items():
            with self.subTest(label=label):
                (self.site / 'article.html').write_bytes(original)
                self.mutate(xpath)
                self.assertTrue(self.check(), f'Loss of {label} was accepted')

    def test_converter_omission_is_rejected_against_latex_prose(self):
        self.mutate('//*[@id="S1.p1"]')
        path = self.work / 'article.html'
        doc = html.parse(str(path))
        node = doc.xpath('//*[@id="S1.p1"]')[0]
        node.getparent().remove(node)
        path.write_bytes(html.tostring(doc))
        self.assertTrue(any('Missing source prose' in e for e in self.check()))

    def test_wrong_equation_number_is_rejected(self):
        self.mutate('//*[contains(@class,"ltx_tag_equation")]', lambda n: setattr(n, 'text', '(999)'))
        self.assertTrue(self.check())

    def test_wrong_table_cell_is_rejected(self):
        self.mutate('//figure[contains(@class,"ltx_table")]//td[normalize-space()="0.00790"]', lambda n: setattr(n, 'text', '9.999'))
        self.assertTrue(self.check())

    def test_broken_reference_is_rejected(self):
        self.mutate('//a[starts-with(@href,"#S")]', lambda n: n.set('href', '#missing'))
        self.assertTrue(self.check())

    def test_citation_to_wrong_existing_entry_is_rejected(self):
        self.mutate('//article//a[starts-with(@href,"#bib.")]',
                    lambda n: n.set('href', '#bib.bib1' if n.get('href') != '#bib.bib1' else '#bib.bib2'))
        self.assertTrue(self.check())

    def test_corrupt_doi_in_converter_and_site_is_rejected(self):
        # Simulate converter defects too: parity with its HTML is insufficient.
        for value in ('https://doi.org/%****%20manuscript.bbl%20Line%20125%20****10.1002/ijch.198000003',
                      'https://doi.org/10.1002/a-valid-but-wrong-doi'):
            with self.subTest(value=value):
                for directory in (self.work, self.site):
                    path = directory / 'article.html'
                    doc = html.parse(str(path))
                    link = doc.xpath('//li[contains(@class,"ltx_bibitem")]//a[starts-with(@href,"https://doi.org/")]')[0]
                    link.set('href', value)
                    link.text = value
                    path.write_bytes(html.tostring(doc, encoding='utf-8'))
                self.assertTrue(any('DOI' in e for e in self.check()), 'Corrupt DOI accepted')

    def test_missing_doi_in_converter_and_site_is_rejected(self):
        for directory in (self.work, self.site):
            path = directory / 'article.html'
            doc = html.parse(str(path))
            link = doc.xpath('//li[contains(@class,"ltx_bibitem")]//a[starts-with(@href,"https://doi.org/")]')[0]
            link.getparent().remove(link)
            path.write_bytes(html.tostring(doc, encoding='utf-8'))
        self.assertTrue(any('DOI' in e for e in self.check()))

    def test_malformed_archive_doi_is_rejected(self):
        path = self.site / 'index.html'
        doc = html.parse(str(path))
        doc.xpath('//a[starts-with(@href,"https://doi.org/")]')[0].set('href', 'https://doi.org/10.5281/zenodo. bad')
        path.write_bytes(html.tostring(doc, encoding='utf-8'))
        self.assertTrue(any('DOI' in e for e in self.check()))

    def test_root_relative_asset_is_rejected(self):
        self.mutate('//link[@rel="stylesheet"]', lambda n: n.set('href', '/site.css'))
        self.assertTrue(self.check())

    def test_swapped_figure_is_rejected(self):
        self.mutate('//img', lambda n: n.set('src', 'figures/figure_03_cycle.svg'))
        self.assertTrue(self.check())

    def test_unapproved_artifact_is_rejected(self):
        (self.site / 'private-record.txt').write_text('must not ship')
        self.assertTrue(self.check())

    def test_changed_pdf_is_rejected(self):
        with (self.site / 'manuscript.pdf').open('ab') as f:
            f.write(b'changed')
        self.assertTrue(self.check())

if __name__ == '__main__':
    unittest.main()
