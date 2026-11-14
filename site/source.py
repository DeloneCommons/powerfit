"""Adapt publisher-only front matter; scientific includes remain byte-for-byte sources."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_manuscript import collect_dependencies, read_tex  # noqa: E402


def argument(text, command):
    """Read a balanced braced argument after an optional star/bracket argument."""
    match = re.search(r'\\' + command + r'\*?\s*(?:\[[^\]]*\]\s*)?\{', text)
    if not match:
        raise ValueError(f'Unsupported manuscript front matter: missing {command}')
    start = match.end()
    depth, end = 1, start
    while end < len(text) and depth:
        if text[end] in '{}' and (end == 0 or text[end - 1] != '\\'):
            depth += 1 if text[end] == '{' else -1
        end += 1
    if depth:
        raise ValueError(f'Unbalanced manuscript front matter: {command}')
    return text[start:end - 1]


def plain_metadata(value):
    # Only the publisher's naming/affiliation wrappers are understood here.
    value = re.sub(r'\\(?:fnm|sur|orgname|orgaddress|city|country)\s*', '', value)
    value = value.replace('{', '').replace('}', '')
    if '\\' in value:
        raise ValueError('Unsupported command in manuscript front matter')
    return ' '.join(value.split())


def source_metadata(text):
    fields = [('title', 'title'), ('author', 'author'), ('email', 'email'), ('affiliation', 'affil')]
    for _, command in fields:
        count = len(re.findall(r'\\' + command + r'\*?(?:\[[^\]]*\])?\s*\{', text))
        if count != 1:
            raise ValueError(f'Unsupported manuscript front matter: expected one {command}, found {count}')
    return {key: plain_metadata(argument(text, command)) for key, command in fields}


def make_wrapper(text):
    """Generate an article-class wrapper; never store a second scientific text."""
    meta = source_metadata(text)
    labels = re.findall(r'\\pacs\b\s*(?:\[([^\]]*)\])?\s*\{', text)
    if len(labels) != 1 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 .()/-]*', labels[0]):
        raise ValueError('Unsupported manuscript classification: expected one explicit literal pacs label')
    classification = labels[0]
    if text.count(r'\maketitle') != 1:
        raise ValueError('Unsupported manuscript front matter: expected one maketitle')
    body = text.split(r'\maketitle', 1)[1]
    # The title-page minipage is solely print layout. Its text is preserved.
    body = body.replace(r'\noindent\begin{minipage}{\linewidth}', '')
    body = body.replace(r'\end{minipage}', '').replace(r'\vspace{-28pt}', '')
    # Restrict this removal to front matter, leaving all included source intact.
    before, includes = body.split(r'\input{sections/', 1)
    body = before.replace(r'\footnotesize', '') + r'\input{sections/' + includes
    body = body.replace(r'\bibliography{refs}', r'\input{manuscript.bbl}')
    theorems = '\n'.join(re.findall(r'^\\newtheorem[^\n]+', text, re.M))
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
        r'\begin{abstract}' + argument(text, 'abstract') + r'\end{abstract}' + '\n' +
        r'\noindent\textbf{Keywords:} ' + argument(text, 'keywords') + '\n\n' +
        r'\noindent\textbf{' + classification + ':} ' + argument(text, 'pacs') + '\n' + body)


def authored_sources(manuscript):
    """Only authored text, excluding the upstream Unicode mapping data."""
    return [manuscript / 'manuscript.tex',
            *sorted((manuscript / 'sections').glob('*.tex')),
            *sorted((manuscript / 'appendices').glob('*.tex'))]
