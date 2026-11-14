"""Review finite LaTeXML warning roles against independently read source spans.

Approvals are deliberately inert data: this module never creates or refreshes
an approval. Coordinates aid attribution/reporting but never authorize a warning.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from texsyntax import command_at, group, skip_space, strip_comments


_LAYOUT = {',', ';', ':', '!', 'quad', 'qquad', 'enspace', 'thinspace',
           'medspace', 'thickspace', 'displaystyle', 'textstyle', 'scriptstyle',
           'scriptscriptstyle', 'allowbreak'}
_TEXT = {'text', 'textrm', 'textnormal', 'textup', 'textit', 'textbf', 'mbox', 'operatorname'}
_HEADER = re.compile(r'^(Warning|Error|Fatal):([^\s]+)\s+(.+)$')
_LOCATION = re.compile(r'^at (.+?); line (\d+) col (\d+)(?: - line (\d+) col (\d+))?$')
_RULE = re.compile(r"^MathParser failed to match rule '([^']+)'$")


def _tokens(text):
    """Lexical identity, preserving commands, grouping and math-text spaces."""
    text = strip_comments(text)
    tokens, pos = [], 0
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
        elif text[pos] == '\\':
            name, end = command_at(text, pos)
            if name == 'label':
                _, pos = group(text, skip_space(text, end))
            elif name in _LAYOUT:
                pos = end
            elif name in _TEXT:
                if name == 'operatorname' and end < len(text) and text[end] == '*':
                    name += '*'
                    end += 1
                content, pos = group(text, skip_space(text, end))
                # Text spaces matter; ordinary reflow of existing spaces does not.
                tokens.extend(['\\' + name, '{', re.sub(r'\s+', ' ', content), '}'])
            else:
                tokens.append('\\' + name)
                pos = end
        else:
            tokens.append(text[pos])
            pos += 1
    return tokens


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def expression_fingerprint(tex, environment):
    """Full authored expression identity; no operand/role equivalence guessing."""
    return _digest([environment, _tokens(tex)])


def diagnostic_fingerprint(text):
    """Complete In/token-trace identity insensitive to diagnostic line wrapping."""
    return _digest(_tokens(text))


def _summary(text, path, count):
    summaries = re.findall(r'^Conversion complete: (.+)$', text, re.M)
    if len(summaries) != 1:
        raise RuntimeError(f'Missing or ambiguous conversion completion summary in {path}')
    if re.search(r'\b[1-9]\d* (?:errors?|undefined (?:macros?|commands?)|missing files?)\b', text, re.I):
        raise RuntimeError(f'Errors, undefined commands or missing files in {path}')
    match = re.match(r'(\d+) warnings?\b', summaries[0])
    if match:
        declared = int(match[1])
    elif summaries[0].startswith('No obvious problems'):
        declared = 0
    else:
        raise RuntimeError(f'Unknown completion summary in {path}: {summaries[0]}')
    if declared != count:
        raise RuntimeError(f'Diagnostic count discrepancy in {path}: summary {declared}, parsed {count}')


def _headers(text, path):
    result = []
    for number, line in enumerate(text.splitlines()):
        if re.match(r'^\s*(?:Warning|Error|Fatal)\b', line):
            match = _HEADER.fullmatch(line.strip())
            if not match:
                raise RuntimeError(f'Unparsed diagnostic header in {path}:{number+1}: {line}')
            severity, signature, rest = match.groups()
            if severity != 'Warning' or not signature.startswith('not_parsed:'):
                raise RuntimeError(f'Unreviewable converter diagnostic in {path}: {line}')
            result.append((number, signature, rest))
    return result


def _location(value):
    match = _LOCATION.fullmatch(value)
    if not match:
        raise RuntimeError(f'Unparsed diagnostic source location: {value}')
    filename, line, column, end_line, end_column = match.groups()
    return {'file': filename, 'line': int(line), 'column': int(column),
            'end_line': int(end_line or line), 'end_column': int(end_column or column)}


def _location_kind(location):
    return 'none' if location is None else 'string' if location['file'] == 'String' and location['line'] == 0 else 'source'


def _console_key(signature, message, location):
    return (signature, message, None if location is None else
            (Path(location['file']).name, location['line'], location['column']))


def parse_conversion_logs(console_path, rich_path):
    """Parse the pinned full-block format and reconcile independent log views."""
    console_path, rich_path = Path(console_path), Path(rich_path)
    console, rich = console_path.read_text(), rich_path.read_text()
    console_keys = []
    for _, signature, rest in _headers(console, console_path):
        match = re.fullmatch(r"(MathParser failed to match rule '[^']+')(?: (at .+))?", rest)
        if not match:
            raise RuntimeError(f'Unknown console parser diagnostic: {rest}')
        message, location = match.groups()
        console_keys.append(_console_key(signature, message, _location(location) if location else None))
    lines, blocks = rich.splitlines(), []
    for start, signature, message in _headers(rich, rich_path):
        rule = _RULE.fullmatch(message)
        if not rule:
            raise RuntimeError(f'Unknown rich-log parser rule: {message}')
        end = start + 1
        while end < len(lines) and (lines[end].startswith('\t') or not lines[end].strip()):
            end += 1
        body = '\n'.join(line.removeprefix('\t') for line in lines[start+1:end]).strip()
        location = None
        if body.startswith('at '):
            first, _, body = body.partition('\n')
            location = _location(first)
        match = re.fullmatch(r'In "(.*?)"\n(.+)', body, re.S)
        if not match:
            raise RuntimeError(f'Incomplete rich diagnostic block in {rich_path}:{start+1}')
        in_tex, trace = match.groups()
        if not re.search(r'>\s*\S.*\[\[[A-Z]+\]\]', trace, re.S) or trace.count('[[') != trace.count(']]'):
            raise RuntimeError(f'Incomplete token trace in {rich_path}:{start+1}')
        blocks.append({'signature': signature, 'rule': rule[1], 'message': message,
                       'location': location, 'in': in_tex, 'trace': trace,
                       'raw': '\n'.join(lines[start:end]), 'log_line': start+1})
    rich_keys = [_console_key(b['signature'], b['message'], b['location']) for b in blocks]
    if Counter(console_keys) != Counter(rich_keys):
        raise RuntimeError('Console/rich diagnostic reconciliation failed')
    _summary(console, console_path, len(console_keys))
    _summary(rich, rich_path, len(blocks))
    return blocks


def _version(value):
    match = re.fullmatch(r'(?:latexml \(LaTeXML version )?(\d+\.\d+\.\d+)\)?', value.strip())
    if not match:
        raise RuntimeError(f'Unrecognized converter version: {value}')
    return match[1]


def binding_context(rich_path, names):
    """Hash relevant installed bindings/core, resolving paths from this run's log."""
    text = Path(rich_path).read_text()
    loaded = re.findall(r'\(Loading ([^\n]+?)\.\.\.', text)
    paths = {}
    for name in names:
        matches = {Path(p) for p in loaded if Path(p).name == name}
        if name.endswith('.pm'):
            for p in loaded:
                path = Path(p)
                if path.parent.name == 'Package' and path.parent.parent.name == 'LaTeXML':
                    candidate = path.parent.parent / name
                    if candidate.is_file():
                        matches.add(candidate)
        if len(matches) != 1:
            raise RuntimeError(f'Unknown or ambiguous relevant binding context: {name}')
        path = matches.pop()
        if not path.is_file():
            raise RuntimeError(f'Relevant binding file unavailable: {path}')
        paths[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return paths


def check_conversion_warnings(console_path, rich_path, inventory, version, approvals_path, report_path=None):
    """Apply reviewed finite source/role caps; emit evidence, never approvals."""
    policy = json.loads(Path(approvals_path).read_text())
    report = {'schema_version': 1, 'stage': 'conversion', 'converter_version': _version(version),
              'matched': [], 'unmatched': []}
    try:
        if policy.get('schema_version') != 1 or policy.get('stage') != 'conversion':
            raise RuntimeError('Unsupported warning approval schema/stage')
        if report['converter_version'] != policy['converter_version']:
            raise RuntimeError('Unreviewed LaTeXML converter version; warning review required')
        rich_text = Path(rich_path).read_text()
        if not rich_text.startswith(f"latexml (LaTeXML version {policy['converter_version']}) processing "):
            raise RuntimeError('Rich log converter version does not match reviewed converter')
        expected = {b['name']: b['sha256'] for b in policy['binding_context']}
        actual = binding_context(rich_path, expected)
        report['binding_context'] = actual
        if actual != expected:
            raise RuntimeError('Relevant LaTeXML binding context changed; review required')
        blocks = parse_conversion_logs(console_path, rich_path)
        report['diagnostics'] = blocks
        items = [m for m in inventory['math'] if m['mode'] != 'row']
        fingerprints = {m['id']: expression_fingerprint(m['tex'], m['environment']) for m in items}
        report['source_candidates'] = [dict(m, source_fingerprint=fingerprints[m['id']]) for m in items
                                       if m['mode'] == 'display']
        consumed = Counter()
        for block in blocks:
            candidates = []
            for record in policy['expressions']:
                for role_number, role in enumerate(record['roles']):
                    if (block['signature'] == role['signature'] and block['rule'] == role['rule']
                            and diagnostic_fingerprint(block['in']) == role['in_fingerprint']
                            and diagnostic_fingerprint(block['trace']) == role['trace_fingerprint']
                            and _location_kind(block['location']) == role['location']):
                        candidates.append((record, role_number, role))
            if len(candidates) != 1:
                raise RuntimeError(f'Unknown or ambiguous diagnostic role: {block["raw"]}')
            record, role_number, role = candidates[0]
            current = [m for m in items if fingerprints[m['id']] == record['source_fingerprint']]
            if len(current) != 1:
                raise RuntimeError(f'Reviewed source expression {record["id"]} is changed, missing or ambiguous; unique attribution required')
            item = current[0]
            if inventory.get('macro_context') != record['macro_context']:
                raise RuntimeError(f'Macro context changed for reviewed expression {record["id"]}')
            location = block['location']
            if role['location'] == 'source':
                containing = [m for m in items if Path(m['source']).name == Path(location['file']).name
                              and m['line'] <= location['line'] <= m['end_line']]
                if len(containing) != 1 or containing[0]['id'] != item['id']:
                    raise RuntimeError(f'Diagnostic source attribution mismatch for {record["id"]}: {location}')
            consumed[(record['id'], role_number)] += 1
            if consumed[(record['id'], role_number)] > role['max_occurrences']:
                raise RuntimeError(f'Warning occurrence cap exceeded for {record["id"]} role {role_number}')
            report['matched'].append({'expression': record['id'], 'role': role_number,
                                      'source': {k: item.get(k) for k in ('id', 'source', 'line', 'end_line', 'labels')},
                                      'source_fingerprint': fingerprints[item['id']],
                                      'diagnostic': block})
    except (RuntimeError, ValueError, KeyError) as error:
        report['unmatched'].append(str(error))
        if report_path:
            Path(report_path).write_text(json.dumps(report, indent=2) + '\n')
        raise RuntimeError(f'Conversion warning review failed: {error}') from error
    if report_path:
        Path(report_path).write_text(json.dumps(report, indent=2) + '\n')
    return report
