"""Source expectations reject common omissions in all converter representations."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from lxml import etree, html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from coverage import validate_inventory
except ImportError:
    validate_inventory = None
from mathsyntax import normalize_math


class IndependentCoverageTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {'schema': 1, 'sources': [], 'labels': {}, 'objects': [
            {'id': 'o1', 'kind': 'document', 'owner': None, 'content': [{'kind': 'object', 'id': 'o2'}]},
            {'id': 'o2', 'kind': 'section', 'owner': 'o1', 'title': [{'kind': 'text', 'text': 'Claim'}],
             'content': [{'kind': 'object', 'id': 'o3'}, {'kind': 'object', 'id': 'o4'}]},
            {'id': 'o3', 'kind': 'prose', 'owner': 'o2', 'content': [
                {'kind': 'text', 'text': 'Let '}, {'kind': 'math', 'id': 'm1'}, {'kind': 'text', 'text': '.'}]},
            {'id': 'o4', 'kind': 'proof', 'owner': 'o2', 'content': [
                {'kind': 'text', 'text': 'Since '}, {'kind': 'math', 'id': 'm2'}, {'kind': 'text', 'text': ', done.'}]},
        ], 'math': [
            {'id': 'm1', 'tex': 'x_i', 'normalized': normalize_math('x_i'), 'cells': [normalize_math('x_i')], 'pure_script': False, 'numbered': False},
            {'id': 'm2', 'tex': 'x_i>0', 'normalized': normalize_math('x_i>0'), 'cells': [normalize_math('x_i>0')], 'pure_script': False, 'numbered': False},
        ]}
        self.xml = etree.fromstring(r'''<document xmlns="http://dlmf.nist.gov/LaTeXML"><section xml:id="S7">
          <title><tag>7</tag>Claim</title><para><p>Let <Math tex="x_{i}" xml:id="m1"/>.</p></para>
          <proof><title>Proof.</title><para><p>Since <Math tex="x_{i}&gt;0" xml:id="m2"/>, done.∎</p></para></proof>
        </section></document>''')
        self.raw = html.fromstring(r'''<article><section class="ltx_section" id="S7">
          <h2 class="ltx_title ltx_title_section"><span class="ltx_tag">7</span>Claim</h2>
          <p>Let <math alttext="x_{i}" id="m1"/>.</p>
          <div class="ltx_proof"><h6 class="ltx_title_proof">Proof.</h6><p>Since <math alttext="x_{i}&gt;0" id="m2"/>, done.∎</p></div>
        </section></article>''')

    def check(self, xml=None, raw=None, final=None):
        self.assertIsNotNone(validate_inventory, 'independent matcher is not implemented')
        return validate_inventory(self.inventory, self.xml if xml is None else xml,
                                  self.raw if raw is None else raw,
                                  deepcopy(self.raw) if final is None else final)[0]

    def test_hand_specified_source_matches_xml_and_both_html_stages(self):
        self.assertEqual(self.check(), [])

    def test_consistently_omitted_inline_math_is_rejected_by_source(self):
        xml, raw = deepcopy(self.xml), deepcopy(self.raw)
        nodes = xml.xpath('//*[local-name()="Math"]')
        self.assertEqual(len(nodes), 2)
        nodes[0].getparent().remove(nodes[0])
        nodes = raw.xpath('//math')
        self.assertEqual(len(nodes), 2)
        nodes[0].getparent().remove(nodes[0])
        errors = self.check(xml, raw, deepcopy(raw))
        self.assertTrue(any('Source mathematics' in e for e in errors), errors)

    def test_consistently_missing_short_proof_fails_in_its_owner(self):
        xml, raw = deepcopy(self.xml), deepcopy(self.raw)
        proof = xml.xpath('//*[local-name()="proof"]')[0]
        for node in list(proof)[1:]:
            proof.remove(node)
        proof = raw.xpath('//*[@class="ltx_proof"]')[0]
        for node in list(proof)[1:]:
            proof.remove(node)
        errors = self.check(xml, raw, deepcopy(raw))
        self.assertTrue(any('Source content' in e and 'proof' in e for e in errors), errors)

    def test_wrong_annotation_in_all_outputs_fails_independent_source(self):
        for replacement in ('x^i', 'i_x', 'x_i+1'):
            xml, raw = deepcopy(self.xml), deepcopy(self.raw)
            xml.xpath('//*[local-name()="Math"]')[0].set('tex', replacement)
            raw.xpath('//math')[0].set('alttext', replacement)
            errors = self.check(xml, raw, deepcopy(raw))
            self.assertTrue(any('Source mathematics' in e for e in errors), errors)

    def test_repeated_text_elsewhere_cannot_replace_a_proof(self):
        xml = deepcopy(self.xml)
        proof = xml.xpath('//*[local-name()="proof"]')[0]
        paragraph = proof[-1]
        proof.remove(paragraph)
        xml[0].insert(1, paragraph)
        errors = self.check(xml)
        self.assertTrue(any('Source content' in e for e in errors), errors)

    def test_hidden_nested_proof_heading_cannot_satisfy_its_identity(self):
        xml, raw = deepcopy(self.xml), deepcopy(self.raw)
        title = xml.xpath('//*[local-name()="proof"]/*[local-name()="title"]')[0]
        child = etree.SubElement(title, '{http://dlmf.nist.gov/LaTeXML}text', hidden='hidden')
        child.text, title.text = title.text, None
        title = raw.xpath('//*[@class="ltx_title_proof"]')[0]
        child = etree.SubElement(title, 'span', hidden='hidden')
        child.text, title.text = title.text, None
        self.assertEqual(''.join(title.itertext()), 'Proof.')
        errors = self.check(xml, raw, deepcopy(raw))
        for stage in ('XML', 'raw HTML', 'final HTML'):
            self.assertTrue(any('Source content' in error and stage in error for error in errors), errors)

    def test_equation_layout_tables_do_not_become_scientific_tables(self):
        # An actual source display owns its generated layout table. Inventing
        # an equation wrapper around inline math must no longer be transparent.
        inventory = {'sources': [], 'labels': {}, 'objects': [
            {'id': 'document', 'kind': 'document', 'owner': None,
             'content': [{'kind': 'object', 'id': 'display'}]},
            {'id': 'display', 'kind': 'display', 'owner': 'document',
             'content': [{'kind': 'math', 'id': 'formula'}]},
        ], 'math': [{'id': 'formula', 'owner': 'display', 'mode': 'display',
                    'tex': 'x_i', 'cells': [normalize_math('x_i')], 'numbered': False}]}
        xml = etree.fromstring('''<document xmlns="http://dlmf.nist.gov/LaTeXML">
          <equation xml:id="fixture.display"><Math tex="x_i" xml:id="fixture.math"/></equation>
        </document>''')
        raw = html.fromstring('''<article><table class="ltx_equation" id="fixture.display">
          <tbody><tr class="ltx_eqn_row"><td class="ltx_eqn_cell" colspan="2">
            <math alttext="x_i" id="fixture.math"/>
          </td></tr></tbody></table></article>''')
        self.assertEqual(validate_inventory(inventory, xml, raw, deepcopy(raw))[0], [])

    def test_equation_wrapper_cannot_invent_an_owner_for_inline_math(self):
        raw = deepcopy(self.raw)
        math = raw.xpath('//math')[0]
        wrapper = html.fromstring('<table class="ltx_equation"><tr class="ltx_eqn_row"><td></td></tr></table>')
        math.getparent().replace(math, wrapper)
        wrapper.xpath('.//td')[0].append(math)
        wrapper.tail, math.tail = math.tail, None
        errors = self.check(raw=raw, final=deepcopy(raw))
        for stage in ('raw HTML', 'final HTML'):
            self.assertTrue(any('Equation ownership' in error and stage in error for error in errors), errors)

    def test_literal_path_is_text_not_a_generated_hyperlink(self):
        self.inventory['objects'][2]['content'][0]['text'] = 'Let folder/name '
        paragraph = self.xml.xpath('//*[local-name()="p"]')[0]
        path = etree.fromstring('<ref xmlns="http://dlmf.nist.gov/LaTeXML" class="ltx_nolink ltx_path" href="folder/name">folder/name</ref>')
        path.tail = ' '
        paragraph.insert(0, path)
        self.raw.xpath('//p')[0].text = 'Let folder/name '
        self.assertEqual(self.check(), [])

    def test_citation_postnote_is_independently_required(self):
        self.inventory['objects'][2]['content'].append({'kind': 'cite', 'command': 'citep', 'targets': ['One'], 'postnote': 'Sec.~2'})
        cite = etree.fromstring('<cite xmlns="http://dlmf.nist.gov/LaTeXML" class="ltx_citemacro_citep">(<bibref bibrefs="One"/>, Sec. 2)</cite>')
        self.xml.xpath('//*[local-name()="p"]')[0].append(cite)
        bib = etree.fromstring('<bibliography xmlns="http://dlmf.nist.gov/LaTeXML"><bibitem key="One" xml:id="bib.one"/></bibliography>')
        self.xml.append(bib)
        self.raw.xpath('//p')[0].append(html.fromstring('<cite class="ltx_citemacro_citep">(One, <a href="#bib.one">2026</a>, Sec. 2)</cite>'))
        self.assertEqual(self.check(), [])
        cite[0].tail = ')'
        self.raw.xpath('//cite/a')[0].tail = ')'
        self.assertTrue(any('Source content' in e for e in self.check()))


if __name__ == '__main__':
    unittest.main()
