"""Canonical natbib labels must constrain visible citation text independently."""
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from lxml import etree, html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate import validate
import canonical

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build'
NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'
AUX = r'''\relax
\bibcite{Spettl2016}{{1}{2016}{{Spettl et~al.}}{{}}}
\bibcite{Bourne2025}{{2}{2025}{{Bourne et~al.}}{{}}}
\bibcite{Spettl2017}{{3}{2017}{{Spettl et~al.}}{{}}}
\bibcite{Spettl2020a}{{4}{2020a}{{Spettl et~al.}}{{}}}
\bibcite{Spettl2020b}{{5}{2020b}{{Spettl et~al.}}{{}}}
'''


class CitationDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.aux = Path(self.temp.name) / 'manuscript.aux'
        self.aux.write_text(AUX)
        self.xml = etree.fromstring(('<document xmlns="' + NS['l'] + '"><bibliography>' +
                                    ''.join(f'<bibitem key="{key}" xml:id="{key}"/>' for key in
                                            ('Spettl2016', 'Bourne2025', 'Spettl2017',
                                             'Spettl2020a', 'Spettl2020b')) +
                                    '</bibliography></document>').encode())

    def check(self, command, keys, display, pre=(), post=()):
        source = [(command, tuple(keys.split(',')), pre, post)]
        page = html.fromstring('<html><body><article><cite class="ltx_cite ltx_citemacro_' +
                               command + '">' + display + '</cite></article></body></html>')
        return canonical.validate_citation_display(source, canonical.read_natbib(self.aux),
                                                   self.xml, page, 'fixture HTML')

    def test_citep_and_citet_match_canonical_author_year_with_grouped_notes(self):
        for command, display in (
                ('citep', '(see Spettl et al., <a href="#Spettl2016">2016</a>; '
                 'Bourne et al., <a href="#Bourne2025">2025</a>, Sec. 2)'),
                ('citet', 'Spettl et al. (see <a href="#Spettl2016">2016</a>, Sec. 2); '
                 'Bourne et al. (see <a href="#Bourne2025">2025</a>, Sec. 2)')):
            with self.subTest(command=command):
                self.assertEqual(self.check(command, 'Spettl2016,Bourne2025', display,
                                            ('see',), ('Sec', '.', '2')), [])

    def test_adjacent_author_groups_and_year_suffixes_use_canonical_labels(self):
        cases = [
            ('citep', 'Spettl2016,Spettl2017',
             '(Spettl et al., <a href="#Spettl2016">2016</a>, <a href="#Spettl2017">2017</a>)'),
            ('citet', 'Spettl2020b,Spettl2020a',
             'Spettl et al. (<a href="#Spettl2020b">2020b</a>, <a href="#Spettl2020a">a</a>)'),
            ('citep', 'Spettl2016,Bourne2025,Spettl2017',
             '(Spettl et al., <a href="#Spettl2016">2016</a>; Bourne et al., '
             '<a href="#Bourne2025">2025</a>; Spettl et al., <a href="#Spettl2017">2017</a>)'),
        ]
        for command, keys, display in cases:
            with self.subTest(command=command, keys=keys):
                self.assertEqual(self.check(command, keys, display), [])

    def test_spettl_author_and_year_mutation_keeps_target_but_fails_display_category(self):
        correct = '(Spettl et al., <a href="#Spettl2016">2016</a>)'
        self.assertEqual(self.check('citep', 'Spettl2016', correct), [])
        changed = '(Wrong Author et al., <a href="#Spettl2016">2999</a>)'
        self.assertNotEqual(changed, correct)
        self.assertEqual(html.fromstring(changed).xpath('.//a/@href'), ['#Spettl2016'])
        errors = self.check('citep', 'Spettl2016', changed)
        self.assertTrue(any('Canonical citation display mismatch (fixture HTML)' in error
                            and 'Spettl2016' in error for error in errors), errors)

    def test_author_year_note_target_and_hidden_label_mutations_are_rejected(self):
        correct = '(see Spettl et al., <a href="#Spettl2016">2016</a>; '
        correct += 'Bourne et al., <a href="#Bourne2025">2025</a>, Sec. 2)'
        for changed in (correct.replace('Spettl et al.', 'Wrong et al.'),
                        correct.replace('>2016<', '>2999<'),
                        correct.replace('Spettl et al.', '<span hidden>Spettl et al.</span>'),
                        correct.replace('see ', ''), correct.replace('Sec. 2', 'Sec. 9'),
                        correct.replace('#Spettl2016', '#Bourne2025')):
            with self.subTest(changed=changed):
                self.assertNotEqual(changed, correct)
                errors = self.check('citep', 'Spettl2016,Bourne2025', changed,
                                    ('see',), ('Sec', '.', '2'))
                self.assertTrue(any('Canonical citation display mismatch' in error for error in errors), errors)

    def test_aux_author_accents_and_literal_year_suffixes_are_read_independently(self):
        self.aux.write_text(r'\bibcite{accent}{{1}{2025b}{{Garc\'ia and G\"odel}}{{}}}')
        self.assertEqual(canonical.read_natbib(self.aux),
                         {'accent': {'author': 'García and Gödel', 'year': '2025b'}})

    def test_duplicate_malformed_or_unknown_natbib_metadata_fails_explicitly(self):
        for source in (AUX + r'\bibcite{Spettl2016}{{9}{2016}{{Wrong}}{{}}}',
                       r'\bibcite{x}{{1}{2024}{{Name}}}',
                       r'\bibcite{x}{{1}{2024}{{Name}}{{}}',
                       r'\bibcite{x}{{1}{\unknownyear}{{Name}}{{}}}',
                       r'\bibcite{x}{{1}{2024}{{\unknownauthor{Name}}}{{}}}'):
            with self.subTest(source=source):
                self.aux.write_text(source)
                with self.assertRaisesRegex(ValueError, 'canonical citation metadata'):
                    canonical.read_natbib(self.aux)

    def test_unsupported_commands_duplicate_keys_and_macro_notes_fail_explicitly(self):
        for command, keys, pre in (('cite', 'Spettl2016', ()),
                                   ('citep', 'Spettl2016,Spettl2016', ()),
                                   ('citep', 'missing', ()),
                                   ('citep', 'Spettl2016', ('\\', 'emph', '{', 'see', '}'))):
            with self.subTest(command=command, keys=keys, pre=pre):
                errors = self.check(command, keys, '(Unvalidated text)', pre)
                self.assertTrue(any('Unsupported canonical citation display' in error for error in errors), errors)


class RealCitationDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.site, self.work = root / 'site', root / 'work'
        shutil.copytree(BUILD / 'site', self.site)
        self.work.mkdir()
        for name in ('article.html', 'article.xml', 'manuscript.aux', 'manuscript.bbl', 'manuscript.fls'):
            source = BUILD / 'site-work' / name
            if not source.is_file() and name == 'manuscript.fls':
                source = ROOT / 'manuscript' / name
            self.assertTrue(source.is_file(), f'Missing canonical artifact: {source}')
            shutil.copy2(source, self.work / name)
        originals = [*(ROOT / 'manuscript').rglob('*.tex'), ROOT / 'manuscript/refs.bib',
                     BUILD / 'site/article.html', *(BUILD / 'site-work').glob('manuscript.*'),
                     BUILD / 'site-work/article.html', BUILD / 'site-work/article.xml']
        self.protected = {path: hashlib.sha256(path.read_bytes()).digest() for path in originals}
        self.addCleanup(self.assert_originals_unchanged)

    def assert_originals_unchanged(self):
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest, str(path))

    def test_complete_real_citation_displays_pass(self):
        self.assertEqual(validate(self.site, self.work, ROOT / 'manuscript'), [])

    def test_wrong_visible_author_and_year_with_correct_target_are_rejected(self):
        xml = etree.parse(str(self.work / 'article.xml'))
        identities = {node.get(XID): node.get('key') for node in xml.xpath('//l:bibitem', namespaces=NS)}
        target_key = None
        for path in (self.work / 'article.html', self.site / 'article.html'):
            before = path.read_bytes()
            document = html.parse(str(path))
            cites = document.xpath('//article//cite[count(a)=1 and contains(@class,"citemacro_citep")]')
            self.assertTrue(cites, 'A real single-reference parenthetical citation must exist')
            citation = cites[0]
            links = citation.xpath('./a')
            self.assertEqual(len(links), 1, 'Mutate a single-reference citation')
            targets = citation.xpath('.//a/@href')
            key = identities[targets[0].removeprefix('#')]
            if target_key is not None:
                self.assertEqual(key, target_key, 'Both HTML stages must mutate the same source citation')
            target_key = key
            self.assertTrue(''.join(links[0].itertext()).strip(), 'Original year must be present')
            citation.text = '(Wrong Author et al., '
            links[0].text = '2999'
            self.assertEqual(citation.xpath('.//a/@href'), targets)
            self.assertEqual(''.join(citation.itertext()), '(Wrong Author et al., 2999)')
            path.write_bytes(html.tostring(document, encoding='utf-8', doctype='<!doctype html>'))
            self.assertNotEqual(path.read_bytes(), before, f'Mutation did not change {path.name}')
        errors = validate(self.site, self.work, ROOT / 'manuscript')
        for stage in ('raw HTML', 'final HTML'):
            self.assertTrue(any(f'Canonical citation display mismatch ({stage})' in error
                                and target_key in error for error in errors), errors)

    def test_grouped_real_citation_changed_author_year_preserves_all_targets(self):
        xml = etree.parse(str(self.work / 'article.xml'))
        identities = {node.get(XID): node.get('key') for node in xml.xpath('//l:bibitem', namespaces=NS)}
        target_key = None
        for path in (self.work / 'article.html', self.site / 'article.html'):
            before = path.read_bytes()
            document = html.parse(str(path))
            candidates = [node for node in document.xpath('//article//cite[count(a)>1]')
                          if ';' in (node.xpath('./a')[-2].tail or '')]
            self.assertTrue(candidates, 'A real citation with multiple author groups must exist')
            citation = candidates[0]
            links = citation.xpath('./a')
            targets = citation.xpath('.//a/@href')
            key = identities[targets[-1].removeprefix('#')]
            if target_key is not None:
                self.assertEqual(key, target_key)
            target_key = key
            links[-2].tail = '; Wrong Author et al., '
            links[-1].text = '2999'
            self.assertEqual(citation.xpath('.//a/@href'), targets)
            self.assertIn('; Wrong Author et al., 2999', ''.join(citation.itertext()))
            path.write_bytes(html.tostring(document, encoding='utf-8', doctype='<!doctype html>'))
            self.assertNotEqual(path.read_bytes(), before, 'Grouped citation mutation must be saved')
        errors = validate(self.site, self.work, ROOT / 'manuscript')
        for stage in ('raw HTML', 'final HTML'):
            self.assertTrue(any(f'Canonical citation display mismatch ({stage})' in error
                                and target_key in error for error in errors), errors)


if __name__ == '__main__':
    unittest.main()
