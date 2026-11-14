"""Two real compact Springer builds prove supported revisions need no count refresh.

The class builds each independent source tree once. No repository scientific
source, frozen evidence, publication asset or reviewed warning record is edited.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from lxml import etree, html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bibliography import source_dois, validate_bibliography_dois
from canonical import (canonical_bibliography, read_aux, validate_labels,
                       validate_recorder, validate_canonical_bibliography)
from coverage import validate_inventory
from inventory import read_inventory
from render import assemble
from source import argument, make_wrapper, source_metadata, read_tex

ROOT = Path(__file__).resolve().parents[2]
NS = {'l': 'http://dlmf.nist.gov/LaTeXML'}
XID = '{http://www.w3.org/XML/1998/namespace}id'
TOOLS = ('pdflatex', 'bibtex', 'latexml', 'latexmlpost', 'pdftocairo', 'pdftotext')


def manuscript(author, title, abstract, keywords, classification, body, classification_label='MSC2020'):
    return r'''\documentclass[pdflatex,sn-mathphys-ay]{sn-jnl}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb,mathtools}
\usepackage{graphicx}
\usepackage{booktabs}
\input{tex-support/glyphtounicode-cmr.tex}
\pdfgentounicode=1
\newtheorem{proposition}{Proposition}
\begin{document}
''' + '\\title{' + title + '}\n' + '\\author*[1]{\\fnm{' + author + r'''} \sur{Example}}\email{''' + author.lower() + r'''@example.org}
\affil*[1]{\orgname{''' + author + r''' Institute}, \orgaddress{\city{Oxford}, \country{UK}}}
\abstract{''' + abstract + '}\n\\keywords{' + keywords + '}\n\\pacs[' + classification_label + ']{' + classification + r'''}
\maketitle
''' + body + '\n\\bibliography{refs}\n\\end{document}\n'


def bibrecord(key, author, title, year, doi):
    return ('@article{' + key + ',\n author={' + author + '},\n title={' + title +
            '},\n journal={Example Journal},\n year={' + year +
            '},\n volume={2},\n pages={1--3},\n doi={' + doi + '}\n}\n')


def fixture_sources(revised):
    """Authored fixture text is explicit independent input, never output-derived."""
    shared = bibrecord('Shared2020', 'Example, Ada', 'An enduring method', '2020', '10.1000/shared')
    if not revised:
        main = manuscript('Ada', 'A com% title comment\n    pact geometry manuscript',
                          'A short abstract describes $x$ and a reproduc% abstract comment\n    ible method with $' +
                          r'\text{con% mathematical text comment' + '\n    nected}+x$ words.',
                          'Geometry, fitting', 'Primary 65D18', r'''
\input{chapters/first}
\input{chapters/second}
\section*{Statements and Declarations}
\subsection*{Funding}
No external funding.
''')
        return {
            'manuscript.tex': main,
            'chapters/first.tex': r'''\section{Geometry}\label{sec:geometry}
A short observation uses $x_i$.
\subsection{First case}
\begin{equation}x_i=y_i+1.\label{eq:old}\end{equation}
\begin{equation}z=2.\end{equation}
Equation~\eqref{eq:old} is useful; see \citep{Shared2020,Removed2021}.
\begin{proposition}[Small claim]We have $x_i>0$.\end{proposition}
\begin{proof}It follows immediately.\end{proof}
\begin{figure}\centering
\includegraphics[width=.5\linewidth]{figures/first.pdf}
\caption{A small geometry illustration.}\label{fig:one}
\end{figure}
\begin{table}\caption{A small table.}\label{tab:one}
\begin{tabular}{lc}\toprule Item & Value\\\midrule A & $2$\\\bottomrule\end{tabular}
\end{table}
''',
            'chapters/second.tex': r'''\section{Interpretation}\label{sec:interpretation}
\subsection{Second case}
The first result appears in Section~\ref{sec:geometry}.
''',
            'orphan.tex': r'\section{Inactive old draft}This draft is not active.',
            'refs.bib': shared + bibrecord('Removed2021', 'Old, Bea', 'A retired comparison', '2021', '10.1000/removed'),
        }
    main = manuscript('Grace', 'Revised geometry and observations',
                      'A rewritten and rewrapped abstract studies $q^2$ with revised observations.',
                      'Graphs, inverse problems', 'Secondary 52C22', r'''
\input{chapters/second}
\input{chapters/first}
\section*{Statements and Declarations}
\subsection*{Funding}
Internal support only.
\subsection*{Competing interests}
None declared.
\appendix
\input{appendices/extra}
''', classification_label='MSC2010')
    return {
        'manuscript.tex': main,
        'chapters/second.tex': r'''\section{Interpretation}\label{sec:interpretation}
\subsection{Reordered second case}
The revised result appears in Section~\ref{sec:geometry}; see \citep{Added2024}.
''',
        'chapters/first.tex': r'''\section{Geometry}\label{sec:geometry}
\subsection{New leading subsection}
A revised short observation uses $q^2$ and \citep{Shared2020}.
\input{parts/algebra}
\begin{figure}\centering
\includegraphics[width=.5\linewidth]{figures/first.pdf}
\caption{The revised geometry illustration.}\label{fig:one}
\end{figure}
\begin{figure}\centering
\includegraphics[width=.4\linewidth]{figures/additional.pdf}
\caption{An additional independent illustration.}\label{fig:two}
\end{figure}
\begin{table}\caption{The expanded table.}\label{tab:one}
\begin{tabular}{lc}\toprule Item & Value\\\midrule B & $3$\\ C & $4$\\\bottomrule\end{tabular}
\end{table}
''',
        'parts/algebra.tex': r'''\subsection{Revised algebra}
\begin{align}
a&=b,\label{eq:renamed}\\
c&=\begin{cases}1&x>0\\0&x\le0\end{cases}\notag\\
d&=e.
\end{align}
\begin{equation}h=q+1.\label{eq:additional}\end{equation}
\begin{equation}t=3.\end{equation}
Equation~\eqref{eq:renamed} replaces the earlier label.
\begin{proposition}[Revised small claim]We have $q>0$.\end{proposition}
\begin{proof}Apply the inequality $q>0$.\end{proof}
''',
        'appendices/extra.tex': r'''\section{An added appendix}\label{app:extra}
A new unnumbered table records two populations.
\begin{tabular}{lc}\toprule Field & Population\\\midrule Active & Current\\ All & Original\\\bottomrule\end{tabular}
''',
        'orphan.tex': r'\section{Inactive revised draft}A different inactive draft.',
        'refs.bib': shared + bibrecord('Added2024', 'New, Cora', 'An added revised comparison', '2024', '10.1000/added'),
    }


class SupportedRevisionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [name for name in TOOLS if shutil.which(name) is None]
        if missing:
            raise unittest.SkipTest('Real Springer fixture tools unavailable: ' + ', '.join(missing))
        cls.temporary = tempfile.TemporaryDirectory(prefix='powerfit-revision-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.cases = [cls.build_fixture(Path(cls.temporary.name) / name, revised)
                     for name, revised in (('original', False), ('revision', True))]

    @classmethod
    def command(cls, command, directory):
        result = subprocess.run(command, cwd=directory, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=180)
        if result.returncode:
            raise AssertionError('Fixture command failed: ' + ' '.join(command) + '\n' + result.stdout[-16000:])
        return result.stdout

    @classmethod
    def build_fixture(cls, directory, revised):
        directory.mkdir()
        for name, text in fixture_sources(revised).items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        for name in ('sn-jnl.cls', 'sn-mathphys-ay.bst', 'tex-support/glyphtounicode-cmr.tex'):
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'manuscript' / name, target)
        figures = directory / 'figures'
        figures.mkdir()
        for name in ('first.pdf', 'additional.pdf') if revised else ('first.pdf',):
            shutil.copyfile(ROOT / 'manuscript/figures/figure_02_separators.pdf', figures / name)
        latex = ['pdflatex', '-interaction=nonstopmode', '-halt-on-error', '-recorder', 'manuscript.tex']
        cls.command(latex, directory)
        cls.command(['bibtex', 'manuscript'], directory)
        cls.command(latex, directory)
        cls.command(latex, directory)
        original = read_tex(directory / 'manuscript.tex')
        (directory / 'article.tex').write_text(make_wrapper(original))
        conversion = cls.command(['latexml', '--nocomments', '--dest=article.xml', 'article.tex'], directory)
        postprocessing = cls.command(['latexmlpost', '--format=html5', '--nosplit', '--pmml',
                                     '--mathtex', '--nographicimages', '--dest=article-raw.html', 'article.xml'], directory)
        for stage, log in (('conversion', conversion), ('postprocessing', postprocessing)):
            if any(line.startswith(('Warning:', 'Error:', 'Fatal:')) for line in log.splitlines()):
                raise AssertionError('Unexpected compact fixture ' + stage + ' diagnostic:\n' + log[-12000:])
        xml = etree.parse(str(directory / 'article.xml'))
        raw = html.parse(str(directory / 'article-raw.html'))
        output = directory / 'output'
        (output / 'figures').mkdir(parents=True)
        for pdf in figures.glob('*.pdf'):
            cls.command(['pdftocairo', '-svg', str(pdf), str(output / 'figures' / pdf.with_suffix('.svg').name)], directory)
        # Deliberately explicit fixture-only provenance; never a real publication.
        provenance = {'build_commit': '0' * 40, 'dirty': True,
                      'manuscript_revision': {'commit': '0' * 40, 'date': '2000-01-01'}}
        assemble(directory / 'article-raw.html', xml, output, source_metadata(original), provenance)
        page = html.parse(str(output / 'article.html'))
        inventory = read_inventory(directory / 'manuscript.tex')
        return {'directory': directory, 'inventory': inventory, 'xml': xml, 'raw': raw,
                'page': page, 'aux': read_aux(directory / 'manuscript.aux')}

    def test_each_source_revision_matches_all_three_actual_converted_representations(self):
        for case in self.cases:
            with self.subTest(tree=case['directory'].name):
                errors, report = validate_inventory(case['inventory'], case['xml'], case['raw'], case['page'])
                self.assertEqual(errors, [])
                self.assertTrue(report['valid'])

    def test_fresh_canonical_labels_dependencies_bibliography_and_dois_agree(self):
        for case in self.cases:
            with self.subTest(tree=case['directory'].name):
                directory = case['directory']
                self.assertEqual(validate_labels(case['inventory']['labels'], case['aux'], case['xml'], case['page']), [])
                self.assertEqual(validate_recorder(directory / 'manuscript.fls', directory, case['inventory']['sources']), [])
                for representation in (case['raw'], case['page']):
                    self.assertEqual(validate_canonical_bibliography(directory / 'manuscript.bbl', case['xml'], representation), [])
                    self.assertEqual(validate_bibliography_dois(representation, case['xml'].xpath('//l:bibitem', namespaces=NS),
                                                              source_dois(directory / 'refs.bib'), XID), [])
                self.assertTrue((directory / 'manuscript.pdf').is_file())

    def test_comment_wordjoins_agree_with_fresh_canonical_and_all_site_stages(self):
        case = self.cases[0]
        directory = case['directory']
        source = read_tex(directory / 'manuscript.tex')
        self.assertEqual(source_metadata(source)['title'], 'A compact geometry manuscript')
        self.assertIn(r'\title{A compact geometry manuscript}', (directory / 'article.tex').read_text())
        self.assertEqual(argument(source, 'abstract'),
                         r'A short abstract describes $x$ and a reproducible method with $\text{connected}+x$ words.')
        title = next(obj for obj in case['inventory']['objects'] if obj['kind'] == 'title')
        self.assertEqual(title['content'], [{'kind': 'text', 'text': 'A compact geometry manuscript'}])
        self.assertTrue(any(math['tex'] == r'\text{connected}+x' for math in case['inventory']['math']))
        pdf_text = self.command(['pdftotext', '-f', '1', '-l', '1', 'manuscript.pdf', '-'], directory)
        compact_pdf = ''.join(pdf_text.split())
        for visible in ('A compact geometry manuscript', 'a reproducible method', 'connected'):
            self.assertIn(''.join(visible.split()), compact_pdf)
        self.assertEqual(validate_inventory(case['inventory'], case['xml'], case['raw'], case['page'])[0], [])

    def test_composite_revision_changes_supported_objects_without_count_refresh(self):
        original, revision = self.cases
        first, second = original['inventory'], revision['inventory']
        def objects(data, kind):
            return [o for o in data['objects'] if o['kind'] == kind]
        def text(obj):
            return ''.join(t.get('text', '') for t in obj['content'])
        for field in ('title', 'author', 'affil', 'email', 'abstract', 'keywords', 'pacs'):
            self.assertNotEqual(objects(first, field)[0]['content'], objects(second, field)[0]['content'], field)
        self.assertNotEqual(objects(first, 'pacs')[0]['option'], objects(second, 'pacs')[0]['option'])
        self.assertNotEqual([o.get('title') for o in objects(first, 'section')],
                            [o.get('title') for o in objects(second, 'section')])
        self.assertEqual([o['labels'] for o in objects(first, 'section')[:2]], [['sec:geometry'], ['sec:interpretation']])
        self.assertEqual([o['labels'] for o in objects(second, 'section')[:2]], [['sec:interpretation'], ['sec:geometry']])
        self.assertIn('parts/algebra.tex', [s['path'] for s in second['sources']])
        self.assertNotIn('orphan.tex', [s['path'] for data in (first, second) for s in data['sources']])
        self.assertIn('eq:old', first['labels'])
        self.assertNotIn('eq:old', second['labels'])
        self.assertIn('eq:renamed', second['labels'])
        self.assertIn('eq:additional', second['labels'])
        self.assertNotEqual([m['tex'] for m in first['math'] if m['numbered'] and not m['labels']],
                            [m['tex'] for m in second['math'] if m['numbered'] and not m['labels']])
        align_rows = [m for m in second['math'] if m['mode'] == 'row']
        self.assertTrue(any(m['numbered'] for m in align_rows))
        self.assertTrue(any(not m['numbered'] and r'\begin{cases}' in m['tex'] for m in align_rows))
        self.assertNotEqual([m['tex'] for m in first['math'] if m['mode'] == 'inline'],
                            [m['tex'] for m in second['math'] if m['mode'] == 'inline'])
        self.assertGreater(len(objects(second, 'graphic')), len(objects(first, 'graphic')))
        self.assertGreater(len(objects(second, 'tabular')), len(objects(first, 'tabular')))
        self.assertTrue(any(o.get('appendix') for o in objects(second, 'section')))
        before = canonical_bibliography(original['directory'] / 'manuscript.bbl')
        after = canonical_bibliography(revision['directory'] / 'manuscript.bbl')
        self.assertNotEqual([b['key'] for b in before], [b['key'] for b in after])
        self.assertNotEqual(source_dois(original['directory'] / 'refs.bib'), source_dois(revision['directory'] / 'refs.bib'))
        self.assertIn('No external funding.', [text(o) for o in objects(first, 'prose')])
        self.assertIn('Internal support only.', [text(o) for o in objects(second, 'prose')])


if __name__ == '__main__':
    unittest.main()
