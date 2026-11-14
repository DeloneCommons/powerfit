"""Small TeX lexical primitives; no macro expansion or environment semantics.

Callers remove comments before reading commands/groups. All returned offsets are
exclusive indices into the supplied string. Control symbols consume one escaped
character, so braces after an even number of backslashes remain delimiters.
"""
import re


def command_at(text, pos):
    """Return (control-sequence name, end) at a literal backslash."""
    if pos >= len(text) or text[pos] != '\\' or pos + 1 >= len(text):
        raise ValueError('Expected TeX command')
    match = re.match(r'[A-Za-z]+|[^\n]', text[pos + 1:])
    if not match:
        raise ValueError('Expected TeX command')
    return match.group(), pos + 1 + len(match.group())


def skip_space(text, pos):
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def strip_comments(text):
    """Remove unescaped percent comments while retaining line boundaries."""
    kept, pos = [], 0
    while pos < len(text):
        if text[pos] == '\\' and pos + 1 < len(text) and text[pos + 1] != '\n':
            _, end = command_at(text, pos)
            kept.append(text[pos:end])
            pos = end
        elif text[pos] == '%':
            end = text.find('\n', pos)
            pos = len(text) if end == -1 else end
        else:
            kept.append(text[pos])
            pos += 1
    return ''.join(kept)


def group(text, pos, opener='{', closer='}'):
    """Read a balanced group, protecting escaped delimiters and braced options."""
    if pos >= len(text) or text[pos] != opener:
        raise ValueError(f'Expected TeX {opener} argument')
    start, depth = pos + 1, 1
    pos += 1
    while pos < len(text):
        char = text[pos]
        if char == '\\':
            _, pos = command_at(text, pos)
            continue
        if opener == '[' and char == '{':
            _, pos = group(text, pos)
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if not depth:
                return text[start:pos], pos + 1
        pos += 1
    raise ValueError(f'Unbalanced TeX {opener}{closer} argument')
