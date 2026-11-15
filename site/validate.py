#!/usr/bin/env python3
"""Fail on missing manuscript content, numbering drift, broken links or asset leakage."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from lxml import etree, html
from source import ROOT, collect_dependencies
from bibliography import is_doi_url, parse_doi_url, source_dois, validate_bibliography_dois
from mathml import presentation_structure
from inventory import read_inventory
from coverage import source_stream, validate_inventory
from canonical import (read_aux, validate_labels, validate_reference_text, validate_recorder,
                       canonical_bibliography, validate_canonical_bibliography,
                       read_natbib, validate_citation_display)
from scientific import validate_scientific_math, resolve_scientific_math, REVIEWED_TEX

NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'


def words(text):
    return ' '.join(re.findall(r'[a-z0-9]+', unicodedata.normalize('NFKD', text).lower()))


def text(node):
    node = deepcopy(node)
    for annotation in node.xpath('.//annotation'):
        annotation.getparent().remove(annotation)
    return ' '.join(' '.join(node.itertext()).split())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(output, work, manuscript):
    errors = []
    try:
        page = html.parse(str(output / 'article.html'))
        landing = html.parse(str(output / 'index.html'))
        raw = html.parse(str(work / 'article.html'))
        xml = etree.parse(str(work / 'article.xml'))
        provenance = json.loads((output / 'provenance.json').read_text())
    except (OSError, ValueError, etree.Error) as exc:
        return [f'Missing or malformed build product: {exc}']
    article = page.xpath('//article')[0] if page.xpath('//article') else None
    if article is None:
        return ['Missing complete article']
    ids = Counter(page.xpath('//@id'))
    by_id = {node.get('id'): node for node in page.xpath('//*[@id]')}
    report = {'schema_version': 1, 'valid': False}
    try:
        inventory = read_inventory(manuscript / 'manuscript.tex')
        independent_errors, report = validate_inventory(inventory, xml, raw, page)
        errors.extend(independent_errors)
        aux = read_aux(work / 'manuscript.aux')
        errors.extend(validate_labels(inventory['labels'], aux, xml, page))
        errors.extend(validate_reference_text(aux, xml, raw))
        errors.extend(validate_reference_text(aux, xml, page))
        citations = [event['value'] for event in source_stream(inventory, {}) if event['kind'] == 'cite']
        natbib = read_natbib(work / 'manuscript.aux')
        errors.extend(validate_citation_display(citations, natbib, xml, raw, 'raw HTML'))
        errors.extend(validate_citation_display(citations, natbib, xml, page, 'final HTML'))
        errors.extend(validate_recorder(work / 'manuscript.fls', manuscript, inventory['sources']))
        errors.extend(validate_canonical_bibliography(work / 'manuscript.bbl', xml, raw))
        errors.extend(validate_canonical_bibliography(work / 'manuscript.bbl', xml, page))
        errors.extend(validate_scientific_math(xml, page))
        report['source_sha256'] = {item['path']: item['sha256'] for item in inventory['sources']}
        report['browser'] = browser_expectations(inventory, xml, page, work / 'manuscript.bbl')
    except (ValueError, OSError, KeyError) as exc:
        errors.append(f'Independent source validation failed: {exc}')
    if any(n != 1 for n in ids.values()):
        errors.append('Duplicate article anchors')
    # Exact parity with the converter output includes every paragraph, math
    # annotation, table cell and formal environment, not just section counts.
    for node in raw.xpath('//article//*[@id]'):
        key = node.get('id')
        match = by_id.get(key)
        if match is None:
            errors.append(f'Missing converted content: {key}')
        elif text(node) != text(match):
            errors.append(f'Changed converted content: {key}')
    for node in raw.xpath('//article//math'):
        match = by_id.get(node.get('id'))
        if match is None or presentation_structure(node) != presentation_structure(match):
            errors.append(f'Changed Presentation MathML structure: {node.get("id")}')
    previous_level = 0
    for heading in article.xpath('.//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6'):
        level = int(heading.tag[1])
        if level > previous_level + 1:
            errors.append(f'Skipped article heading level: {heading.tag}: {text(heading)}')
        previous_level = level
    reference_query = '//article//a[contains(concat(" ",@class," ")," ltx_ref ")]'
    original_links = [(n.get('href'), text(n)) for n in raw.xpath(reference_query)]
    final_links = [(n.get('href'), text(n)) for n in page.xpath(reference_query)]
    if original_links != final_links:
        errors.append('Citation or cross-reference destinations differ from converter output')
    # LaTeXML emits a duplicate short caption for lists and a fallback MathFork
    # branch. Neither is selected by its HTML transform; all other math is required.
    maths = xml.xpath('//l:Math[not(ancestor::l:toccaption) and not(parent::l:MathFork)]', namespaces=NS)
    for node in maths:
        match = by_id.get(node.get(XID))
        annotations = [] if match is None else match.xpath('./semantics/annotation[@encoding="application/x-tex"]')
        if match is None or match.tag != 'math' or not annotations:
            errors.append(f'Missing semantic mathematics: {node.get(XID)}')
        elif match.get('alttext') != node.get('tex') or ''.join(annotations[0].itertext()) != node.get('tex'):
            errors.append(f'Changed mathematical source: {node.get(XID)}')
    if page.xpath('//*[contains(@class,"ltx_ERROR") or contains(@class,"ltx_missing")] | //merror'):
        errors.append('Unresolved converter output')
    try:
        metadata = source_dois(manuscript / 'refs.bib')
        errors.extend(validate_bibliography_dois(page, xml.xpath('//l:bibitem', namespaces=NS), metadata, XID))
    except ValueError as exc:
        errors.append(f'Invalid authoritative DOI metadata: {exc}')
    for graphic in xml.xpath('//l:graphics', namespaces=NS):
        expected = 'figures/' + Path(graphic.get('graphic')).with_suffix('.svg').name
        nodes = page.xpath('//img[@id=$key]', key=graphic.get(XID))
        if len(nodes) != 1 or nodes[0].get('src') != expected or not nodes[0].get('alt'):
            errors.append(f'Missing/wrong figure: {expected}')
    # Check every local target and fragment under a project-site base path.
    pages = {'article.html': page, 'index.html': landing}
    for filename, doc in pages.items():
        if doc.getroot().get('lang') != 'en' or not doc.xpath('//meta[@name="viewport"]'):
            errors.append(f'Missing language or viewport: {filename}')
        for target in doc.xpath('//@href | //@src'):
            url = urlsplit(target)
            if is_doi_url(target):
                try:
                    parse_doi_url(target)
                except ValueError as exc:
                    errors.append(str(exc))
            if url.scheme in ('https', 'http', 'mailto'):
                continue
            if url.scheme or target.startswith('/') or '..' in Path(unquote(url.path)).parts:
                errors.append(f'Nonportable local URL: {target}')
                continue
            name = unquote(url.path) or filename
            if not (output / name).is_file():
                errors.append(f'Broken local URL: {filename}: {target}')
            elif url.fragment and name in pages and unquote(url.fragment) not in pages[name].xpath('//@id'):
                errors.append(f'Broken anchor: {filename}: {target}')
    dependencies = collect_dependencies(manuscript)
    expected_figures = {'figures/' + p.with_suffix('.svg').name for p in dependencies if p.suffix == '.pdf'}
    if set(provenance['figures']) != expected_figures:
        errors.append('Unexpected figure provenance inventory')
    if set(provenance['source_sha256']) != {p.relative_to(ROOT).as_posix() for p in dependencies}:
        errors.append('Unexpected source provenance inventory')
    allowed = {'index.html', 'article.html', 'site.css', 'site.js', 'manuscript.pdf', 'provenance.json', 'LICENSE.txt', *expected_figures}
    actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    if actual != allowed or any(p.is_symlink() for p in output.rglob('*')):
        errors.append('Website artifact contains missing, unexpected or symbolic files')
    for relative, expected in provenance['source_sha256'].items():
        if sha(ROOT / relative) != expected:
            errors.append(f'Source provenance mismatch: {relative}')
    if sha(output / 'manuscript.pdf') != provenance['pdf_sha256'] or sha(output / 'manuscript.pdf') != sha(manuscript / 'manuscript.pdf'):
        errors.append('Download differs from canonical PDF')
    for relative, record in provenance['figures'].items():
        if not (output / relative).is_file():
            continue
        svg = etree.parse(str(output / relative))
        if sha(output / relative) != record['sha256'] or sha(ROOT / record['source']) != record['source_sha256']:
            errors.append(f'Figure provenance mismatch: {relative}')
        if svg.xpath('//*[local-name()="image" or local-name()="script"]'):
            errors.append(f'Nonvector or executable SVG: {relative}')
    for filename, doc in pages.items():
        content = words(text(doc.getroot()))
        for phrase in ('submitted for peer review', 'not accepted or published' if filename == 'article.html' else 'not an accepted or published journal article'):
            if words(phrase) not in content:
                errors.append(f'Missing publication status: {filename}')
        if provenance['manuscript_revision']['date'] not in text(doc.getroot()):
            errors.append(f'Missing revision date: {filename}')
    report.update(valid=not errors, errors=errors, article_sha256=sha(output / 'article.html'))
    (work / 'source-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    return errors


def browser_expectations(inventory, xml, page, bbl):
    """Presentation targets become trusted only when every validation gate passes."""
    labels = {label.removeprefix('LABEL:'): node.get(XID) for node in xml.xpath('//*[@labels]')
              for label in node.get('labels').split()}
    unique = lambda values: list(dict.fromkeys(value for value in values if value))
    toc = []
    for section in xml.xpath('/l:document/l:section | /l:document/l:appendix | /l:document/l:bibliography', namespaces=NS):
        toc.append(section.get(XID))
        toc.extend(node.get(XID) for node in section.xpath('./l:subsection', namespaces=NS))
    captures = []
    for query in ('//l:section', '//l:equation[l:tags]', '//l:appendix', '//l:table', '//l:paragraph'):
        nodes = xml.xpath(query, namespaces=NS)
        if nodes:
            captures.append(nodes[0].get(XID))
    for label in REVIEWED_TEX:
        captures.append(resolve_scientific_math(xml, page, label).get('id'))
    selectors = [('math', '//math'), ('.ltx_eqn_eqno', '//*[contains(concat(" ",@class," ")," ltx_eqn_eqno ")]'),
                 ('.ltx_table th', '//figure[contains(@class,"ltx_table")]//th'),
                 ('.ltx_table tbody tr:nth-child(even) td', '//figure[contains(@class,"ltx_table")]//tbody/tr[position() mod 2 = 0]/td')]
    return {
        'math': sum(len(m['cells']) for m in inventory['math'] if m.get('representation') != 'container' and not m['pure_script']),
        'numbered_equations': sum(bool(m['numbered']) for m in inventory['math']),
        'figures': sum(obj['kind'] == 'graphic' for obj in inventory['objects']),
        'tables': sum(obj['kind'] == 'table' for obj in inventory['objects']),
        'bibliography': len(canonical_bibliography(bbl)),
        'toc_targets': unique(toc),
        'reference_targets': unique(labels.get(node.get('labelref').removeprefix('LABEL:')) for node in xml.xpath('//l:ref[@labelref]', namespaces=NS)),
        'bibliography_targets': [n.get(XID) for n in xml.xpath('//l:bibitem', namespaces=NS)],
        'capture_targets': unique(captures),
        'contrast_targets': [selector for selector, query in selectors if page.xpath(query)],
    }


if __name__ == '__main__':
    errors = validate(ROOT / 'build/site', ROOT / 'build/site-work', ROOT / 'manuscript')
    if errors:
        raise SystemExit('\n'.join(errors))
    report = json.loads((ROOT / 'build/site-work/source-validation.json').read_text())
    expected = report['browser']
    print('Site validated against original authored sources and canonical PDF evidence: '
          f"{expected['math']} MathML cells, {expected['numbered_equations']} numbered equations, "
          f"{expected['figures']} vector graphics, {expected['tables']} numbered tables, "
          f"{expected['bibliography']} bibliography entries; "
          'ordered content, mathematical roles, links, provenance and asset allowlist checked.')
