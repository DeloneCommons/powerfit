"""Independent fresh Springer auxiliary, recorder and formatted bibliography evidence.

This is a bounded reader, not a TeX interpreter. Bibliography macro definitions
are skipped only before the explicit Springer PreBibitemsHook delimiter. Item
bodies accept a finite list of transparent formatting wrappers and text escapes;
unknown commands raise an actionable error instead of deleting content.
"""
import hashlib
from pathlib import Path
import re
import unicodedata

from texsyntax import command_at, group, skip_space, strip_comments

NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'


def read_aux(path):
    """Read balanced newlabel records, rejecting duplicates and malformed fields."""
    text, pos, labels = strip_comments(Path(path).read_text()), 0, {}
    try:
        while pos < len(text):
            if text[pos] == '{':
                _, pos = group(text, pos)
            elif text[pos] == '\\':
                name, pos = command_at(text, pos)
                if name != 'newlabel':
                    continue
                key, pos = group(text, skip_space(text, pos))
                value, pos = group(text, skip_space(text, pos))
                fields, inner = [], 0
                while skip_space(value, inner) < len(value):
                    field, inner = group(value, skip_space(value, inner))
                    fields.append(field)
                if key in labels:
                    raise ValueError(f'duplicate {key}')
                if not key or len(fields) not in (2, 5):
                    raise ValueError(f'unsupported newlabel fields for {key}')
                labels[key] = dict(zip(('number', 'page', 'title', 'destination'),
                                       fields[:4] if len(fields) == 5 else fields + ['', '']))
            else:
                pos += 1
    except ValueError as exc:
        raise ValueError(f'Invalid canonical labels: {exc}') from exc
    return labels


def visible_text(node):
    """Visible text shared by canonical and authored-content comparisons."""
    def parts(element):
        tag = element.tag.rsplit('}', 1)[-1] if isinstance(element.tag, str) else ''
        style = re.sub(r'\s+', '', element.get('style', '')).lower()
        if (tag in ('annotation', 'annotation-xml', 'script', 'style') or
                'hidden' in element.attrib or element.get('aria-hidden') == 'true' or
                'display:none' in style or 'visibility:hidden' in style):
            return ''
        value = element.text or ''
        for child in element:
            value += parts(child) + (child.tail or '')
        return value
    return _normalize(parts(node))


def _normalize(value):
    return ' '.join(unicodedata.normalize('NFC', value).split())


def validate_labels(source_labels, aux_labels, xml, page=None):
    """Match source membership and canonical numbering, never global totals."""
    errors, expected = [], list(source_labels)
    page_ids = {}
    if page is not None:
        for node in page.xpath('//*[@id]'):
            page_ids.setdefault(node.get('id'), []).append(node)
    if len(expected) != len(set(expected)):
        errors.append('Duplicate source labels in canonical comparison')
    expected = set(expected)
    if set(aux_labels) != expected:
        errors.append('Canonical labels differ from source labels: missing=' +
                      repr(sorted(expected - aux_labels.keys())) + ' unexpected=' +
                      repr(sorted(aux_labels.keys() - expected)))
    converted = {}
    for node in xml.xpath('//*[@labels]'):
        for value in node.get('labels').split():
            if value.startswith('LABEL:'):
                converted.setdefault(value[6:], []).append(node)
    if set(converted) != expected:
        errors.append('XML source label membership differs: missing=' +
                      repr(sorted(expected - converted.keys())) + ' unexpected=' +
                      repr(sorted(converted.keys() - expected)))
    for label in sorted(expected & aux_labels.keys() & converted.keys()):
        nodes = converted[label]
        if len(nodes) != 1:
            errors.append(f'Missing or duplicate XML source label: {label}')
            continue
        numbers = nodes[0].xpath('./l:tags/l:tag[@role="refnum"]', namespaces=NS)
        actual = [visible_text(node) for node in numbers]
        if actual != [aux_labels[label]['number']]:
            errors.append(f'Canonical numbering mismatch: {label}: {actual} != {aux_labels[label]["number"]}')
        if page is not None:
            anchors = page_ids.get(label, [])
            if len(anchors) != 1:
                errors.append(f'Missing or duplicate named source anchor: {label}')
                continue
            targets = page_ids.get(nodes[0].get(XID), [])
            if len(targets) != 1:
                errors.append(f'Missing named source anchor destination: {label}')
                continue
            target = targets[0]
            tables = target.xpath('ancestor-or-self::table')
            if tables:
                target = tables[0]
            if 'wide-block' in target.getparent().get('class', '').split():
                target = target.getparent()
            following = anchors[0].getnext()
            while following is not None and 'source-anchor' in following.get('class', '').split():
                following = following.getnext()
            if following is not target:
                errors.append(f'Incorrect named source anchor location: {label}')
    return errors


def validate_reference_text(aux_labels, xml, page):
    """Literal ref/eqref display values come from the fresh canonical aux."""
    destinations = {value[6:]: node.get(XID) for node in xml.xpath('//*[@labels]')
                    for value in node.get('labels').split() if value.startswith('LABEL:')}
    expected = []
    for ref in xml.xpath('//l:ref[@labelref and not(ancestor::l:toccaption)]', namespaces=NS):
        label = ref.get('labelref').removeprefix('LABEL:')
        if label not in aux_labels or label not in destinations:
            return [f'Canonical reference text has unresolved source target: {label}']
        expected.append(('#' + destinations[label], aux_labels[label]['number']))
    actual = [(node.get('href'), visible_text(node)) for node in page.xpath(
        '//article//a[starts-with(@href,"#") and '
        'contains(concat(" ",@class," ")," ltx_ref ") and not(ancestor::cite)]')]
    return [] if actual == expected else ['Canonical reference text/destination mismatch']


def read_natbib(path):
    """Read canonical four-field natbib bibcite author/year records.

    Supported years are four ASCII digits and an optional lowercase suffix.
    Author text uses the same finite text/escape grammar as the Springer bbl.
    Numeric citations, arbitrary year macros and malformed records fail closed;
    the full-author field is decoded but starred citation commands are unsupported.
    """
    text, pos, labels = strip_comments(Path(path).read_text()), 0, {}
    try:
        while pos < len(text):
            if text[pos] == '{':
                _, pos = group(text, pos)
            elif text[pos] == '\\':
                name, pos = command_at(text, pos)
                if name != 'bibcite':
                    continue
                key, pos = group(text, skip_space(text, pos))
                value, pos = group(text, skip_space(text, pos))
                fields, inner = [], 0
                while skip_space(value, inner) < len(value):
                    field, inner = group(value, skip_space(value, inner))
                    fields.append(field)
                if not key or key in labels:
                    raise ValueError(f'empty or duplicate bibcite key: {key}')
                if (len(fields) != 4 or not re.fullmatch(r'[1-9][0-9]*', fields[0]) or
                        not re.fullmatch(r'[0-9]{4}[a-z]?', fields[1])):
                    raise ValueError(f'unsupported natbib fields for {key}')
                author = _normalize(_bibtext(fields[2]))
                _bibtext(fields[3])  # Do not silently discard unknown full-author syntax.
                if not author:
                    raise ValueError(f'empty natbib author for {key}')
                labels[key] = {'author': author, 'year': fields[1]}
            else:
                pos += 1
    except ValueError as exc:
        raise ValueError(f'Invalid canonical citation metadata: {exc}') from exc
    return labels


def _citation_tokens(value):
    value = unicodedata.normalize('NFKC', value)
    value = value.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"'}))
    return re.findall(r'\w+|[^\w\s]', value)


def _citation_display(source, labels):
    """Bounded author/year notation from aux labels and independent source notes.

    citep and citet retain source key order. Adjacent identical short authors
    share a group; adjacent identical base years show suffix-only subsequent
    years. Literal pre/post notes are outside citep groups and inside each citet
    group's parentheses. This is not a configurable natbib style interpreter.
    """
    command, keys, pre, post = source
    if command not in ('citep', 'citet') or not keys or len(keys) != len(set(keys)):
        raise ValueError('expected citep/citet with a nonempty, nonduplicate key group')
    if any(token in ('\\', '{', '}', '$', '^') for token in (*pre, *post)):
        raise ValueError('citation notes must be literal text, without TeX commands or mathematics')
    groups, linked_years = [], []
    for key in keys:
        if key not in labels:
            raise ValueError(f'missing canonical author/year for {key}')
        author, year = labels[key]['author'], labels[key]['year']
        if not groups or groups[-1]['author'] != author:
            groups.append({'author': author, 'years': [], 'previous': None})
        current = groups[-1]
        previous = current['previous']
        display_year = year
        if previous and previous[:4] == year[:4]:
            if len(previous) != 5 or len(year) != 5 or previous == year:
                raise ValueError(f'ambiguous repeated author/year for {key}')
            display_year = year[4:]
        current['previous'] = year
        current['years'].append(display_year)
        linked_years.append(display_year)
    body = []
    for current in groups:
        if body:
            body.append(';')
        body.extend(_citation_tokens(current['author']))
        body.extend([','] if command == 'citep' else ['(', *pre])
        body.extend(_citation_tokens(', '.join(current['years'])))
        if command == 'citet':
            body.extend([',', *post] if post else [])
            body.append(')')
    if command == 'citep':
        body = ['(', *pre, *body, *([',', *post] if post else []), ')']
    return body, linked_years


def validate_citation_display(citations, labels, xml, page, stage):
    """Check visible author/year, notes and linked years against source + aux.

    Converter bibliography IDs supply only link identities, never expected
    authors, years, punctuation or notes. Existing bbl validation separately
    verifies those IDs' complete bibliography content and source membership.
    """
    errors, destinations = [], {}
    for node in xml.xpath('//l:bibitem', namespaces=NS):
        destinations.setdefault(node.get('key'), []).append('#' + node.get(XID, ''))
    nodes = page.xpath('//article//cite')
    category = f'Canonical citation display mismatch ({stage})'
    if len(nodes) != len(citations):
        errors.append(f'{category}: expected {len(citations)} source groups, found {len(nodes)}')
    for index, (source, node) in enumerate(zip(citations, nodes), 1):
        command, keys, _, _ = source
        try:
            expected, years = _citation_display(source, labels)
        except ValueError as exc:
            errors.append(f'Unsupported canonical citation display ({stage}): group {index}: {exc}')
            continue
        links = node.xpath('.//a[@href]')
        targets = [destinations.get(key, []) for key in keys]
        if (any(len(target) != 1 for target in targets) or
                [link.get('href') for link in links] != [target[0] for target in targets if target] or
                [visible_text(link) for link in links] != years or
                _citation_tokens(visible_text(node)) != expected or
                'ltx_citemacro_' + command not in node.get('class', '').split()):
            errors.append(f'{category}: group {index}, keys {", ".join(keys)}')
    return errors


SYSTEM_ROOTS = tuple(Path(value) for value in (
    '/usr/share/texlive', '/usr/share/texmf', '/usr/local/texlive',
    '/var/lib/texmf', '/etc/texmf',
))
GENERATED_INPUTS = {'manuscript.' + ext for ext in ('aux', 'bbl', 'out', 'toc', 'lof', 'lot')}
UNICODE_INPUT = 'tex-support/glyphtounicode-cmr.tex'


def validate_recorder(path, manuscript, sources):
    """Cross-check file consumption and hashes, relocating recorded PWD safely.

    Sources are inventory records with relative path, sha256, and authored or
    publisher-unicode role. Recorder repeats are normal and do not imply repeated
    authored inclusion. Only the explicit Unicode support file has that role.
    """
    errors, expected, seen = [], {}, set()
    manuscript = Path(manuscript).resolve()
    lines = Path(path).read_text().splitlines()
    directories = [line[4:] for line in lines if line.startswith('PWD ')]
    if len(set(directories)) != 1 or not directories or not Path(directories[0]).is_absolute():
        return ['Invalid canonical recorder: expected one absolute PWD']
    recorded_root = Path(directories[0])
    for item in sources:
        name = item['path']
        local = manuscript / name
        if Path(name).is_absolute() or not local.resolve().is_relative_to(manuscript):
            errors.append(f'Invalid canonical recorder source path: {name}')
            continue
        if item.get('role') not in ('authored', 'publisher-unicode'):
            errors.append(f'Invalid canonical recorder source role: {name}')
            continue
        if (item.get('role') == 'publisher-unicode') != (name == UNICODE_INPUT):
            errors.append(f'Invalid canonical recorder Unicode role: {name}')
        expected[name] = item
        if not local.is_file() or local.is_symlink():
            errors.append(f'Canonical source missing or symbolic: {name}')
        elif hashlib.sha256(local.read_bytes()).hexdigest() != item['sha256']:
            errors.append(f'Canonical source hash mismatch: {name}')
    for line in lines:
        if not line.startswith('INPUT '):
            continue
        value = Path(line[6:])
        absolute = value if value.is_absolute() else recorded_root / value
        # resolve(strict=False) normalizes dot components even after artifact
        # relocation; the recorded original working directory need not exist.
        absolute = absolute.resolve()
        if not absolute.is_relative_to(recorded_root):
            if any(absolute.is_relative_to(root) for root in SYSTEM_ROOTS):
                continue
            if absolute.suffix == '.tex':
                errors.append(f'Canonical recorder unexpected external input: {value}')
            continue
        relative = absolute.relative_to(recorded_root).as_posix()
        if relative in expected:
            seen.add(relative)
        elif relative in GENERATED_INPUTS:
            continue
        elif relative == 'sn-jnl.cls' or absolute.suffix == '.pdf':
            # Publisher class and graphics have separate provenance/asset checks.
            continue
        else:
            errors.append(f'Canonical recorder unexpected local input: {relative}')
    for name in sorted(expected.keys() - seen):
        errors.append(f'Canonical source not consumed by recorder: {name}')
    return errors


WRAPPERS = frozenset('''bauthor oauthor bsnm binits bsuffix bparticle batitle bjtitle
bvolume byear bissue bfpage blpage burl binstitute binstitutionaled bctitle beditor
bpublisher bbtitle bedition bseriesno blocation bsertitle bconfdate bconflocation
bcomment textbf textit textsf textrm texttt emph mbox'''.split())
ENVIRONMENTS = frozenset(('barticle', 'bbook', 'bchapter', 'botherref'))
ACCENTS = {'"': '\u0308', "'": '\u0301', '`': '\u0300', '^': '\u0302',
           '~': '\u0303', '=': '\u0304', '.': '\u0307', 'c': '\u0327',
           'v': '\u030c', 'u': '\u0306', 'H': '\u030b', 'r': '\u030a'}
LETTERS = {'ae': 'æ', 'AE': 'Æ', 'oe': 'œ', 'OE': 'Œ', 'aa': 'å', 'AA': 'Å',
           'o': 'ø', 'O': 'Ø', 'ss': 'ß', 'l': 'ł', 'L': 'Ł', 'i': 'ı', 'j': 'ȷ'}


def _bibtext(text):
    out, pos, environments = [], 0, []
    while pos < len(text):
        char = text[pos]
        if char == '{':
            value, pos = group(text, pos)
            out.append(_bibtext(value))
        elif char == '\\':
            name, pos = command_at(text, pos)
            if name in WRAPPERS or name in ('doiurl', 'url', 'href', 'bisbn'):
                value, pos = group(text, skip_space(text, pos))
                if name in ('doiurl', 'url'):
                    # URL typography does not apply TeX dash/quote ligatures.
                    if re.search(r'\\(?![%_&#${}])', value):
                        raise ValueError('unsupported URL command')
                    value = re.sub(r'\\([%_&#${}])', r'\1', value)
                    out.append(('https://doi.org/' if name == 'doiurl' else '') + value)
                elif name == 'href':
                    label, pos = group(text, skip_space(text, pos))
                    out.append(_bibtext(label))
                else:
                    out.append(('ISBN ' if name == 'bisbn' else '') + _bibtext(value))
            elif name in ('begin', 'end'):
                value, pos = group(text, skip_space(text, pos))
                if value not in ENVIRONMENTS:
                    raise ValueError(f'unsupported bibliography environment {value}')
                if name == 'begin':
                    environments.append(value)
                elif not environments or environments.pop() != value:
                    raise ValueError('unbalanced bibliography environment')
            elif name in ACCENTS:
                pos = skip_space(text, pos)
                if pos < len(text) and text[pos] == '{':
                    value, pos = group(text, pos)
                    value = _bibtext(value)
                elif pos < len(text):
                    value, pos = text[pos], pos + 1
                else:
                    raise ValueError('missing accent argument')
                if len(value) != 1:
                    raise ValueError('unsupported accent argument')
                out.append(unicodedata.normalize('NFC', value + ACCENTS[name]))
            elif name in LETTERS:
                out.append(LETTERS[name])
            elif name in '%_&#${}':
                out.append(name)
            elif name in (' ', ',', ';', ':', 'quad', 'qquad', 'newblock'):
                out.append(' ')
            elif name == 'betal':
                out.append('et al.')
            elif name in ('protect', 'relax'):
                pass
            else:
                raise ValueError(f'unsupported item command \\{name}')
        elif char in '}$^':
            raise ValueError(f'unsupported bibliography text syntax {char}')
        else:
            end = pos + 1
            while end < len(text) and text[end] not in '{}\\$^':
                end += 1
            out.append(text[pos:end].replace('---', '—').replace('--', '–').replace('``', '“').replace("''", '”').replace('~', ' '))
            pos = end
    if environments:
        raise ValueError('unclosed bibliography environment')
    return ''.join(out)


def canonical_bibliography(path):
    """Return ordered canonical keys and complete formatted visible item text."""
    text = strip_comments(Path(path).read_text())
    hook = r'\csname PreBibitemsHook\endcsname'
    try:
        if text.count(hook) != 1:
            raise ValueError('expected Springer PreBibitemsHook delimiter')
        prefix, text = text.split(hook)
        if not re.search(r'\\begin\s*\{thebibliography\}\s*\{[^{}]+\}', prefix):
            raise ValueError('missing thebibliography environment')
        pos, entries, keys = 0, [], set()
        while True:
            pos = skip_space(text, pos)
            name, pos = command_at(text, pos)
            if name == 'end':
                value, pos = group(text, skip_space(text, pos))
                if value != 'thebibliography' or text[pos:].strip():
                    raise ValueError('unexpected bibliography trailer')
                return entries
            if name != 'bibitem':
                raise ValueError('expected bibitem')
            pos = skip_space(text, pos)
            if pos < len(text) and text[pos] == '[':
                _, pos = group(text, pos, '[', ']')
            key, pos = group(text, skip_space(text, pos))
            if not key or key in keys:
                raise ValueError(f'empty or duplicate bibliography key: {key}')
            keys.add(key)
            start, scan = pos, pos
            while scan < len(text):
                if text[scan] == '{':
                    _, scan = group(text, scan)
                elif text[scan] == '\\':
                    token_start = scan
                    token, scan = command_at(text, scan)
                    if token == 'endbibitem':
                        content = _normalize(_bibtext(text[start:token_start]))
                        if not content:
                            raise ValueError(f'empty bibliography item: {key}')
                        entries.append({'key': key, 'text': content})
                        pos = scan
                        break
                    if token == 'bibitem':
                        raise ValueError(f'missing endbibitem for {key}')
                else:
                    scan += 1
            else:
                raise ValueError(f'missing endbibitem for {key}')
    except ValueError as exc:
        raise ValueError(f'Invalid canonical bibliography: {exc}') from exc


def validate_canonical_bibliography(bbl, xml, page):
    """Compare identities/order/multiplicity and full content in XML and HTML."""
    try:
        entries = canonical_bibliography(bbl)
    except (ValueError, OSError) as exc:
        return [str(exc)]
    errors = []
    nodes = xml.xpath('//l:bibitem', namespaces=NS)
    if [node.get('key') for node in nodes] != [entry['key'] for entry in entries]:
        errors.append('XML bibliography identities/order/multiplicity differ from canonical bibliography')
    by_key = {}
    for node in nodes:
        by_key.setdefault(node.get('key'), []).append(node)
    html_nodes = page.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," ltx_bibitem ")]')
    if [node.get('id') for node in html_nodes] != [node.get(XID) for node in nodes]:
        errors.append('HTML bibliography identities/order/multiplicity differ from XML bibliography')
    for entry in entries:
        candidates = by_key.get(entry['key'], [])
        if len(candidates) != 1:
            continue
        node = candidates[0]
        blocks = node.xpath('./l:bibblock', namespaces=NS)
        content = _normalize(' '.join(visible_text(block) for block in blocks))
        if content != entry['text']:
            errors.append(f'XML bibliography content differs from canonical bibliography: {entry["key"]}')
        targets = page.xpath('//*[@id=$identifier]', identifier=node.get(XID))
        if len(targets) != 1:
            errors.append(f'HTML bibliography missing or duplicate item: {entry["key"]}')
            continue
        blocks = targets[0].xpath('./*[contains(concat(" ",normalize-space(@class)," ")," ltx_bibblock ")]')
        content = _normalize(' '.join(visible_text(block) for block in blocks))
        if content != entry['text']:
            errors.append(f'HTML bibliography content differs from canonical bibliography: {entry["key"]}')
    return errors
