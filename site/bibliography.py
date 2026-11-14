"""Validate rendered DOI links independently against the authoritative BibTeX."""
import re
from urllib.parse import unquote, urlsplit


def source_dois(path):
    """Read literal DOI fields in refs.bib, failing closed on unsupported forms.

    This is deliberately not a general BibTeX interpreter. Entries must start on
    their own lines; DOI values may be braced or quoted literals (not macros or
    concatenations). Other fields remain the responsibility of canonical BibTeX.
    """
    source = path.read_text()
    starts = list(re.finditer(r'^@\w+\s*\{\s*([^,\s]+)\s*,', source, re.M))
    records = {}
    for i, entry in enumerate(starts):
        key = entry[1].lower()  # Normalize comparison keys, never source bytes.
        if key in records:
            raise ValueError(f'Duplicate bibliography key: {key}')
        block = source[entry.end():starts[i + 1].start() if i + 1 < len(starts) else len(source)]
        fields = re.findall(r'^\s*doi\s*=\s*(.*?)\s*$', block, re.I | re.M)
        doi = None
        if fields:
            literal = re.fullmatch(r'(?:\{([^{}]+)\}|"([^"]+)")\s*,?', fields[0])
            if len(fields) != 1 or not literal:
                raise ValueError(f'Unsupported DOI metadata for {key}: expected one literal field')
            doi = literal[1] or literal[2]
            parse_doi_url('https://doi.org/' + doi)
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
