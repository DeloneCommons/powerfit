"""Independent miniature canonical evidence; no manuscript acceptance totals."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from lxml import etree, html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical import (read_aux, validate_labels, validate_recorder,
                       canonical_bibliography, validate_canonical_bibliography)

NS = 'http://dlmf.nist.gov/LaTeXML'
BBL = r'''\begin{thebibliography}{2}
\csname PreBibitemsHook\endcsname
\bibitem[\protect\citeauthoryear{Example}{2024}]{first}
\begin{barticle}
\bauthor{\bsnm{Example}, \binits{A.}}:
\batitle{A {small} title}.
\bjtitle{Journal} \bvolume{7}, \bfpage{10}--\blpage{12} (\byear{2024})
\doiurl{10.1234/test}
\end{barticle}\endbibitem
\bibitem{second}
\begin{bbook}\bauthor{\bsnm{Other}, \binits{B.}}:
\bbtitle{Another title}. \bpublisher{Publisher} (\byear{2025})
\end{bbook}\endbibitem
\end{thebibliography}
'''
TEXTS = ['Example, A.: A small title. Journal 7, 10–12 (2024) https://doi.org/10.1234/test',
         'Other, B.: Another title. Publisher (2025)']


def documents():
    xml = etree.fromstring(('<document xmlns="' + NS + '"><bibliography><biblist>' + ''.join(
        f'<bibitem key="{key}" xml:id="bib{index}"><tags><tag role="refnum">unused</tag></tags>'
        f'<bibblock>{text}</bibblock></bibitem>'
        for index, (key, text) in enumerate(zip(('first', 'second'), TEXTS), 1)) +
        '</biblist></bibliography></document>').encode())
    page = html.fromstring('<html><body><ul>' + ''.join(
        f'<li id="bib{index}" class="ltx_bibitem"><span class="ltx_tag">unused</span>'
        f'<span class="ltx_bibblock">{text}</span></li>' for index, text in enumerate(TEXTS, 1)) +
        '</ul></body></html>')
    return xml, page


class CanonicalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_balanced_aux_labels_keep_numbers_and_destinations(self):
        path = self.write('paper.aux', r'''\relax
\newlabel{eq:first}{{A.1}{2}{A {nested} title}{equation.A.1}{}}
\newlabel{sec:next}{{B}{3}}
% \newlabel{ignored}{{9}{9}}
''')
        self.assertEqual(read_aux(path), {
            'eq:first': {'number': 'A.1', 'page': '2', 'title': 'A {nested} title', 'destination': 'equation.A.1'},
            'sec:next': {'number': 'B', 'page': '3', 'title': '', 'destination': ''}})

    def test_duplicate_and_malformed_aux_labels_fail(self):
        for value in (r'\newlabel{x}{{1}{2}}\newlabel{x}{{1}{2}}',
                      r'\newlabel{x}{{1}{2}', r'\newlabel{x}{1}'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'canonical labels'):
                read_aux(self.write('paper.aux', value))

    def test_source_aux_xml_membership_and_numbering_are_independent(self):
        aux = {'sec:a': {'number': '2', 'page': '1', 'title': '', 'destination': 'section.2'}}
        xml = etree.fromstring(('<document xmlns="' + NS + '"><section labels="LABEL:sec:a" xml:id="s">'
                               '<tags><tag role="refnum">2</tag></tags></section></document>').encode())
        self.assertEqual(validate_labels(['sec:a'], aux, xml), [])
        for labels, canonical, converted in ((['sec:missing'], aux, xml),
                                              (['sec:a'], {}, xml),
                                              (['sec:a'], aux, etree.fromstring(('<document xmlns="' + NS + '"/>').encode()))):
            with self.subTest(labels=labels):
                self.assertTrue(validate_labels(labels, canonical, converted))
        xml[0][0][0].text = '9'
        self.assertTrue(any('numbering' in e for e in validate_labels(['sec:a'], aux, xml)))

    def test_recorder_matches_active_roles_with_relocated_working_directory(self):
        entries = []
        for name, role in (('manuscript.tex', 'authored'), ('nested/active.tex', 'authored'),
                           ('tex-support/glyphtounicode-cmr.tex', 'publisher-unicode')):
            path = self.write(name, 'source:' + name)
            entries.append({'path': name, 'role': role, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        fls = self.write('paper.fls', 'PWD /old/copy/manuscript\nINPUT manuscript.tex\n'
                         'INPUT /old/copy/manuscript/nested/active.tex\nINPUT ./nested/active.tex\n'
                         'INPUT tex-support/glyphtounicode-cmr.tex\nINPUT manuscript.aux\nINPUT manuscript.bbl\n'
                         'INPUT /usr/share/texlive/texmf-dist/system.tex\nOUTPUT manuscript.log\n')
        self.assertEqual(validate_recorder(fls, self.root, entries), [])
        fls.write_text(fls.read_text() + 'INPUT untracked/science.tex\n')
        self.assertTrue(any('unexpected local input' in e for e in validate_recorder(fls, self.root, entries)))
        fls.write_text(fls.read_text().replace('INPUT manuscript.tex\n', ''))
        self.assertTrue(any('not consumed' in e for e in validate_recorder(fls, self.root, entries)))
        (self.root / 'nested/active.tex').write_text('changed source')
        self.assertTrue(any('hash' in e for e in validate_recorder(fls, self.root, entries)))

    def test_canonical_bibliography_has_literal_hand_checked_text(self):
        self.assertEqual(canonical_bibliography(self.write('paper.bbl', BBL)),
                         [{'key': 'first', 'text': TEXTS[0]}, {'key': 'second', 'text': TEXTS[1]}])

    def test_full_bibliography_text_matches_both_products(self):
        xml, page = documents()
        path = self.write('paper.bbl', BBL)
        self.assertEqual(validate_canonical_bibliography(path, xml, page), [])
        for removed in ('Example, A.: ', 'A small title. '):
            changed_xml, changed_page = deepcopy(xml), deepcopy(page)
            for node in changed_xml.xpath('//*[local-name()="bibblock"]') + changed_page.xpath('//*[@class="ltx_bibblock"]'):
                node.text = node.text.replace(removed, '')
            errors = validate_canonical_bibliography(path, changed_xml, changed_page)
            self.assertTrue(any('XML bibliography content' in e for e in errors), errors)
            self.assertTrue(any('HTML bibliography content' in e for e in errors), errors)

    def test_bibliography_order_duplicate_and_missing_entries_fail(self):
        path = self.write('paper.bbl', BBL)
        for mode in ('order', 'duplicate', 'missing'):
            xml, page = documents()
            biblist = xml.xpath('//*[local-name()="biblist"]')[0]
            if mode == 'order':
                biblist.insert(0, biblist[-1])
            elif mode == 'duplicate':
                biblist.append(deepcopy(biblist[0]))
            else:
                biblist.remove(biblist[0])
            self.assertTrue(any('XML bibliography identities' in e for e in validate_canonical_bibliography(path, xml, page)))
        duplicate = BBL.replace(r'\bibitem{second}', r'\bibitem{first}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            canonical_bibliography(self.write('paper.bbl', duplicate))

    def test_unknown_item_commands_and_unclosed_entries_fail(self):
        for changed in (BBL.replace('A {small}', r'\scientificmacro{A small}'),
                        BBL.replace(r'\endbibitem', '', 1)):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'canonical bibliography'):
                canonical_bibliography(self.write('paper.bbl', changed))

    def test_hidden_bibliography_text_cannot_satisfy_visible_content(self):
        xml, page = documents()
        blocks = page.xpath('//*[@class="ltx_bibblock"]')
        text = blocks[0].text
        blocks[0].text = None
        hidden = html.Element('span', hidden='hidden')
        hidden.text = 'Example, A.: '
        hidden.tail = text.replace('Example, A.: ', '')
        blocks[0].insert(0, hidden)
        self.assertTrue(any('HTML bibliography content' in e for e in
                            validate_canonical_bibliography(self.write('paper.bbl', BBL), xml, page)))

    def test_unclassified_generated_inputs_are_not_blanket_excluded(self):
        fls = self.write('paper.fls', 'PWD /old/copy/manuscript\nINPUT unexplained.aux\n')
        self.assertTrue(any('unexpected local input' in e for e in validate_recorder(fls, self.root, [])))

    def test_bibliographic_accents_and_escaped_symbols(self):
        changed = BBL.replace('A {small} title', r'G\"odel and Garc\'ia \& 10\%')
        self.assertIn('Gödel and García & 10%', canonical_bibliography(self.write('paper.bbl', changed))[0]['text'])


if __name__ == '__main__':
    unittest.main()
