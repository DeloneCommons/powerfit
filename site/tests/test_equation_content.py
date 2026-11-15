"""R1: generated equation scaffolding cannot conceal unauthored content."""
import json
import unittest
from lxml import etree, html

import test_validation as artifacts
from coverage import validate_inventory
from inventory import read_inventory
from validate import validate

NS, XID, css = artifacts.NS, artifacts.XID, artifacts.css


class EquationContentTests(artifacts.ContentIntegrityFixture):
    def target(self, docs):
        candidates = docs['XML'].xpath('//l:equation[l:tags/l:tag[@role="refnum"] and l:Math]', namespaces=NS)
        owner = self.first(candidates, 'numbered equation with direct mathematics')
        return {stage: self.identified(doc, owner.get(XID), stage) for stage, doc in docs.items()}

    def originals(self, doc, stage):
        maths = doc.xpath('//l:Math' if stage == 'XML' else '//article//math', namespaces=NS)
        tags = doc.xpath('//l:tags' if stage == 'XML' else '//*[' + css('ltx_tag_equation') + ' or ' + css('ltx_tag_equationgroup') + ']', namespaces=NS)
        return ([etree.tostring(n, with_tail=False) for n in maths],
                [etree.tostring(n, with_tail=False) for n in tags])

    def source_rejects(self, stages):
        docs = self.documents()
        errors, report = validate_inventory(read_inventory(artifacts.ROOT / 'manuscript/manuscript.tex'),
                                           docs['XML'], docs['raw HTML'], docs['final HTML'])
        self.assertFalse(report['valid'])
        for stage in stages:
            self.assertTrue(any('Unexpected equation content' in e and stage in e for e in errors), errors)

    def padding(self, owner):
        return self.one(owner.xpath('.//td[' + css('ltx_eqn_center_padleft') + ']'), 'original left padding cell')

    def add_xml_sibling(self, owner):
        math = self.one(owner.xpath('./l:Math', namespaces=NS), 'direct original Math')
        extra = etree.Element('{' + NS['l'] + '}text')
        extra.text = '0 = 1'
        math.addprevious(extra)
        self.assertEqual(extra.getnext(), math)

    def test_original_three_product_zero_equals_one_is_rejected(self):
        docs = self.documents()
        targets = self.target(docs)
        for stage, doc in docs.items():
            before = self.originals(doc, stage)
            owner = targets[stage]
            node = owner if stage == 'XML' else self.padding(owner)
            self.change(doc, node, stage, self.add_xml_sibling if stage == 'XML' else lambda n: setattr(n, 'text', '0 = 1'))
            self.assertIn('0 = 1', ''.join(node.itertext()))
            self.assertEqual(self.originals(doc, stage), before)
        self.assert_originals_unchanged()
        self.reject('Unexpected equation content', all_stages=True)
        self.assertFalse(json.loads((self.work / 'source-validation.json').read_text())['valid'])

    def test_xml_direct_math_sibling_is_independently_rejected(self):
        docs = self.documents()
        before = self.originals(docs['XML'], 'XML')
        self.change(docs['XML'], self.target(docs)['XML'], 'XML', self.add_xml_sibling)
        self.assertEqual(self.originals(docs['XML'], 'XML'), before)
        self.source_rejects(('XML',))

    def test_xml_wrapper_text_elements_and_tails_are_not_discarded(self):
        queries = ('//l:equationgroup', '//l:MathFork', '//l:MathBranch', '//l:MathBranch/l:td', '//l:equation/l:tags')
        for query in queries:
            for location in ('text', 'child', 'tail'):
                with self.subTest(query=query, location=location):
                    self.restore()
                    docs = self.documents()
                    node = self.first(docs['XML'].xpath(query, namespaces=NS), query)
                    node = self.one(docs['XML'].xpath(docs['XML'].getpath(node)), 'selected XML wrapper')
                    before = self.originals(docs['XML'], 'XML')[0]
                    def mutate(n):
                        if location == 'text':
                            n.text = '0 = 1'
                        elif location == 'child':
                            etree.SubElement(n, '{' + NS['l'] + '}text').text = '0 = 1'
                        else:
                            child = self.first(list(n), 'child with tail')
                            child.tail = '0 = 1'
                    self.change(docs['XML'], node, 'XML', mutate)
                    self.assertEqual(self.originals(docs['XML'], 'XML')[0], before)
                    self.source_rejects(('XML',))

    def test_html_padding_rejects_text_math_and_mixed_markup_in_each_stage(self):
        for stage in ('raw HTML', 'final HTML'):
            for content in ('0 = 1', '<math><mn>0</mn><mo>=</mo><mn>1</mn></math>',
                            '<span></span>0 = 1', '<span>0 = 1</span>',
                            '<math hidden><annotation>0 = 1</annotation></math>'):
                with self.subTest(stage=stage, content=content):
                    self.restore()
                    docs = self.documents()
                    pad = self.padding(self.target(docs)[stage])
                    before_math, before_tags = self.originals(docs[stage], stage)
                    def mutate(n):
                        fragment = html.fragment_fromstring(content, create_parent='div')
                        n.text = fragment.text
                        n.extend(fragment)
                    self.change(docs[stage], pad, stage, mutate)
                    after_math, after_tags = self.originals(docs[stage], stage)
                    self.assertTrue(all(m in after_math for m in before_math))
                    self.assertEqual(after_tags, before_tags)
                    self.source_rejects((stage,))

    def test_html_number_cell_remainder_preserves_correct_number(self):
        docs = self.documents()
        for stage in ('raw HTML', 'final HTML'):
            owner = self.target(docs)[stage]
            cell = self.one(owner.xpath('.//td[' + css('ltx_eqn_eqno') + ']'), 'number cell')
            tag = self.one(cell.xpath('./span[' + css('ltx_tag_equation') + ']'), 'correct numbering tag')
            before = self.originals(docs[stage], stage)
            self.change(docs[stage], cell, stage, lambda _: setattr(tag, 'tail', '0 = 1'))
            self.assertEqual(self.originals(docs[stage], stage), before)
        self.source_rejects(('raw HTML', 'final HTML'))
        self.reject('Unexpected equation content')

    def test_html_wrapper_text_and_tails_are_not_discarded(self):
        for stage in ('raw HTML', 'final HTML'):
            for query in ('.', './tbody', './tbody/tr'):
                for location in ('text', 'tail'):
                    with self.subTest(stage=stage, query=query, location=location):
                        self.restore()
                        docs = self.documents()
                        owner = self.target(docs)[stage]
                        wrapper = self.one(owner.xpath(query), 'equation layout wrapper')
                        before = self.originals(docs[stage], stage)
                        def mutate(n):
                            if location == 'text':
                                n.text = '0 = 1'
                            else:
                                self.first(list(n), 'layout child').tail = '0 = 1'
                        self.change(docs[stage], wrapper, stage, mutate)
                        self.assertEqual(self.originals(docs[stage], stage), before)
                        self.source_rejects((stage,))

    def test_allowed_layout_cannot_hide_unconsumed_mathematical_cells(self):
        docs = self.documents()
        branch = self.first(docs['XML'].xpath('//l:MathBranch[l:td]', namespaces=NS), 'direct-cell math branch')
        branch = self.one(docs['XML'].xpath(docs['XML'].getpath(branch)), 'selected MathBranch')
        before_math = self.originals(docs['XML'], 'XML')[0]
        def xml_mutation(node):
            row = etree.Element('{' + NS['l'] + '}tr')
            row.extend(list(node))
            node.append(row)
            cell = etree.SubElement(node, '{' + NS['l'] + '}td')
            etree.SubElement(cell, '{' + NS['l'] + '}Math', tex='0=1', attrib={XID: 'r1.extra'})
        self.change(docs['XML'], branch, 'XML', xml_mutation)
        after_math = self.originals(docs['XML'], 'XML')[0]
        self.assertEqual([m for m in after_math if m in before_math], before_math)
        targets = self.target(docs)
        for stage in ('raw HTML', 'final HTML'):
            before_math, before_tags = self.originals(docs[stage], stage)
            row = html.fromstring('<tr><td><math id="r1.extra" alttext="0=1"><semantics><mrow><mn>0</mn><mo>=</mo><mn>1</mn></mrow><annotation encoding="application/x-tex">0=1</annotation></semantics></math></td></tr>')
            self.change(docs[stage], targets[stage], stage, lambda n: n.append(row))
            after_math, after_tags = self.originals(docs[stage], stage)
            self.assertEqual([m for m in after_math if m in before_math], before_math)
            self.assertEqual(after_tags, before_tags)
        self.source_rejects(docs)
        self.reject('Unexpected equation content', all_stages=True)

    def test_skipped_math_inside_consumed_cell_cannot_supply_extra_content(self):
        for attribute, value in (('aria-hidden', 'true'), ('class', 'ltx_tag'), ('class', 'source-anchor')):
            with self.subTest(attribute=attribute, value=value):
                self.restore()
                docs = self.documents()
                source = self.first(docs['XML'].xpath('//l:MathBranch/l:td/l:Math', namespaces=NS), 'delivered alignment Math')
                for stage, doc in docs.items():
                    original = self.identified(doc, source.get(XID), stage)
                    before_math, before_tags = self.originals(doc, stage)
                    if stage == 'XML':
                        extra = etree.Element('{' + NS['l'] + '}Math', tex='0=1', attrib={XID: 'r1.extra'})
                        extra.text = '0 = 1'
                        # XML's tag exclusion is element-based, so use the
                        # independently reproduced skipped-leaf attribute here.
                        extra.set('aria-hidden', 'true')
                    else:
                        extra = html.fromstring('<math id="r1.extra" alttext="0=1"><semantics><mrow><mn>0</mn><mo>=</mo><mn>1</mn></mrow><annotation encoding="application/x-tex">0=1</annotation></semantics></math>')
                        extra.set(attribute, value)
                    self.change(doc, original.getparent(), stage, lambda n: n.append(extra))
                    after_math, after_tags = self.originals(doc, stage)
                    self.assertEqual([m for m in after_math if m in before_math], before_math)
                    self.assertEqual(after_tags, before_tags)
                self.source_rejects(docs)
                self.reject('Unexpected equation content', all_stages=True)

    def test_pristine_and_empty_layout_markup_remain_accepted(self):
        self.assertEqual(validate(self.site, self.work, artifacts.ROOT / 'manuscript'), [])
        docs = self.documents()
        for stage in ('raw HTML', 'final HTML'):
            pad = self.padding(self.target(docs)[stage])
            self.assertEqual(''.join(pad.itertext()).strip(), '')
            def mutate(n):
                n.text = '\n '
                etree.SubElement(n, 'span').text = ' '
                etree.SubElement(n, 'br')
            self.change(docs[stage], pad, stage, mutate)
        self.assertEqual(validate(self.site, self.work, artifacts.ROOT / 'manuscript'), [])


if __name__ == '__main__':
    unittest.main()
