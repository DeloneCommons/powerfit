"""Adapt a bounded Springer front matter; reject semantics we cannot preserve."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_manuscript import collect_dependencies  # noqa: E402
from texsyntax import command_at, group, skip_space, strip_comments  # noqa: E402

def read_tex(path):
    """Read wrapper input with TeX comment/EOL semantics, preserving word joins."""
    return strip_comments(Path(path).read_text(encoding='utf-8'))


FIELDS = ('title', 'author', 'email', 'affil', 'abstract', 'keywords', 'pacs')
# These packages are already represented by the article wrapper (or concern
# print layout). Options that could change mathematics are deliberately absent.
PACKAGES = {
    'fontenc': 'T1', 'inputenc': 'utf8', 'lmodern': None, 'xcolor': None,
    'amsmath': None, 'amssymb': None, 'mathtools': None, 'graphicx': None,
    'placeins': None, 'needspace': None, 'booktabs': None,
}


def _call(text, pos):
    """Read the supported star, single optional argument and required argument."""
    pos = skip_space(text, pos)
    star = pos < len(text) and text[pos] == '*'
    pos = skip_space(text, pos + int(star))
    option = None
    if pos < len(text) and text[pos] == '[':
        option, pos = group(text, pos, '[', ']')
    value, pos = group(text, skip_space(text, pos))
    return value, option, star, pos


def argument(text, command):
    """Read a balanced argument of an exact control-sequence token."""
    text, pos = strip_comments(text), 0
    while pos < len(text):
        if text[pos] == '\\':
            name, pos = command_at(text, pos)
            if name == command:
                return _call(text, pos)[0]
        else:
            pos += 1
    raise ValueError(f'Unsupported manuscript front matter: missing {command}')


def plain_metadata(value):
    """Flatten only the known naming/affiliation wrappers, never other macros."""
    value = re.sub(r'\\(?:fnm|sur|orgname|orgaddress|city|country)\b\s*', '', value)
    value = value.replace('{', '').replace('}', '')
    if '\\' in value or any(char in value for char in '$&#_^~'):
        raise ValueError('Unsupported command or TeX syntax in manuscript front matter')
    value = ' '.join(value.split())
    if not value:
        raise ValueError('Unsupported manuscript front matter: empty metadata')
    return value


def _hypersetup(value):
    """Only nonprinting PDF metadata and the existing hidelinks layout setting."""
    pos, keys = 0, set()
    while pos < len(value):
        pos = skip_space(value, pos)
        match = re.match(r'(hidelinks|pdftitle|pdfauthor)\b', value[pos:])
        if not match or match.group() in keys:
            raise ValueError('Unsupported manuscript preamble: hypersetup setting')
        key = match.group()
        keys.add(key)
        pos = skip_space(value, pos + len(key))
        if key != 'hidelinks':
            if pos >= len(value) or value[pos] != '=':
                raise ValueError('Unsupported manuscript preamble: PDF metadata')
            literal, pos = group(value, skip_space(value, pos + 1))
            plain_metadata(literal)
            pos = skip_space(value, pos)
        if pos == len(value):
            break
        if value[pos] != ',':
            raise ValueError('Unsupported manuscript preamble: hypersetup setting')
        pos += 1


def _preamble(text):
    pos, declarations, documentclass = 0, [], False
    while True:
        pos = skip_space(text, pos)
        if pos >= len(text):
            raise ValueError('Unsupported manuscript preamble: missing document environment')
        start = pos
        try:
            name, pos = command_at(text, pos)
            if name == 'pdfgentounicode':
                match = re.match(r'\s*=\s*1(?=\s|\\|$)', text[pos:])
                if not match:
                    raise ValueError('unsupported Unicode extraction setting')
                pos += match.end()
                continue
            if name == 'newtheorem':
                env, shared, star, pos = _call(text, pos)
                if not re.fullmatch(r'[A-Za-z]+', env) or shared is not None:
                    raise ValueError('unsupported theorem environment')
                next_pos = skip_space(text, pos)
                counter = None
                if next_pos < len(text) and text[next_pos] == '[':
                    counter, pos = group(text, next_pos, '[', ']')
                heading, pos = group(text, skip_space(text, pos))
                if not heading.strip():
                    raise ValueError('empty theorem heading')
                next_pos = skip_space(text, pos)
                within = None
                if next_pos < len(text) and text[next_pos] == '[':
                    within, pos = group(text, next_pos, '[', ']')
                if (star and (counter is not None or within is not None) or
                        counter is not None and within is not None or
                        any(not re.fullmatch(r'[A-Za-z]+', item)
                            for item in (counter, within) if item is not None)):
                    raise ValueError('unsupported theorem counter')
                declarations.append(text[start:pos])
                continue
            value, option, star, pos = _call(text, pos)
            if star:
                raise ValueError('unsupported starred command')
            if name == 'begin' and value == 'document' and option is None:
                if not documentclass:
                    raise ValueError('missing Springer documentclass')
                return pos, '\n'.join(declarations)
            if name == 'documentclass' and not documentclass:
                if value != 'sn-jnl' or option not in (None, 'pdflatex,sn-mathphys-ay'):
                    raise ValueError('unsupported publisher class or options')
                documentclass = True
            elif name == 'usepackage':
                packages = [item.strip() for item in value.split(',')]
                if any(item not in PACKAGES or PACKAGES[item] != option for item in packages):
                    raise ValueError('unsupported package or package options')
            elif name == 'hypersetup' and option is None:
                _hypersetup(value)
            elif name == 'input' and option is None and value == 'tex-support/glyphtounicode-cmr.tex':
                pass
            else:
                raise ValueError(f'unsupported command \\{name}')
        except ValueError as exc:
            raise ValueError(f'Unsupported manuscript preamble: {exc}') from exc


def _front_matter(text):
    """Consume every token that is replaced by the HTML wrapper."""
    text = strip_comments(text)
    pos, theorems = _preamble(text)
    fields, classification = {}, None
    while True:
        pos = skip_space(text, pos)
        try:
            name, pos = command_at(text, pos)
            if name == 'maketitle':
                break
            if name not in FIELDS:
                raise ValueError(f'unsupported command \\{name}')
            if name in fields:
                raise ValueError(f'expected one {name}, found duplicate')
            value, option, star, pos = _call(text, pos)
            if star and name not in ('author', 'affil'):
                raise ValueError(f'unsupported starred {name}')
            if name == 'pacs':
                if option is None or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 .()/-]*', option):
                    raise ValueError('classification: expected one explicit literal pacs label')
                classification = option
            elif name in ('author', 'affil'):
                if option not in (None, '1'):
                    raise ValueError(f'unsupported {name} index')
            elif name == 'title':
                if option is not None:
                    plain_metadata(option)
            elif option is not None:
                raise ValueError(f'unsupported {name} option')
            if not value.strip():
                raise ValueError(f'empty {name}')
            fields[name] = value
        except ValueError as exc:
            raise ValueError(f'Unsupported manuscript front matter: {exc}') from exc
    missing = set(FIELDS) - fields.keys()
    if missing:
        raise ValueError('Unsupported manuscript front matter: missing ' + ', '.join(sorted(missing)))
    # Publisher metadata commands after maketitle are outside this grammar;
    # leaving them to an article class would lose the very metadata we guard.
    scan = pos
    while scan < len(text):
        if text[scan] == '\\':
            name, scan = command_at(text, scan)
            if name in FIELDS or name == 'maketitle':
                raise ValueError(f'Unsupported manuscript front matter: unexpected {name} after maketitle')
        else:
            scan += 1
    return fields, classification, text[pos:], theorems


def source_metadata(text):
    fields, _, _, _ = _front_matter(text)
    return {key: plain_metadata(fields[command]) for key, command in
            [('title', 'title'), ('author', 'author'), ('email', 'email'), ('affiliation', 'affil')]}


def _title_layout(body):
    """Adapt only the exact opening CAM title-page acknowledgment layout."""
    opening = re.match(
        r'\s*(\\vspace\{-28pt\})\s*(\\noindent\\begin\{minipage\}\{\\linewidth\})'
        r'\s*(\\footnotesize)\b', body)
    if not opening:
        return body
    # Nested minipages are not part of the publisher title-page idiom.
    closing = re.search(r'\\(?:begin|end)\{minipage\}', body[opening.end():])
    if not closing or closing.group() != r'\end{minipage}':
        return body
    end_start = opening.end() + closing.start()
    end_end = opening.end() + closing.end()
    if not re.match(r'\s*\\clearpage\b', body[end_end:]):
        return body
    for start, end in reversed([opening.span(1), opening.span(2), opening.span(3),
                                (end_start, end_end)]):
        body = body[:start] + body[end:]
    return body


def make_wrapper(text):
    """Generate an article-class wrapper; never store a second scientific text."""
    fields, classification, body, theorems = _front_matter(text)
    meta = {key: plain_metadata(fields[command]) for key, command in
            [('title', 'title'), ('author', 'author'), ('email', 'email'), ('affiliation', 'affil')]}
    body = _title_layout(body)
    body = body.replace(r'\bibliography{refs}', r'\input{manuscript.bbl}')
    return r'''\documentclass{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern,xcolor,amsmath,amssymb,mathtools,amsthm,graphicx,booktabs}
\usepackage[authoryear]{natbib}
\usepackage{hyperref,placeins}
\newcommand{\Needspace}[1]{}
\newcommand{\backmatter}{}
\newcommand{\bibcommenthead}{}
\newenvironment{barticle}{}{}
\newenvironment{bbook}{}{}
\newenvironment{bchapter}{}{}
\newenvironment{botherref}{}{}
''' + theorems + '\n' + r'\begin{document}' + '\n' + (
        r'\title{' + meta['title'] + '}\n' +
        r'\author{' + meta['author'] + '}\n' +
        r'\date{' + meta['affiliation'] + '}\n' + r'\maketitle' + '\n' +
        r'\noindent\href{mailto:' + meta['email'] + '}{' + meta['email'] + '}\n' +
        r'\begin{abstract}' + fields['abstract'] + r'\end{abstract}' + '\n' +
        r'\noindent\textbf{Keywords:} ' + fields['keywords'] + '\n\n' +
        r'\noindent\textbf{' + classification + ':} ' + fields['pacs'] + '\n' + body)


def authored_sources(manuscript):
    """Active authored inputs in document order, excluding publisher support."""
    from inventory import read_inventory
    return [manuscript / item['path'] for item in read_inventory(manuscript / 'manuscript.tex')['sources']
            if item['role'] == 'authored']
