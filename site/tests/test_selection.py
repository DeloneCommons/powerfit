"""Small authored fixtures keep mutation selection valid after harmless revisions."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

from lxml import etree, html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical import read_aux, validate_labels, validate_reference_text
from coverage import validate_inventory
from inventory import read_inventory
from selection_helpers import (NS, XID, funding_declaration, declaration_fragment,
                               labelled_equation_and_section, one, swap_label_destinations)


class SelectionRevisionTests(unittest.TestCase):
    labels = ('eq:fixture-value', 'sec:fixture-method')

    def fixture(self, *, inserted=False, funding_title='Funding', funding_body='No external funding.'):
        """The TeX and three representations are explicit independent inputs.

        Equation 1 and section 1 deliberately share a number in the base case.
        A preceding unlabelled equation makes the same owners unequal in the
        revision. No manuscript-wide build or converter-derived expectation is
        involved in either fixture.
        """
        temp = tempfile.TemporaryDirectory(prefix='powerfit-selection-')
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        source = r'''\documentclass{article}\begin{document}
\section{Method}\label{sec:fixture-method}
''' + (r'\begin{equation}z=0.\end{equation}' + '\n' if inserted else '') + r'''
\begin{equation}q=x+1.\label{eq:fixture-value}\end{equation}
See Section~\ref{sec:fixture-method} and Equation~\eqref{eq:fixture-value}.
\section*{Statements and Declarations}
\subsection*{''' + funding_title + r'''}
''' + funding_body + r'''
\subsection*{Other declarations}
No further declarations.
\end{document}
'''
        master = directory / 'manuscript.tex'
        master.write_text(source)
        inventory = read_inventory(master)
        number = '2' if inserted else '1'
        aux_path = directory / 'manuscript.aux'
        aux_path.write_text(r'\newlabel{sec:fixture-method}{{1}{1}{}{section.1}{}}' + '\n' +
                            r'\newlabel{eq:fixture-value}{{' + number + r'}{1}{}{equation.' + number + '}{}}\n')
        inserted_xml = ('''<equation xml:id="fixture.inserted"><tags><tag role="refnum">1</tag></tags>
          <Math xml:id="fixture.inserted.math" tex="z=0."/></equation>''' if inserted else '')
        xml = etree.fromstring(('''<document xmlns="http://dlmf.nist.gov/LaTeXML">
          <section xml:id="fixture.method" labels="LABEL:sec:fixture-method">
            <tags><tag role="refnum">1</tag></tags><title><tag>1</tag>Method</title>
            ''' + inserted_xml + '''
            <equation xml:id="fixture.value" labels="LABEL:eq:fixture-value">
              <tags><tag role="refnum">''' + number + '''</tag></tags>
              <Math xml:id="fixture.value.math" tex="q=x+1."/>
            </equation>
            <para xml:id="fixture.references"><p>See Section <ref labelref="LABEL:sec:fixture-method">1</ref> and Equation (<ref labelref="LABEL:eq:fixture-value">''' + number + '''</ref>).</p></para>
          </section>
          <section xml:id="fixture.declarations"><title>Statements and Declarations</title>
            <subsection xml:id="fixture.support"><title>''' + funding_title + '''</title>
              <para xml:id="fixture.funding"><p>''' + funding_body + '''</p></para>
            </subsection>
            <subsection xml:id="fixture.other"><title>Other declarations</title>
              <para xml:id="fixture.other.paragraph"><p>No further declarations.</p></para>
            </subsection>
          </section>
        </document>''').encode())
        inserted_html = ('''<div class="ltx_equation" id="fixture.inserted">
          <span class="ltx_tag ltx_tag_equation">(1)</span>
          <math id="fixture.inserted.math" alttext="z=0."><mi>z</mi></math></div>''' if inserted else '')
        raw = html.fromstring('''<article>
          <section class="ltx_section" id="fixture.method">
            <h2 class="ltx_title ltx_title_section"><span class="ltx_tag">1</span>Method</h2>
            ''' + inserted_html + '''
            <div class="ltx_equation" id="fixture.value">
              <span class="ltx_tag ltx_tag_equation">(''' + number + ''')</span>
              <math id="fixture.value.math" alttext="q=x+1."><mi>q</mi></math>
            </div>
            <div class="ltx_para" id="fixture.references"><p>See Section <a class="ltx_ref" href="#fixture.method">1</a> and Equation (<a class="ltx_ref" href="#fixture.value">''' + number + '''</a>).</p></div>
          </section>
          <section class="ltx_section" id="fixture.declarations"><h2 class="ltx_title ltx_title_section">Statements and Declarations</h2>
            <section class="ltx_subsection" id="fixture.support"><h3 class="ltx_title ltx_title_subsection">''' + funding_title + '''</h3>
              <div class="ltx_para" id="fixture.funding"><p>''' + funding_body + '''</p></div>
            </section>
            <section class="ltx_subsection" id="fixture.other"><h3 class="ltx_title ltx_title_subsection">Other declarations</h3>
              <div class="ltx_para" id="fixture.other.paragraph"><p>No further declarations.</p></div>
            </section>
          </section>
        </article>''')
        page = deepcopy(raw)
        for label, key in zip(self.labels, ('fixture.value', 'fixture.method')):
            owner = one(self, page.xpath('//*[@id=$key]', key=key), label + ' fixture owner')
            owner.addprevious(html.Element('a', {'id': label, 'class': 'source-anchor'}))
        return inventory, read_aux(aux_path), {'XML': xml, 'raw HTML': raw, 'final HTML': page}

    def assert_valid(self, inventory, aux, docs):
        errors, report = validate_inventory(inventory, docs['XML'], docs['raw HTML'], docs['final HTML'])
        self.assertEqual(errors, [])
        self.assertTrue(report['valid'])
        self.assertEqual(validate_labels(inventory['labels'], aux, docs['XML'], docs['final HTML']), [])
        for stage in ('raw HTML', 'final HTML'):
            self.assertEqual(validate_reference_text(aux, docs['XML'], docs[stage]), [], stage)
        return report

    def assert_swap_rejected(self, inventory, aux, docs):
        report = self.assert_valid(inventory, aux, docs)
        self.assertEqual(labelled_equation_and_section(self, inventory), self.labels,
                         'The actual article selector must resolve these explicit fixture identities')
        objects = {obj['id']: obj for obj in inventory['objects']}
        self.assertEqual(objects[inventory['labels'][self.labels[0]]]['kind'], 'equation')
        self.assertEqual(objects[inventory['labels'][self.labels[1]]]['kind'], 'section')
        self.assertEqual(report['label_destinations'], dict(zip(self.labels, ('fixture.value', 'fixture.method'))))
        swap_label_destinations(self, docs, self.labels)
        errors, report = validate_inventory(inventory, docs['XML'], docs['raw HTML'], docs['final HTML'])
        self.assertFalse(report['valid'])
        self.assertTrue(all(record['matched'] for record in report['representations'].values()),
                        'Coordinated corruption preserves every ordered content stream')
        for label in self.labels:
            self.assertTrue(any('Source label ownership mismatch: ' + label in error for error in errors), errors)
        self.assertTrue(all('Source label ownership' in error for error in errors), errors)
        canonical = validate_labels(inventory['labels'], aux, docs['XML'], docs['final HTML'])
        unequal = aux[self.labels[0]]['number'] != aux[self.labels[1]]['number']
        self.assertEqual(len(canonical), 2 if unequal else 0, canonical)
        for label in self.labels:
            self.assertEqual(any('Canonical numbering mismatch: ' + label + ':' in error for error in canonical),
                             unequal, canonical)
        for stage in ('raw HTML', 'final HTML'):
            self.assertEqual(validate_reference_text(aux, docs['XML'], docs[stage]), [], stage)

    def test_deliberate_equal_number_swap_reaches_full_ownership_validator(self):
        inventory, aux, docs = self.fixture()
        self.assertEqual(aux[self.labels[0]]['number'], '1')
        self.assertEqual(aux[self.labels[1]]['number'], '1')
        self.assert_swap_rejected(inventory, aux, docs)

    def test_inserted_unlabelled_equation_renumbers_same_mutation_targets(self):
        original, original_aux, original_docs = self.fixture()
        revised, revised_aux, revised_docs = self.fixture(inserted=True)
        self.assert_valid(original, original_aux, original_docs)
        self.assert_valid(revised, revised_aux, revised_docs)
        self.assertEqual(original_aux[self.labels[0]]['number'], '1')
        self.assertEqual(revised_aux[self.labels[0]]['number'], '2')
        self.assertEqual(revised_aux[self.labels[1]]['number'], '1')
        extra = one(self, [math for math in revised['math'] if math['numbered'] and not math['labels']],
                    'inserted unlabelled numbered equation')
        self.assertEqual(extra['tex'], 'z=0.')
        self.assertEqual(extra['number'], 1)
        self.assert_swap_rejected(revised, revised_aux, revised_docs)

    def test_renamed_funding_heading_preserves_same_declaration_mutations(self):
        self.check_declaration_mutations('No external funding.')

    def test_rewritten_declaration_body_and_heading_preserve_same_mutation_target(self):
        for body in ('No external financial support.', 'None.',
                     'The work was completed using internal institutional resources and received no external financial support.'):
            with self.subTest(body=body):
                self.check_declaration_mutations(body)

    def check_declaration_mutations(self, body):
        inventory, aux, docs = self.fixture(funding_title='Funding information', funding_body=body)
        self.assert_valid(inventory, aux, docs)
        self.assertEqual(docs['XML'].xpath('//l:subsection/l:title/text()', namespaces=NS),
                         ['Funding information', 'Other declarations'])
        source = funding_declaration(self, inventory, docs)
        self.assertEqual(source.get(XID), 'fixture.funding')
        for mutation in ('omit', 'hide'):
            with self.subTest(mutation=mutation):
                changed = deepcopy(docs)
                # Re-run the real tests' selector against each untouched copy.
                target = funding_declaration(self, inventory, changed)
                fragment = declaration_fragment(self, target)
                for stage, doc in changed.items():
                    node = one(self, doc.xpath('//*[@xml:id=$key]' if stage == 'XML' else '//*[@id=$key]',
                                               key=target.get(XID)), stage + ' declaration')
                    before = etree.tostring(doc)
                    content = ''.join(node.itertext())
                    if mutation == 'omit':
                        paragraph = one(self, node.xpath('./l:p' if stage == 'XML' else './p', namespaces=NS),
                                        stage + ' declaration text')
                        self.assertEqual(paragraph.text, body)
                        self.assertEqual(paragraph.text.count(fragment), 1)
                        paragraph.text = paragraph.text.replace(fragment, '', 1)
                    else:
                        node.set('style', 'display:none')
                        self.assertEqual(''.join(node.itertext()), content)
                    self.assertNotEqual(etree.tostring(doc), before, stage)
                errors, report = validate_inventory(inventory, changed['XML'], changed['raw HTML'], changed['final HTML'])
                self.assertFalse(report['valid'])
                for stage in changed:
                    self.assertTrue(any('Source content' in error and stage in error for error in errors), errors)


if __name__ == '__main__':
    unittest.main()
