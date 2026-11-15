"""Mutation targets shared by real-artifact tests and independent tiny fixtures."""
import re

from lxml import etree

from canonical import visible_text
from coverage import validate_inventory
from scientific import resolve_scientific_math

NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'
REVIEWED_LABELS = ('eq:connector-clearance', 'eq:measurement-error-energy',
                   'eq:reduced-spectral-bound')


def one(test, nodes, description):
    test.assertEqual(len(nodes), 1, f'Expected one mutation target: {description}; found {len(nodes)}')
    return nodes[0]


def reviewed_math(test, xml, page, label):
    """Resolve a scientific identity before joining its unique source/rendered IDs."""
    rendered = resolve_scientific_math(xml, page, label)
    source = one(test, xml.xpath('//l:Math[@xml:id=$key]', namespaces=NS,
                                 key=rendered.get('id')), label + ' source Math')
    test.assertTrue(source.get(XID), 'Reviewed mathematical target needs an identifier')
    test.assertEqual(source.get(XID), rendered.get('id'))
    return source, rendered


def rename_reviewed_ids(test, xml, page):
    for label in REVIEWED_LABELS:
        source, rendered = reviewed_math(test, xml, page, label)
        old = source.get(XID)
        source.set(XID, 'revised.' + old)
        rendered.set('id', 'revised.' + old)
        test.assertNotEqual(source.get(XID), old)
        test.assertEqual(rendered.get('id'), source.get(XID))


def rename_reviewed_labels(test, xml, page):
    for label in REVIEWED_LABELS:
        source, _ = reviewed_math(test, xml, page, label)
        owner = one(test, source.xpath('ancestor::l:equation[1]', namespaces=NS),
                    label + ' equation owner')
        old = owner.get('labels')
        test.assertTrue(old, 'The label-rename mutation needs an existing source label')
        tex = source.get('tex')
        owner.set('labels', ' '.join('LABEL:renamed:' + value.removeprefix('LABEL:')
                                    for value in old.split()))
        test.assertNotEqual(owner.get('labels'), old)
        test.assertEqual(source.get('tex'), tex, 'A label-only rename must preserve the expression')


def funding_declaration(test, inventory, documents):
    """Follow the first declaration's source order to its matched structural owner.

    The declaration section is the unique unnumbered top-level section with
    unnumbered subsections. Select its first subsection and first prose object
    in authored order, independently of editable headings and body wording.
    """
    objects = {obj['id']: obj for obj in inventory['objects']}
    def children(owner, kind):
        return [objects[token['id']] for token in owner.get('content', [])
                if token['kind'] == 'object' and objects[token['id']]['kind'] == kind]
    def unnumbered_subsections(section):
        return [obj for obj in children(section, 'subsection') if obj.get('number') is None]
    document = one(test, [obj for obj in objects.values() if obj['kind'] == 'document'], 'source document')
    section = one(test, [obj for obj in children(document, 'section')
                         if obj.get('number') is None and not obj.get('appendix') and
                         unnumbered_subsections(obj)], 'unnumbered declaration section')
    subsection = unnumbered_subsections(section)[0]
    prose = children(subsection, 'prose')
    test.assertTrue(prose, 'The first declaration subsection must contain authored prose')
    source = prose[0]
    test.assertEqual(source['owner'], subsection['id'])
    test.assertTrue(all(token['kind'] == 'text' for token in source['content']),
                    'The short declaration mutation requires literal authored prose')
    errors, report = validate_inventory(inventory, documents['XML'], documents['raw HTML'], documents['final HTML'])
    test.assertEqual(errors, [], 'Mutation selection requires an independently matched baseline')
    match = one(test, [entry for entry in report['matches']
                       if entry['source_id'] == source['owner'] and
                       entry['kind'] == 'open' and entry['value'] == 'subsection'],
                'funding declaration source owner')
    owner = one(test, documents['XML'].xpath('//*[@xml:id=$key]', key=match['xml_id']),
                'matched funding subsection')
    paragraph = one(test, owner.xpath('./l:para[1]', namespaces=NS), 'first declaration paragraph')
    test.assertEqual(visible_text(paragraph), ' '.join(''.join(token['text'] for token in source['content']).split()))
    test.assertTrue(paragraph.get(XID), 'Funding declaration needs an identifier for all-stage mutation')
    return paragraph


def declaration_fragment(test, paragraph):
    slot = one(test, paragraph.xpath('./l:p/text()[normalize-space()]', namespaces=NS), 'declaration text')
    words = list(re.finditer(r'\w+', str(slot)))
    test.assertTrue(words, 'Declaration omission must remove authored words')
    return str(slot)[words[0].start():words[min(7, len(words)) - 1].end()]


def labelled_equation_and_section(test, inventory):
    objects = {obj['id']: obj for obj in inventory['objects']}
    numbered = {math['owner'] for math in inventory['math'] if math['numbered']}
    numbered.update(obj['id'] for obj in inventory['objects'] if obj.get('number') is not None)
    labels = []
    for kind in ('equation', 'section'):
        candidates = [label for label, owner in inventory['labels'].items()
                      if objects[owner]['kind'] == kind and owner in numbered]
        test.assertTrue(candidates, 'Label-swap mutation requires a numbered source ' + kind)
        labels.append(candidates[0])
    return tuple(labels)


def swap_label_destinations(test, documents, labels):
    """Corrupt two source meanings consistently without assuming equal numbers."""
    xml = documents['XML']
    owners = [one(test, xml.xpath(
        '//*[@labels and contains(concat(" ",normalize-space(@labels)," "),$label)]',
        label=' LABEL:' + label + ' '), label) for label in labels]
    keys = [owner.get(XID) for owner in owners]
    test.assertTrue(all(keys), 'Both swapped objects need identifiers')
    test.assertNotEqual(keys[0], keys[1], 'The swapped source objects must be distinct')
    for stage, doc in documents.items():
        before = etree.tostring(doc)
        if stage == 'XML':
            values = [owner.get('labels') for owner in owners]
            test.assertNotEqual(values[0], values[1])
            owners[0].set('labels', values[1])
            owners[1].set('labels', values[0])
        else:
            for key in keys:
                one(test, doc.xpath('//*[@id=$key]', key=key), stage + ' swapped owner')
            links = doc.xpath('//a[@href=$first or @href=$second]',
                              first='#' + keys[0], second='#' + keys[1])
            destinations = {'#' + keys[0]: '#' + keys[1], '#' + keys[1]: '#' + keys[0]}
            for link in links:
                old = link.get('href')
                link.set('href', destinations[old])
                test.assertNotEqual(link.get('href'), old)
            if stage == 'final HTML':
                anchors = [one(test, doc.xpath('//*[@id=$key]', key=label), label + ' named anchor')
                           for label in labels]
                anchors[0].set('id', labels[1])
                anchors[1].set('id', labels[0])
            elif not links:
                # Unreferenced source objects have no raw HTML links to rewrite.
                test.assertEqual(etree.tostring(doc), before)
                continue
        test.assertNotEqual(etree.tostring(doc), before, 'Label swap must mutate ' + stage)
