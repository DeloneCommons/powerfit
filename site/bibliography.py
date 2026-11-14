"""Validate rendered DOI links independently against the authoritative BibTeX."""
import re
from urllib.parse import unquote, urlsplit


def _entry_parts(source, start, closing):
    """Split only top-level commas; nested braces/quotes protect field values."""
    parts, buffer = [], []
    depth, quoted, i = 0, False, start
    while i < len(source):
        char = source[i]
        # Backslashes do not escape BibTeX's structural delimiters. TeX commands
        # are interpreted later; skipping "\}" here can hide a following field.
        if char == '%' and not depth and not quoted:
            end = source.find('\n', i)
            i = len(source) if end < 0 else end
            continue
        if char == closing and not depth and not quoted:
            return parts + [''.join(buffer).strip()], i + 1
        if char == '{':
            depth += 1
        elif char == '}':
            if not depth:
                raise ValueError('Unbalanced braces in bibliography entry')
            depth -= 1
        elif char == '"' and not depth:
            quoted = not quoted
        if char == ',' and not depth and not quoted:
            parts.append(''.join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
        i += 1
    raise ValueError('Unterminated bibliography entry or DOI expression')


def source_dois(path):
    """Read literal DOI fields independently of BibTeX line layout.

    This bounded scanner understands entry/field boundaries, braces, quotes
    and comments outside values. It does not expand BibTeX macros or
    concatenations: DOI expressions must be one braced or quoted literal.
    Other field expressions are left to canonical BibTeX.
    """
    source = path.read_text()
    records, i = {}, 0
    while i < len(source):
        if source[i] == '%':
            end = source.find('\n', i)
            i = len(source) if end < 0 else end + 1
            continue
        if source[i] != '@':
            i += 1
            continue
        entry = re.match(r'@(\w+)\s*([\{(])', source[i:])
        if not entry:
            raise ValueError('Unsupported bibliography entry syntax')
        parts, i = _entry_parts(source, i + entry.end(), '}' if entry[2] == '{' else ')')
        if entry[1].lower() in ('comment', 'preamble', 'string'):
            continue
        key = parts[0].lower()
        if not re.fullmatch(r'[^\s,={}()]+', key):
            raise ValueError('Missing or malformed bibliography key')
        if key in records:
            raise ValueError(f'Duplicate bibliography key: {key}')
        doi, seen_doi = None, False
        for part in parts[1:]:
            if not part:  # A trailing comma is permitted.
                continue
            field = re.fullmatch(r'([A-Za-z][\w-]*)\s*=\s*(.+)', part, re.S)
            if not field:
                raise ValueError(f'Malformed bibliography field in {key}: {part}')
            if field[1].lower() == 'crossref':
                raise ValueError(f'Unsupported BibTeX crossref inheritance in {key}')
            if field[1].lower() != 'doi':
                continue
            literal = re.fullmatch(r'(?:\{([^{}]+)\}|"([^"{}]+)")', field[2], re.S)
            if seen_doi or not literal:
                raise ValueError(f'Unsupported DOI metadata for {key}: expected one literal field')
            doi = (literal[1] or literal[2]).strip()
            parse_doi_url('https://doi.org/' + doi)
            seen_doi = True
        records[key] = doi
    if not records:
        raise ValueError('No authoritative bibliography entries found')
    return records


def is_doi_url(target):
    return urlsplit(target).hostname in ('doi.org', 'dx.doi.org')


def parse_doi_url(target):
    url = urlsplit(target)
    doi = unquote(url.path.removeprefix('/'))
    if (url.scheme != 'https' or url.netloc != 'doi.org' or url.query or url.fragment
            or re.search(r'\s|%(?![0-9a-fA-F]{2})', target)
            or not re.fullmatch(r'10\.\d{4,9}/[^\s<>\\{}"]+', doi)):
        raise ValueError(f'Malformed DOI URL: {target}')
    return doi


def validate_bibliography_dois(page, entries, metadata, xid):
    errors = []
    for entry in entries:
        key = entry.get('key').lower()
        nodes = page.xpath('//*[@id=$id]', id=entry.get(xid))
        if key not in metadata or len(nodes) != 1:
            errors.append(f'Missing DOI metadata or rendered bibliography entry: {key}')
            continue
        expected = metadata[key]
        links = [a for a in nodes[0].xpath('.//a[@href]') if is_doi_url(a.get('href'))]
        if len(links) != (1 if expected else 0):
            errors.append(f'DOI link inventory differs from refs.bib: {key}')
            continue
        for link in links:
            try:
                actual = parse_doi_url(link.get('href'))
                if actual.casefold() != expected.casefold():
                    errors.append(f'DOI differs from refs.bib: {key}: {actual} != {expected}')
                if ''.join(link.itertext()).strip() != link.get('href'):
                    errors.append(f'DOI display differs from its URL: {key}')
            except ValueError as exc:
                errors.append(str(exc))
    return errors
