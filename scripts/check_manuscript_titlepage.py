#!/usr/bin/env python3
"""Check source-derived CAM front matter on canonical PDF page one.

The contract covers the supported title, author, email, affiliation, complete
plain-text abstract, keywords, classification label/value, and opening root
prose declarations before the first body input, page break or section heading.
It derives expectations only from authored TeX, using the stdlib source reader;
no website build, converter output or third-party Python package is needed.

This checks content presence on page one, not typography or precise placement.
PDF comparison ignores case, punctuation, whitespace and compatibility ligatures
so line wrapping/hyphenation cannot freeze current pagination. Email receives an
additional punctuation-preserving comparison. Mathematical/reference/citation
runs are left to independent site coverage and canonical TeX compilation; each
surrounding plain-text run remains required. Math-only fields add no PDF-text
claim. This check does not verify mathematical roles or rendered reference values.
With --bbl, this also checks literal alphanumeric bibliography pages/ranges
from fresh canonical .bbl against the whole PDF text. This bounded regression
preserves page prefixes; it does not validate the complete PDF bibliography.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'site'))
from inventory import read_inventory  # noqa: E402
from texsyntax import command_at, group, skip_space, strip_comments  # noqa: E402

FIELDS = {'title': 'title', 'author': 'author', 'email': 'email',
          'affil': 'affiliation', 'abstract': 'abstract', 'keywords': 'keywords',
          'pacs': 'classification'}


def _opening_limit(text):
    """Locate title-page boundaries in original master coordinates, lexically."""
    pos, after_title, title_end = 0, False, None
    while pos < len(text):
        if text[pos] == '{':
            _, pos = group(text, pos)
        elif text[pos] == '\\':
            start = pos
            command, pos = command_at(text, pos)
            if command == 'maketitle':
                if after_title:
                    raise ValueError('Unsupported title-page source: duplicate maketitle')
                after_title, title_end = True, pos
            elif after_title and command in ('input', 'include', 'clearpage', 'newpage',
                                              'section', 'subsection', 'chapter', 'end'):
                # End minipage closes a title-page layout container, not the page.
                if command == 'end':
                    match = re.match(r'\s*\{([^}]+)\}', text[pos:])
                    if not match or match.group(1) != 'document':
                        continue
                return title_end, start
        else:
            pos += 1
    if title_end is None:
        raise ValueError('Unsupported title-page source: missing maketitle')
    return title_end, len(text)


def _plain_parts(runs):
    values = ['']
    for run in runs:
        if run['kind'] == 'text':
            values[-1] += run['text']
        elif run['kind'] == 'link':
            linked = _plain_parts(run['content'])
            if linked:
                values[-1] += linked[0]
                values.extend(linked[1:])
        elif run['kind'] in ('math', 'ref', 'cite'):
            values.append('')
        else:
            raise ValueError(f'Unsupported title-page text run: {run["kind"]}')
    return [value.strip() for value in values if _letters(value)]


def titlepage_expectations(master):
    """Return source role/text/location records independently of the PDF."""
    master = Path(master).resolve()
    text = strip_comments(master.read_text())
    title_end, limit = _opening_limit(text)
    title_line = text.count('\n', 0, title_end) + 1
    # Parse the exact original prefix, preserving offsets/line breaks. This
    # deliberately scoped title-page inventory neither reads nor validates later
    # body syntax. Unicode mapping input keeps its explicitly nonprinting role.
    with tempfile.TemporaryDirectory(prefix='powerfit-titlepage-') as temporary:
        root = Path(temporary)
        prefix = text[:limit] + '\n' + r'\end{document}' + '\n'
        entry = root / master.name
        entry.write_text(prefix)
        if 'tex-support/glyphtounicode-cmr.tex' in prefix:
            support = root / 'tex-support/glyphtounicode-cmr.tex'
            support.parent.mkdir()
            support.write_bytes((master.parent / 'tex-support/glyphtounicode-cmr.tex').read_bytes())
        inventory = read_inventory(entry)
    document = inventory['objects'][0]['id']
    front, declarations = {}, []
    for obj in inventory['objects']:
        if obj['source'] != master.name or obj['owner'] != document:
            continue
        kind = obj['kind']
        if kind in FIELDS and obj['line'] <= title_line:
            if kind in front:
                raise ValueError(f'Unsupported title-page source: duplicate {kind}')
            front[kind] = obj
        elif kind == 'prose':
            declarations.append(obj)
    if set(front) != set(FIELDS):
        raise ValueError('Unsupported title-page source: missing ' + ', '.join(sorted(set(FIELDS) - front.keys())))
    expected = []
    for kind, role in FIELDS.items():
        obj = front[kind]
        parts = _plain_parts(obj['content'])
        expected.append({'role': role, 'text': ' '.join(parts), 'fragments': parts,
                         'source': obj['source'], 'line': obj['line']})
    pacs = front['pacs']
    if not pacs.get('option'):
        raise ValueError('Unsupported title-page source: missing classification label')
    expected.append({'role': 'classification label', 'text': pacs['option'],
                     'source': pacs['source'], 'line': pacs['line']})
    for obj in declarations:
        parts = _plain_parts(obj['content'])
        expected.append({'role': 'declaration', 'text': ' '.join(parts), 'fragments': parts,
                         'source': obj['source'], 'line': obj['line']})
    return expected


def _letters(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    value = re.sub(r'[-‐‑]\s*\n\s*', '', value)
    return ' '.join(''.join(char for char in value if char.isalnum() or char.isspace()).split())


def validate_titlepage(master, first_page_text):
    """Return diagnostics for missing source-derived first-page content."""
    first_page_text = first_page_text.split('\f', 1)[0]
    letters = _letters(first_page_text)
    compact = ''.join(unicodedata.normalize('NFKC', first_page_text).split())
    errors = []
    expectations = titlepage_expectations(master)
    abstract = next(entry for entry in expectations if entry['role'] == 'abstract')
    abstract_parts = abstract.get('fragments', [])
    abstract_start = letters.find(_letters(abstract_parts[0])) if abstract_parts else -1
    for entry in expectations:
        value = entry['text']
        region = letters
        if entry['role'] in ('title', 'author', 'email', 'affiliation') and abstract_start >= 0:
            region = letters[:abstract_start]
        present = all(_letters(fragment) in region for fragment in entry.get('fragments', [value]))
        if entry['role'] == 'email':
            present = present and ''.join(value.split()) in compact
        if not present:
            errors.append(f'CAM first page missing [{entry["role"]}] '
                          f'{entry["source"]}:{entry["line"]}: {value[:100]}')
    return errors


def _bibliography_items(text):
    """Read actual bibitems, skipping preamble macro definitions and groups."""
    text = strip_comments(text)
    pos = 0
    while pos < len(text):
        if text[pos] == '{':
            _, pos = group(text, pos)
        elif text[pos] == '\\':
            name, pos = command_at(text, pos)
            if name != 'bibitem':
                continue
            pos = skip_space(text, pos)
            if pos < len(text) and text[pos] == '[':
                _, pos = group(text, pos, '[', ']')
            key, pos = group(text, skip_space(text, pos))
            start = pos
            while pos < len(text):
                if text[pos] == '{':
                    _, pos = group(text, pos)
                elif text[pos] == '\\':
                    token_start = pos
                    name, pos = command_at(text, pos)
                    if name == 'endbibitem':
                        yield key, text[start:token_start]
                        break
                    if name == 'bibitem':
                        raise ValueError(f'Missing endbibitem for bibliography entry {key}')
                else:
                    pos += 1
            else:
                raise ValueError(f'Missing endbibitem for bibliography entry {key}')
        else:
            pos += 1


def _page_literal(text):
    """Only literal letters/digits and balanced grouping are supported here."""
    parts, pos = [], 0
    while pos < len(text):
        if text[pos] == '{':
            value, pos = group(text, pos)
            parts.append(_page_literal(value))
        elif text[pos].isspace():
            pos += 1
        elif text[pos].isascii() and text[pos].isalnum():
            parts.append(text[pos])
            pos += 1
        else:
            raise ValueError(f'Unsupported canonical bibliography page syntax: {text!r}')
    value = ''.join(parts)
    if not value:
        raise ValueError('Empty canonical bibliography page value')
    return value


def _page_fields(text, offset=0):
    pos = 0
    while pos < len(text):
        if text[pos] == '{':
            start = pos
            value, pos = group(text, pos)
            yield from _page_fields(value, offset + start + 1)
        elif text[pos] == '\\':
            start = pos
            name, pos = command_at(text, pos)
            if name in ('bfpage', 'blpage'):
                value, pos = group(text, skip_space(text, pos))
                yield name, _page_literal(value), offset + start, offset + pos
        else:
            pos += 1


def bibliography_page_expectations(bbl):
    """Derive bounded alphanumeric page/range obligations from fresh .bbl.

    Supports literal bfpage/blpage fields and Springer's literal ``pp.`` notes
    (the current botherref representation). Numeric-only pages add no claim.
    This is a prefix-preservation regression, not a complete PDF bibliography
    validator; the existing site checks retain complete per-entry validation.
    """
    expected = []
    for key, body in _bibliography_items(Path(bbl).read_text()):
        fields = list(_page_fields(body))
        if fields:
            names = [field[0] for field in fields]
            if names not in (['bfpage'], ['bfpage', 'blpage']):
                raise ValueError(f'Ambiguous canonical bibliography page fields for {key}')
            first = fields[0][1]
            last = fields[1][1] if len(fields) == 2 else None
            if any(char.isalpha() for char in first + (last or '')):
                if last and not re.fullmatch(r'\s*--\s*', body[fields[0][3]:fields[1][2]]):
                    raise ValueError(f'Unsupported canonical bibliography page range separator for {key}')
                expected.append({'key': key, 'first': first, 'last': last})
        # A literal pp. marker is deliberately required; arbitrary identifiers,
        # title numbers, years and numeric pages are outside this regression.
        pattern = r'(?<![A-Za-z0-9])pp\.\s+([A-Za-z0-9]+)(?:\s*--\s*([A-Za-z0-9]+))?(?![A-Za-z0-9])'
        for match in re.finditer(pattern, body):
            first, last = match.groups()
            if any(char.isalpha() for char in first + (last or '')):
                expected.append({'key': key, 'first': first, 'last': last})
    return expected


def validate_bibliography_pages(bbl, pdf_text):
    """Require complete source-derived alphanumeric ranges in the whole PDF."""
    # Preserve case, letters, digits and token boundaries. Only compatibility
    # typography, whitespace and dash glyphs are normalized; D1 cannot match D10.
    text = unicodedata.normalize('NFKC', pdf_text)
    text = re.sub('[‐‑‒–—−]', '-', text)
    text = re.sub(r'-{2,}', '-', text)
    text = ' '.join(text.split())
    errors = []
    for entry in bibliography_page_expectations(bbl):
        pattern = re.escape(entry['first'])
        display = entry['first']
        if entry['last'] is not None:
            pattern += r'\s*-\s*' + re.escape(entry['last'])
            display += '–' + entry['last']
        pattern = r'(?<![A-Za-z0-9])' + pattern + r'(?![A-Za-z0-9])'
        if not re.search(pattern, text):
            errors.append(f'PDF bibliography pagination missing [{entry["key"]}]: {display}')
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manuscript', type=Path, default=ROOT / 'manuscript/manuscript.tex')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--pdf', type=Path, help='canonical PDF (defaults beside manuscript)')
    group.add_argument('--text', type=Path, help='extracted text (whole PDF required with --bbl)')
    parser.add_argument('--bbl', type=Path, help='fresh canonical bibliography for alphanumeric PDF pagination checks')
    parser.add_argument('--text-output', type=Path, help='retain extracted first-page evidence')
    args = parser.parse_args(argv)
    try:
        if args.text:
            text = args.text.read_text()
        else:
            extraction = ['pdftotext'] + ([] if args.bbl else ['-f', '1', '-l', '1'])
            result = subprocess.run([*extraction, str(args.pdf or args.manuscript.with_suffix('.pdf')), '-'],
                                    check=True, capture_output=True, text=True)
            text = result.stdout
        if args.text_output:
            args.text_output.write_text(text.split('\f', 1)[0])
        errors = validate_titlepage(args.manuscript, text)
        if args.bbl:
            errors.extend(validate_bibliography_pages(args.bbl, text))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        errors = [str(exc)]
    for error in errors:
        print('error: ' + error, file=sys.stderr)
    if not errors:
        print('CAM first-page source content verified' +
              ('; PDF bibliography pagination verified' if args.bbl else ''))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
