"""Real-artifact audit regressions for equation ownership and scientific grids."""
import unittest

from lxml import etree

import test_validation as artifacts
from validate import validate

NS, XID, css = artifacts.NS, artifacts.XID, artifacts.css


class EquationGridTests(artifacts.ContentIntegrityFixture):
    def test_unchanged_equation_layouts_and_source_tables_pass(self):
        self.assertEqual(validate(self.site, self.work, artifacts.ROOT / 'manuscript'), [])

    @staticmethod
    def mathematical_order(doc, stage):
        query = ('//l:Math[not(ancestor::l:toccaption) and not(parent::l:MathFork)]'
                 if stage == 'XML' else '//article//math')
        return [(node.get(XID if stage == 'XML' else 'id'),
                 node.get('tex' if stage == 'XML' else 'alttext'))
                for node in doc.xpath(query, namespaces=NS)]

    def test_number_transferred_from_unlabelled_equation_to_unnumbered_owner(self):
        docs = self.documents()
        equations = docs['XML'].xpath('//l:equation', namespaces=NS)
        pair = self.first([(a, b) for a, b in zip(equations, equations[1:])
                           if not a.get('labels') and not b.get('labels')
                           and a.xpath('./l:tags/l:tag[@role="refnum"]', namespaces=NS)
                           and not b.xpath('./l:tags', namespaces=NS)],
                          'adjacent numbered/un-numbered unlabelled equations')
        for stage, doc in docs.items():
            first, second = [self.identified(doc, n.get(XID), stage) for n in pair]
            before = self.mathematical_order(doc, stage)
            number_query = ('//l:equation/l:tags/l:tag[@role="refnum"]/text()' if stage == 'XML'
                            else '//*[' + css('ltx_tag_equation') + ']/text()')
            numbers = doc.xpath(number_query, namespaces=NS)
            if stage == 'XML':
                tag = self.one(first.xpath('./l:tags', namespaces=NS), 'numbering tags')
                self.assertFalse(second.xpath('./l:tags', namespaces=NS))
                operation = lambda _: second.insert(0, tag)
            else:
                cell = self.one(first.xpath('.//*[' + css('ltx_eqn_eqno') + ']'), 'number cell')
                self.assertFalse(second.xpath('.//*[' + css('ltx_eqn_eqno') + ']'))
                row = self.one(second.xpath('.//tr[' + css('ltx_eqn_row') + ']'), 'destination row')
                operation = lambda _: row.append(cell)
            self.change(doc, first, stage, operation)
            self.assertEqual(self.mathematical_order(doc, stage), before)
            self.assertEqual(doc.xpath(number_query, namespaces=NS), numbers)
        self.reject('Equation ownership', all_stages=True)

    def test_aligned_cell_moved_across_row_boundary_preserves_flattened_math(self):
        docs = self.documents()
        candidates = []
        for group in docs['XML'].xpath('//l:equationgroup[not(l:tags)]', namespaces=NS):
            rows = group.xpath('./l:equation', namespaces=NS)
            if (len(rows) >= 2 and not any(row.xpath('./l:tags', namespaces=NS) for row in rows)
                    and all(len(row.xpath('./l:MathFork/l:MathBranch/l:td', namespaces=NS)) > 1
                            for row in rows[:2])):
                candidates.append(rows[:2])
        pair = self.first(candidates, 'two unnumbered alignment rows with scientific cells')
        for stage, doc in docs.items():
            owners = [self.identified(doc, n.get(XID), stage) for n in pair]
            before = self.mathematical_order(doc, stage)
            if stage == 'XML':
                rows = [self.one(owner.xpath('./l:MathFork/l:MathBranch', namespaces=NS), 'math branch')
                        for owner in owners]
                cells = [row.xpath('./l:td', namespaces=NS) for row in rows]
            else:
                rows = [self.one(owner.xpath('./tr[' + css('ltx_eqn_row') + ']'), 'alignment row')
                        for owner in owners]
                cells = [row.xpath('./td[math]') for row in rows]
            old_partition = [len(items) for items in cells]
            donor = self.first(cells[1], 'cell to reassign')
            self.change(doc, rows[0], stage, lambda _: rows[0].insert(rows[0].index(cells[0][-1]) + 1, donor))
            self.assertEqual(self.mathematical_order(doc, stage), before)
            query = './l:td' if stage == 'XML' else './td[math]'
            new_partition = [len(row.xpath(query, namespaces=NS)) for row in rows]
            self.assertEqual(new_partition, [old_partition[0] + 1, old_partition[1] - 1])
            self.assertNotEqual(new_partition, old_partition)
        self.reject('Alignment-row ownership', all_stages=True)

    def test_html_equation_ids_cannot_redirect_labels_to_another_owner(self):
        docs = self.documents()
        owners = docs['XML'].xpath('//l:equation[@labels][l:tags/l:tag[@role="refnum"]]', namespaces=NS)[:2]
        self.assertEqual(len(owners), 2, 'Two labelled numbered equation owners must exist')
        keys = [owner.get(XID) for owner in owners]
        self.assertTrue(all(keys))
        self.assertNotEqual(keys[0], keys[1])
        labels = [[value.removeprefix('LABEL:') for value in owner.get('labels').split()]
                  for owner in owners]
        xml_before = etree.tostring(docs['XML'])
        for stage in ('raw HTML', 'final HTML'):
            doc = docs[stage]
            targets = [self.identified(doc, key, stage) for key in keys]
            maths = self.mathematical_order(doc, stage)
            numbers = doc.xpath('//*[' + css('ltx_tag_equation') + ']/text()')
            links = doc.xpath('//a/@href')

            def operation(_):
                for target, key in zip(targets, reversed(keys)):
                    target.set('id', key)
                if stage == 'final HTML':
                    # Preserve the named-anchor placement contract as well as
                    # every visible number and reference destination. Only an
                    # XML-to-HTML owner binding can reject this redirection.
                    for key, owner_labels in zip(keys, labels):
                        target = self.identified(doc, key, stage)
                        tables = target.xpath('ancestor-or-self::table')
                        if tables:
                            target = tables[0]
                        if 'wide-block' in target.getparent().get('class', '').split():
                            target = target.getparent()
                        for label in owner_labels:
                            target.addprevious(self.identified(doc, label, stage))

            self.change(doc, doc.getroot(), stage, operation)
            self.assertEqual(self.mathematical_order(doc, stage), maths)
            self.assertEqual(doc.xpath('//*[' + css('ltx_tag_equation') + ']/text()'), numbers)
            self.assertEqual(doc.xpath('//a/@href'), links)
        self.assertEqual(etree.tostring(docs['XML']), xml_before)
        errors = validate(self.site, self.work, artifacts.ROOT / 'manuscript')
        for stage in ('raw HTML', 'final HTML'):
            self.assertTrue(any('Equation ownership' in error and stage in error for error in errors), errors)

    def source_cells(self, docs):
        owner = self.first(docs['XML'].xpath('//l:table[l:tabular/l:tbody/l:tr/l:td]', namespaces=NS),
                           'source table with body cells')
        result = {}
        for stage, doc in docs.items():
            table = self.identified(doc, owner.get(XID), stage)
            query = ('./l:tabular/l:tbody/l:tr[1]/l:td[1]' if stage == 'XML'
                     else './/table[' + css('ltx_tabular') + ']/tbody/tr[1]/*[self::td or self::th][1]')
            result[stage] = self.one(table.xpath(query, namespaces=NS), 'first scientific body cell')
        return result

    def test_hidden_equation_rows_branches_and_number_cells_are_rejected(self):
        for target in ('row owner', 'math branch', 'HTML row', 'number cell'):
            with self.subTest(target=target):
                self.restore()
                docs = self.documents()
                if target in ('row owner', 'math branch', 'HTML row'):
                    owner = self.first(docs['XML'].xpath(
                        '//l:equationgroup[not(l:tags)]/l:equation[not(l:tags)][l:MathFork/l:MathBranch/l:td]',
                        namespaces=NS), 'nested scientific equation row')
                else:
                    owner = self.first(docs['XML'].xpath('//l:equation[l:tags]', namespaces=NS),
                                       'numbered equation')
                stages = ('XML', 'raw HTML', 'final HTML') if target in ('row owner', 'math branch') else ('raw HTML', 'final HTML')
                for stage in stages:
                    doc = docs[stage]
                    node = self.identified(doc, owner.get(XID), stage)
                    if stage == 'XML' and target == 'math branch':
                        node = self.one(node.xpath('./l:MathFork/l:MathBranch', namespaces=NS), 'math branch')
                    elif target == 'HTML row':
                        node = self.one(node.xpath('.//tr[' + css('ltx_eqn_row') + ']'), 'equation row')
                    elif target == 'number cell':
                        node = self.one(node.xpath('.//td[' + css('ltx_eqn_eqno') + ']'), 'number cell')
                    before = self.mathematical_order(doc, stage)
                    self.change(doc, node, stage, lambda n: n.set('style', 'display:none'))
                    self.assertEqual(self.mathematical_order(doc, stage), before)
                errors = validate(self.site, self.work, artifacts.ROOT / 'manuscript')
                category = 'Equation ownership' if target == 'number cell' else 'Alignment-row ownership'
                for stage in stages:
                    self.assertTrue(any(category in e and stage in e for e in errors), errors)

    def test_invented_or_malformed_source_table_spans_are_rejected(self):
        for attribute, value in (('colspan', '2'), ('rowspan', '2'), ('colspan', '0'),
                                 ('rowspan', '-1'), ('colspan', 'two'), ('rowspan', '1.5'),
                                 ('colspan', '')):
            with self.subTest(attribute=attribute, value=value):
                self.restore()
                docs = self.documents()
                cells = self.source_cells(docs)
                for stage, doc in docs.items():
                    cell = cells[stage]
                    before = ''.join(cell.itertext())
                    self.assertIsNone(cell.get(attribute))
                    self.change(doc, cell, stage, lambda n: n.set(attribute, value))
                    self.assertEqual(''.join(cell.itertext()), before)
                self.reject('Table-grid span', all_stages=True)

    def test_explicit_unit_source_table_spans_are_supported(self):
        docs = self.documents()
        cells = self.source_cells(docs)
        for stage, doc in docs.items():
            def operation(node):
                node.set('colspan', '1')
                node.set('rowspan', '1')
            self.change(doc, cells[stage], stage, operation)
        self.assertEqual(validate(self.site, self.work, artifacts.ROOT / 'manuscript'), [])


if __name__ == '__main__':
    unittest.main()
