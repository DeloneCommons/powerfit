"""Corrupt copied real artifacts while preserving authoritative source evidence."""
from copy import deepcopy
import hashlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from lxml import etree, html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate import validate
from canonical import read_aux, validate_labels
from inventory import read_inventory
from selection_helpers import (funding_declaration, declaration_fragment, reviewed_math,
                               labelled_equation_and_section, swap_label_destinations)

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build'
NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'


def css(name):
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


def remove(node):
    """Remove just the target, retaining the surrounding authored prose."""
    parent, previous, tail = node.getparent(), node.getprevious(), node.tail
    parent.remove(node)
    if tail:
        if previous is None:
            parent.text = (parent.text or '') + tail
        else:
            previous.tail = (previous.tail or '') + tail


class ContentIntegrityFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BUILD / 'site/article.html').is_file():
            raise RuntimeError('Build the actual website before running its integration tests')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name) / 'site'
        shutil.copytree(BUILD / 'site', self.site)
        self.work = Path(self.temp.name) / 'work'
        self.work.mkdir()
        for name in ('article.html', 'article.xml', 'manuscript.aux', 'manuscript.bbl', 'manuscript.fls'):
            source = BUILD / 'site-work' / name
            if not source.is_file() and name == 'manuscript.fls':
                source = BUILD.parent / 'manuscript' / name
            self.assertTrue(source.is_file(), f'Missing canonical artifact: {source}')
            shutil.copy2(source, self.work / name)
        self.paths = {'XML': self.work / 'article.xml', 'raw HTML': self.work / 'article.html',
                      'final HTML': self.site / 'article.html'}
        self.original = {stage: path.read_bytes() for stage, path in self.paths.items()}
        originals = [BUILD / 'site/article.html', BUILD / 'site-work/article.html', BUILD / 'site-work/article.xml',
                     ROOT / 'manuscript/refs.bib', *(ROOT / 'manuscript').rglob('*.tex')]
        self.protected = {p: hashlib.sha256(p.read_bytes()).digest() for p in originals}
        self.addCleanup(self.assert_originals_unchanged)

    def assert_originals_unchanged(self):
        for path, digest in self.protected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest, str(path))

    def restore(self):
        for stage, path in self.paths.items():
            path.write_bytes(self.original[stage])

    def documents(self):
        return {stage: (etree.parse(str(path)) if stage == 'XML' else html.parse(str(path)))
                for stage, path in self.paths.items()}

    def one(self, nodes, description):
        self.assertEqual(len(nodes), 1, f'Expected one mutation target: {description}; found {len(nodes)}')
        return nodes[0]

    def first(self, nodes, description):
        self.assertTrue(nodes, f'Mutation target must exist: {description}')
        return nodes[0]

    def identified(self, doc, key, stage):
        self.assertTrue(key, f'Mutation target needs an identifier: {stage}')
        return self.one(doc.xpath('//*[@xml:id=$key]' if stage == 'XML' else '//*[@id=$key]', key=key), key)

    def labelled(self, xml, label):
        return self.one(xml.xpath('//*[@labels and contains(concat(" ",normalize-space(@labels)," "),$label)]',
                                  label=' LABEL:' + label + ' '), label)

    def change(self, doc, node, stage, operation):
        before = etree.tostring(doc)
        operation(node)
        self.assertNotEqual(etree.tostring(doc), before, f'Mutation did not change {stage}')
        self.paths[stage].write_bytes(etree.tostring(doc, encoding='utf-8') if stage == 'XML' else
                                     html.tostring(doc, encoding='utf-8', doctype='<!doctype html>'))
        self.assertNotEqual(self.paths[stage].read_bytes(), self.original[stage], f'{stage} mutation was not saved')

    def remove_identified(self, source):
        for stage, doc in self.documents().items():
            self.change(doc, self.identified(doc, source.get(XID), stage), stage, remove)

    def reject(self, category, *, all_stages=False):
        errors = validate(self.site, self.work, ROOT / 'manuscript')
        self.assertTrue(any(category.lower() in e.lower() for e in errors), f'Expected {category}: {errors}')
        if all_stages:
            for stage in self.paths:
                self.assertTrue(any(category.lower() in e.lower() and stage in e for e in errors),
                                f'{stage} did not independently reject {category}: {errors}')

    def mutate_final(self, query, operation=remove):
        doc = self.documents()['final HTML']
        self.change(doc, self.first(doc.xpath(query), query), 'final HTML', operation)

    def remove_fragment(self, source, fragment):
        for stage, doc in self.documents().items():
            owner = self.identified(doc, source.get(XID), stage)
            slots = owner.xpath('.//text()[not(ancestor::*[local-name()="Math" or local-name()="math"])]')
            slot = self.one([s for s in slots if fragment in str(s)], 'authored text fragment in ' + stage)
            self.assertEqual(str(slot).count(fragment), 1)
            def operation(_):
                value = str(slot).replace(fragment, '', 1)
                if slot.is_tail:
                    slot.getparent().tail = value
                else:
                    slot.getparent().text = value
            self.change(doc, owner, stage, operation)


class ContentIntegrityTests(ContentIntegrityFixture):
    def test_complete_generated_site_passes(self):
        self.assertEqual(validate(self.site, self.work, ROOT / 'manuscript'), [])

    def test_unlabelled_numbered_equation_omitted_everywhere_is_rejected(self):
        node = self.first(self.documents()['XML'].xpath(
            '//l:equation[l:tags/l:tag[@role="refnum"] and not(@labels)]', namespaces=NS), 'unlabelled numbered equation')
        self.remove_identified(node)
        self.reject('Source mathematics', all_stages=True)

    def test_inline_expression_omitted_everywhere_is_rejected(self):
        node = self.first(self.documents()['XML'].xpath(
            '//l:Math[@mode="inline" and not(ancestor::l:toccaption) and not(parent::l:MathFork)]', namespaces=NS), 'inline mathematics')
        self.remove_identified(node)
        self.reject('Source mathematics', all_stages=True)

    def test_pure_script_omitted_everywhere_is_rejected(self):
        docs = self.documents()
        script = self.first(docs['XML'].xpath('//l:sup', namespaces=NS), 'standalone superscript')
        owner = self.first(script.xpath('ancestor::*[@xml:id][1]'), 'script owner')
        index = owner.xpath('.//l:sup', namespaces=NS).index(script)
        for stage, doc in docs.items():
            parent = self.identified(doc, owner.get(XID), stage)
            query = './/l:sup' if stage == 'XML' else './/sup[' + css('ltx_sup') + ']'
            scripts = parent.xpath(query, namespaces=NS)
            self.assertGreater(len(scripts), index, 'Corresponding standalone superscript must exist')
            self.change(doc, scripts[index], stage, remove)
        self.reject('Source mathematics', all_stages=True)

    def test_short_proof_fragment_omitted_everywhere_is_rejected(self):
        slots = self.documents()['XML'].xpath('//l:proof//l:p/text()', namespaces=NS)
        slot = self.first([s for s in slots if len(re.findall(r'\w+', str(s))) >= 3], 'proof body fragment')
        words = list(re.finditer(r'\w+', str(slot)))
        fragment = str(slot)[words[0].start():words[2].end()]
        self.assertEqual(len(re.findall(r'\w+', fragment)), 3)
        owner = self.first(slot.getparent().xpath('ancestor::l:para[@xml:id][1]', namespaces=NS), 'proof paragraph')
        self.remove_fragment(owner, fragment)
        self.reject('Source content', all_stages=True)

    def test_short_funding_declaration_omitted_everywhere_is_rejected(self):
        inventory = read_inventory(ROOT / 'manuscript/manuscript.tex')
        owner = funding_declaration(self, inventory, self.documents())
        fragment = declaration_fragment(self, owner)
        self.remove_fragment(owner, fragment)
        self.reject('Source content', all_stages=True)

    def test_source_funding_hidden_in_every_representation_is_rejected(self):
        docs = self.documents()
        inventory = read_inventory(ROOT / 'manuscript/manuscript.tex')
        owner = funding_declaration(self, inventory, docs)
        for stage, doc in docs.items():
            node = self.identified(doc, owner.get(XID), stage)
            content = ''.join(node.itertext())
            self.change(doc, node, stage, lambda n: n.set('style', 'display:none'))
            self.assertEqual(''.join(node.itertext()), content, 'Hidden authored text remains in the DOM')
        self.reject('Source content', all_stages=True)

    def test_missing_duplicate_and_changed_cells_in_numbered_and_unnumbered_tables(self):
        for location in ('reviewed', 'unnumbered'):
            for mutation in ('missing', 'duplicate', 'changed'):
                with self.subTest(location=location, mutation=mutation):
                    self.restore()
                    docs = self.documents()
                    if location == 'reviewed':
                        owner = self.labelled(docs['XML'], 'tab:refinement-paired')
                        index = 0
                    else:
                        table = self.first(docs['XML'].xpath('//l:tabular[not(ancestor::l:table)]', namespaces=NS), 'unnumbered table')
                        owner = self.first(table.xpath('ancestor::*[@xml:id][1]'), 'unnumbered table owner')
                        index = owner.xpath('.//l:tabular', namespaces=NS).index(table)
                    for stage, doc in docs.items():
                        parent = self.identified(doc, owner.get(XID), stage)
                        tables = parent.xpath('.//l:tabular' if stage == 'XML' else './/table[' + css('ltx_tabular') + ']', namespaces=NS)
                        self.assertGreater(len(tables), index, 'Corresponding authored table must exist')
                        query = './l:tbody/l:tr[1]/l:td[1]' if stage == 'XML' else './tbody/tr[1]/td[1]'
                        cell = self.one(tables[index].xpath(query, namespaces=NS), 'first authored data cell')
                        def operation(node):
                            if mutation == 'missing':
                                remove(node)
                            elif mutation == 'duplicate':
                                node.addnext(deepcopy(node))
                            else:
                                for child in list(node):
                                    node.remove(child)
                                node.text = 'CORRUPTED SCIENTIFIC CELL'
                        self.change(doc, cell, stage, operation)
                    self.reject('Source content', all_stages=True)

    def test_math_annotations_with_changed_operand_roles_are_rejected(self):
        patterns = {'numerator': r'\\frac\s*\{([^{}]+)\}',
                    'denominator': r'\\frac\s*\{[^{}]*\}\s*\{([^{}]+)\}',
                    'subscript': r'_\{([^{}]+)\}', 'superscript': r'\^\{([^{}]+)\}',
                    'limit': r'\\(?:sum|prod|int|lim|min|max)\s*_\{([^{}]+)\}'}
        for role, pattern in patterns.items():
            with self.subTest(role=role):
                self.restore()
                docs = self.documents()
                candidates = docs['XML'].xpath('//l:Math[not(ancestor::l:toccaption) and not(parent::l:MathFork)]', namespaces=NS)
                source = self.first([n for n in candidates if re.search(pattern, n.get('tex', ''))], role)
                old = source.get('tex')
                match = re.search(pattern, old)
                new = old[:match.start(1)] + '987654321' + old[match.end(1):]
                self.assertNotEqual(old, new)
                for stage, doc in docs.items():
                    node = self.identified(doc, source.get(XID), stage)
                    def operation(math):
                        if stage == 'XML':
                            self.assertEqual(math.get('tex'), old)
                            math.set('tex', new)
                        else:
                            self.assertEqual(math.get('alttext'), old)
                            math.set('alttext', new)
                            annotation = self.one(math.xpath('./semantics/annotation[@encoding="application/x-tex"]'), 'TeX annotation')
                            self.assertEqual(annotation.text, old)
                            annotation.text = new
                    self.change(doc, node, stage, operation)
                self.reject('Source mathematics', all_stages=True)

    def test_wrong_equation_number_everywhere_is_rejected(self):
        docs = self.documents()
        equation = self.first(docs['XML'].xpath('//l:equation[l:tags/l:tag[@role="refnum"]]', namespaces=NS), 'numbered equation')
        for stage, doc in docs.items():
            owner = self.identified(doc, equation.get(XID), stage)
            query = './l:tags/l:tag[@role="refnum"]' if stage == 'XML' else './/*[' + css('ltx_tag_equation') + ']'
            node = self.one(owner.xpath(query, namespaces=NS), 'equation number')
            self.change(doc, node, stage, lambda n: setattr(n, 'text', '999999' if stage == 'XML' else '(999999)'))
        self.reject('Source equation numbering')

    def test_consistently_corrupted_generated_visible_identities_are_rejected(self):
        cases = (
            ('proposition kind', 'prop:cycle-compatibility',
             './l:tags/l:tag[not(@role="refnum")] | ./l:title/l:tag',
             './/*[' + css('ltx_tag_theorem') + ']'),
            ('section number', 'sec:introduction',
             './l:tags/l:tag[not(@role)] | ./l:title/l:tag',
             './*[' + css('ltx_title_section') + ']/*[' + css('ltx_tag_section') + ']'),
            ('figure number', 'fig:two-site-separators',
             './l:tags/l:tag[not(@role)] | ./l:caption/l:tag | ./l:toccaption/l:tag',
             './figcaption/*[' + css('ltx_tag_figure') + ']'),
        )
        for role, label, xml_query, html_query in cases:
            with self.subTest(role=role):
                self.restore()
                docs = self.documents()
                source = self.labelled(docs['XML'], label)
                canonical_number = self.one(source.xpath('./l:tags/l:tag[@role="refnum"]/text()', namespaces=NS),
                                            label + ' unchanged canonical number')
                original_class = source.get('class')
                for stage, doc in docs.items():
                    owner = self.identified(doc, source.get(XID), stage)
                    targets = owner.xpath(xml_query if stage == 'XML' else html_query, namespaces=NS)
                    self.assertTrue(targets, 'Generated visible identity must exist: ' + role)
                    def operation(_):
                        changed = 0
                        for target in targets:
                            for node in target.iter():
                                if node.text is None:
                                    continue
                                old = node.text
                                if role == 'proposition kind':
                                    node.text = old.replace('Proposition', 'Conjecture')
                                else:
                                    node.text = re.sub(r'\d+', '999', old)
                                changed += old != node.text
                        self.assertGreater(changed, 0, 'Visible identity mutation must change its displayed type or number')
                    self.change(doc, owner, stage, operation)
                self.assertEqual(source.get('class'), original_class, 'The source theorem kind remains proposition')
                self.assertEqual(source.xpath('./l:tags/l:tag[@role="refnum"]/text()', namespaces=NS), [canonical_number],
                                 'Canonical number metadata must remain unchanged')
                self.reject('Source visible identity')

    def test_reference_visible_number_corrupted_with_correct_destination_is_rejected(self):
        docs = self.documents()
        source = self.first(docs['XML'].xpath('//l:ref[@labelref]', namespaces=NS), 'numbered cross-reference')
        target = self.labelled(docs['XML'], source.get('labelref').removeprefix('LABEL:'))
        owner = self.first(source.xpath('ancestor::*[@xml:id][1]'), 'reference paragraph')
        for stage in ('raw HTML', 'final HTML'):
            doc = docs[stage]
            parent = self.identified(doc, owner.get(XID), stage)
            link = self.one(parent.xpath('.//a[@href=$href]', href='#' + target.get(XID)), 'correct reference destination')
            href = link.get('href')
            slot = self.first([slot for slot in link.xpath('.//text()') if re.search(r'\d+', str(slot))],
                              'visible reference number')
            def operation(_):
                value = re.sub(r'\d+', '999', str(slot))
                if slot.is_tail:
                    slot.getparent().tail = value
                else:
                    slot.getparent().text = value
            self.change(doc, link, stage, operation)
            self.assertEqual(link.get('href'), href, 'Reference destination must remain correct')
        self.reject('Canonical reference text')

    def test_hidden_generated_theorem_identity_is_rejected(self):
        docs = self.documents()
        source = self.labelled(docs['XML'], 'prop:cycle-compatibility')
        for stage, doc in docs.items():
            owner = self.identified(doc, source.get(XID), stage)
            query = './l:title/l:tag' if stage == 'XML' else './/*[' + css('ltx_tag_theorem') + ']'
            target = self.one(owner.xpath(query, namespaces=NS), 'visible theorem identity')
            before = ''.join(target.itertext())
            self.change(doc, target, stage, lambda node: node.set('style', 'display:none'))
            self.assertEqual(''.join(target.itertext()), before)
        self.reject('Source visible identity')

    def test_reviewed_roles_reject_identical_raw_and_final_structure_corruption(self):
        for label, query, action in (
            ('eq:reduced-spectral-bound', './/msup[mi="R"]', 'script'),
            ('eq:measurement-error-energy', './/munderover', 'limits'),
            ('eq:connector-clearance', './/munder', 'minimum'),
        ):
            with self.subTest(label=label):
                self.restore()
                docs = self.documents()
                for stage in ('raw HTML', 'final HTML'):
                    doc = docs[stage]
                    _, math = reviewed_math(self, docs['XML'], doc, label)
                    operators = math.xpath(query)
                    self.assertEqual(len(operators), 2 if action == 'script' else 1,
                                     'Reviewed operand-role targets must have their independent multiplicity')
                    annotation = self.one(math.xpath('./semantics/annotation'), 'source annotation').text
                    def operation(_):
                        for operator in operators:
                            if action == 'script':
                                operator.tag = 'msub'
                            else:
                                children = list(operator)
                                a, b = (1, 2) if action == 'limits' else (0, 1)
                                children[a], children[b] = children[b], children[a]
                                operator[:] = children
                    self.change(doc, math, stage, operation)
                    self.assertEqual(self.one(math.xpath('./semantics/annotation'), 'source annotation').text, annotation)
                self.reject('Scientific MathML role')

    def test_missing_bibliography_author_or_title_everywhere_is_rejected(self):
        for field in ('author', 'title'):
            with self.subTest(field=field):
                self.restore()
                docs = self.documents()
                item = self.first(docs['XML'].xpath('//l:bibitem[l:bibblock]', namespaces=NS), 'bibliography entry')
                block = self.one(item.xpath('./l:bibblock', namespaces=NS), 'bibliography block')
                lines = [line.strip() for line in (block.text or '').splitlines() if line.strip()]
                self.assertGreaterEqual(len(lines), 3, 'Author and title mutation fields must exist')
                fragment = lines[0 if field == 'author' else 1]
                self.remove_fragment(item, fragment)
                self.reject('canonical bibliography')

    def test_citation_to_wrong_existing_entry_everywhere_is_rejected(self):
        docs = self.documents()
        source = self.first(docs['XML'].xpath('//l:cite/l:bibref[not(contains(@bibrefs,","))]', namespaces=NS), 'single-key citation')
        old_key = source.get('bibrefs')
        old = self.one(docs['XML'].xpath('//l:bibitem[@key=$key]', key=old_key, namespaces=NS), old_key)
        other = self.first(docs['XML'].xpath('//l:bibitem[@key!=$key]', key=old_key, namespaces=NS), 'different existing citation target')
        owner = self.first(source.xpath('ancestor::*[@xml:id][1]'), 'citation paragraph')
        for stage, doc in docs.items():
            parent = self.identified(doc, owner.get(XID), stage)
            query = './/l:cite/l:bibref[@bibrefs=$target]' if stage == 'XML' else './/cite//a[@href=$target]'
            target = old_key if stage == 'XML' else '#' + old.get(XID)
            node = self.one(parent.xpath(query, target=target, namespaces=NS), 'citation occurrence')
            self.change(doc, node, stage, lambda n: n.set('bibrefs' if stage == 'XML' else 'href',
                                                        other.get('key') if stage == 'XML' else '#' + other.get(XID)))
        self.reject('Source content', all_stages=True)

    def test_reference_to_wrong_existing_label_everywhere_is_rejected(self):
        docs = self.documents()
        source = self.first(docs['XML'].xpath('//l:ref[@labelref]', namespaces=NS), 'cross-reference')
        old_label = source.get('labelref')
        old = self.labelled(docs['XML'], old_label.removeprefix('LABEL:'))
        other = self.first(docs['XML'].xpath('//*[@labels and @labels!=$old]', old=old_label), 'different existing source label')
        owner = self.first(source.xpath('ancestor::*[@xml:id][1]'), 'cross-reference paragraph')
        for stage, doc in docs.items():
            parent = self.identified(doc, owner.get(XID), stage)
            query = './/l:ref[@labelref=$target]' if stage == 'XML' else './/a[@href=$target]'
            target = old_label if stage == 'XML' else '#' + old.get(XID)
            node = self.one(parent.xpath(query, target=target, namespaces=NS), 'reference occurrence')
            self.change(doc, node, stage, lambda n: n.set('labelref' if stage == 'XML' else 'href',
                                                        other.get('labels').split()[0] if stage == 'XML' else '#' + other.get(XID)))
        self.reject('Source content', all_stages=True)

    def test_coordinated_label_and_destination_swap_is_rejected(self):
        docs = self.documents()
        inventory = read_inventory(ROOT / 'manuscript/manuscript.tex')
        labels = labelled_equation_and_section(self, inventory)
        aux = read_aux(self.work / 'manuscript.aux')
        self.assertEqual(validate_labels(inventory['labels'], aux, docs['XML'], docs['final HTML']), [])
        before = {stage: etree.tostring(doc) for stage, doc in docs.items()}
        swap_label_destinations(self, docs, labels)
        for stage, doc in docs.items():
            if etree.tostring(doc) != before[stage]:
                self.paths[stage].write_bytes(etree.tostring(doc, encoding='utf-8') if stage == 'XML' else
                                             html.tostring(doc, encoding='utf-8', doctype='<!doctype html>'))
                self.assertNotEqual(self.paths[stage].read_bytes(), self.original[stage])
        # Canonical checks may also reject this swap after an innocent equation
        # insertion. Ownership must reject it regardless of numbering equality.
        canonical = validate_labels(inventory['labels'], aux, docs['XML'], docs['final HTML'])
        for label in labels:
            self.assertEqual(any('Canonical numbering mismatch: ' + label + ':' in error for error in canonical),
                             aux[labels[0]]['number'] != aux[labels[1]]['number'], canonical)
        self.reject('Source label ownership')

    def test_named_source_anchor_moved_to_another_valid_object_is_rejected(self):
        docs = self.documents()
        source = self.labelled(docs['XML'], 'eq:exact-incidence')
        other = self.labelled(docs['XML'], 'sec:discussion')
        self.assertNotEqual(source.get(XID), other.get(XID))
        doc = docs['final HTML']
        anchor = self.identified(doc, 'eq:exact-incidence', 'final HTML')
        self.assertIn('source-anchor', anchor.get('class', '').split())
        target = self.identified(doc, other.get(XID), 'final HTML')
        hrefs, ids = doc.xpath('//@href'), sorted(doc.xpath('//@id'))
        content = re.findall(r'\w+|[^\w\s]', ''.join(doc.xpath('//article')[0].itertext()))
        def operation(node):
            node.getparent().remove(node)
            target.addprevious(node)
        self.change(doc, anchor, 'final HTML', operation)
        self.assertEqual(doc.xpath('//@href'), hrefs, 'Only the anchor location should change')
        self.assertEqual(sorted(doc.xpath('//@id')), ids, 'Every destination must remain valid')
        self.assertEqual(re.findall(r'\w+|[^\w\s]', ''.join(doc.xpath('//article')[0].itertext())), content,
                         'Moving a named anchor must preserve authored content')
        self.reject('named source anchor location')

    def test_source_figure_removed_everywhere_is_rejected(self):
        self.remove_identified(self.labelled(self.documents()['XML'], 'fig:two-site-separators'))
        self.reject('Source content', all_stages=True)

    def test_source_figure_associated_with_another_existing_asset_is_rejected(self):
        docs = self.documents()
        source = self.one(self.labelled(docs['XML'], 'fig:two-site-separators').xpath('./l:graphics', namespaces=NS), 'reviewed graphic')
        other = self.first(docs['XML'].xpath('//l:graphics[@graphic!=$path]', path=source.get('graphic'), namespaces=NS), 'different source graphic')
        replacement = other.get('graphic')
        for stage in ('XML', 'final HTML'):
            doc = docs[stage]
            node = self.identified(doc, source.get(XID), stage)
            self.change(doc, node, stage, lambda n: n.set('graphic' if stage == 'XML' else 'src',
                                                        replacement if stage == 'XML' else 'figures/' + Path(replacement).with_suffix('.svg').name))
        # Empty raw image placeholders obtain their identity from XML, and
        # therefore inherit precisely the same incorrect association.
        self.reject('Source content', all_stages=True)

    def test_math_alignment_attribute_is_rejected(self):
        self.mutate_final('//math//mtable[not(@columnalign="left")]', lambda n: n.set('columnalign', 'left'))
        self.reject('MathML structure')

    def test_skipped_paragraph_heading_is_rejected(self):
        docs = self.documents()
        source = self.first(docs['XML'].xpath('//l:paragraph[@xml:id]', namespaces=NS), 'paragraph heading')
        owner = self.identified(docs['final HTML'], source.get(XID), 'final HTML')
        heading = self.one(owner.xpath('./*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5]'), 'paragraph heading level')
        self.change(docs['final HTML'], heading, 'final HTML', lambda n: setattr(n, 'tag', 'h6'))
        self.reject('heading level')

    def test_broken_reference_is_rejected(self):
        self.mutate_final('//article//a[starts-with(@href,"#") and ' + css('ltx_ref') + ']', lambda n: n.set('href', '#missing-source-target'))
        self.reject('Broken anchor')

    def doi_mutation(self, operation):
        for stage in ('raw HTML', 'final HTML'):
            doc = self.documents()[stage]
            link = self.first(doc.xpath('//li[' + css('ltx_bibitem') + ']//a[starts-with(@href,"https://doi.org/")]'), 'bibliography DOI')
            self.change(doc, link, stage, operation)

    def test_corrupt_doi_in_converter_and_site_is_rejected(self):
        for value in ('https://doi.org/%****%20manuscript.bbl%20Line%20125%20****10.1002/ijch.198000003',
                      'https://doi.org/10.1002/a-valid-but-wrong-doi'):
            with self.subTest(value=value):
                self.restore()
                def operation(link):
                    link.set('href', value)
                    link.text = value
                self.doi_mutation(operation)
                self.reject('DOI')

    def test_missing_doi_in_converter_and_site_is_rejected(self):
        self.doi_mutation(remove)
        self.reject('DOI')

    def test_malformed_archive_doi_is_rejected(self):
        path = self.site / 'index.html'
        doc = html.parse(str(path))
        link = self.first(doc.xpath('//a[starts-with(@href,"https://doi.org/")]'), 'archive DOI')
        before = etree.tostring(doc)
        link.set('href', 'https://doi.org/10.5281/zenodo. bad')
        self.assertNotEqual(etree.tostring(doc), before)
        path.write_bytes(html.tostring(doc, encoding='utf-8'))
        self.reject('DOI')

    def test_root_relative_asset_is_rejected(self):
        self.mutate_final('//link[@rel="stylesheet"]', lambda n: n.set('href', '/site.css'))
        self.reject('Nonportable local URL')

    def test_unapproved_artifact_is_rejected(self):
        target = self.site / 'private-record.txt'
        self.assertFalse(target.exists())
        target.write_text('must not ship')
        self.assertTrue(target.is_file())
        self.reject('unexpected')

    def test_changed_pdf_is_rejected(self):
        target = self.site / 'manuscript.pdf'
        before = target.read_bytes()
        target.write_bytes(before + b'changed')
        self.assertNotEqual(target.read_bytes(), before)
        self.reject('canonical PDF')


if __name__ == '__main__':
    unittest.main()
