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
from source import ROOT, authored_sources, collect_dependencies, read_tex
from bibliography import is_doi_url, parse_doi_url, source_dois, validate_bibliography_dois

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


def prose_fragments(source):
    """Long literal prose spans provide a source-to-converter omission check.

    Math and TeX controls break spans; they are checked separately by the
    equation/label inventories and the converter's MathML/TeX pairs.
    """
    source = re.sub(r'\\\[.*?\\\]|\$[^$]*\$', '\n#\n', source, flags=re.S)
    source = re.sub(r'\\(?:begin|end)\{(?:equation\*?|align\*?|aligned|cases)\}', '#', source)
    source = re.sub(r'\\(?:label|cite\w*|ref|eqref|input|includegraphics)(?:\[[^\]]*\])*\{[^}]*\}', '#', source)
    source = re.sub(r'\\[A-Za-z]+\*?(?:\[[^\]]*\])?', '#', source)
    for chunk in re.split(r'[#{}$&\\\n]\s*', source):
        # Match across ordinary source line wraps below, not command boundaries.
        if len(words(chunk).split()) >= 10:
            yield words(chunk)


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
    reference_query = '//article//a[contains(concat(" ",@class," ")," ltx_ref ")]'
    original_links = [(n.get('href'), text(n)) for n in raw.xpath(reference_query)]
    final_links = [(n.get('href'), text(n)) for n in page.xpath(reference_query)]
    if original_links != final_links:
        errors.append('Citation or cross-reference destinations differ from converter output')
    for name, query, expected in [
        ('main sections', './l:section[l:tags]', 9), ('appendices', './l:appendix', 5),
        ('figures', '//l:figure', 7), ('tables', '//l:table', 4),
        ('bibliography entries', '//l:bibitem', 34), ('proofs', '//l:proof', 5),
        ('formal statements', '//l:theorem', 4),
    ]:
        if len(xml.xpath(query, namespaces=NS)) != expected:
            errors.append(f'Expected {expected} {name}')
    # Source labels and numbering must agree with the canonical PDF's auxiliary file.
    aux = (work / 'manuscript.aux').read_text()
    labels = dict(re.findall(r'\\newlabel\{([^}]+)\}\{\{([^}]*)\}', aux))
    for label, number in labels.items():
        nodes = xml.xpath('//*[@labels and contains(concat(" ",@labels," "),$label)]', label=' LABEL:' + label + ' ')
        if len(nodes) != 1:
            errors.append(f'Missing or duplicate source label: {label}')
            continue
        actual = nodes[0].xpath('./l:tags/l:tag[@role="refnum"]/text()', namespaces=NS)
        if actual != [number]:
            errors.append(f'PDF/HTML numbering mismatch: {label}: {actual} != {number}')
        if label not in ids:
            errors.append(f'Missing named source anchor: {label}')
    equation_numbers = [text(n) for n in page.xpath('//td//span[contains(@class,"ltx_tag_equation")]')]
    if equation_numbers != [f'({n})' for n in range(1, 76)]:
        errors.append('Numbered equations must be complete and ordered (1)–(75)')
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
    # Compare independent literal source prose against rendered content, excluding
    # hidden annotations so raw TeX cannot falsely satisfy the check.
    visible = deepcopy(article)
    for node in visible.xpath('.//annotation'):
        node.getparent().remove(node)
    corpus = words(text(visible))
    for source in authored_sources(manuscript):
        for fragment in prose_fragments(read_tex(source)):
            if fragment not in corpus:
                errors.append(f'Missing source prose ({source.name}): {fragment[:100]}')
    expected_bib = set(re.findall(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}', (work / 'manuscript.bbl').read_text()))
    if {n.get('key') for n in xml.xpath('//l:bibitem', namespaces=NS)} != expected_bib:
        errors.append('Bibliography differs from the canonical PDF bibliography')
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
    return errors


if __name__ == '__main__':
    errors = validate(ROOT / 'build/site', ROOT / 'build/site-work', ROOT / 'manuscript')
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Site validated: 9 sections, 5 appendices, 75 numbered equations, 4 formal statements, '
          '5 proofs, 7 vector figures, 4 tables, 34 references; source prose, numbering, links, provenance and asset allowlist checked.')
