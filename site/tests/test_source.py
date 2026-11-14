"""Small independent fixtures for the bounded Springer wrapper grammar."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source import argument, make_wrapper, source_metadata, read_tex

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = r'''\documentclass[pdflatex,sn-mathphys-ay]{sn-jnl}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,mathtools}
\newtheorem{proposition}{Proposition}
\begin{document}
\title[Short title]{A small manuscript}
\author*[1]{\fnm{Ada} \sur{Example}}\email{ada@example.org}
\affil*[1]{\orgname{Example Institute}, \orgaddress{\city{Oxford}, \country{UK}}}
\abstract{An abstract with {nested text}.}
\keywords{Geometry, inference}
\pacs[MSC2020]{Primary 65D18}
\maketitle
\vspace{-28pt}
\noindent\begin{minipage}{\linewidth}
\footnotesize
\textbf{Acknowledgments.} Thanks for the useful discussion.
\end{minipage}
\clearpage
\input{sections/introduction}
\section*{Statements and Declarations}
An independent declaration.
\bibliography{refs}
\end{document}
'''


class WrapperTests(unittest.TestCase):
    def test_supported_metadata_and_science_propagate(self):
        self.assertEqual(source_metadata(FIXTURE), {
            'title': 'A small manuscript', 'author': 'Ada Example',
            'email': 'ada@example.org', 'affiliation': 'Example Institute, Oxford, UK'})
        revised = FIXTURE.replace('sections/introduction', 'chapters/introduction').replace('A small manuscript', 'A revised manuscript').replace(
            'Ada', 'Grace').replace('ada@example.org', 'grace@example.org').replace(
            'Example Institute', 'New Institute').replace('An abstract', 'A revised abstract').replace(
            'Geometry, inference', 'Graphs, fitting').replace('MSC2020', 'MSC2010').replace(
            'Primary 65D18', 'Secondary 52C22').replace('An independent declaration.', 'Revised declaration.')
        wrapper = make_wrapper(revised)
        for expected in ('A revised manuscript', 'Grace Example', 'grace@example.org',
                         'New Institute', 'A revised abstract', 'Graphs, fitting',
                         r'\textbf{MSC2010:} Secondary 52C22', 'Revised declaration.',
                         r'\input{chapters/introduction}', r'\input{manuscript.bbl}'):
            self.assertIn(expected, wrapper)
        self.assertNotIn(r'\begin{minipage}', wrapper)
        self.assertNotIn(r'\footnotesize', wrapper)
        self.assertNotIn(r'\vspace{-28pt}', wrapper)

    def test_each_metadata_field_must_occur_once(self):
        for command in ('title', 'author', 'email', 'affil', 'abstract', 'keywords', 'pacs'):
            with self.subTest(command=command):
                duplicate = '\\' + command + ('[MSC2020]' if command == 'pacs' else '') + '{Extra}'
                with self.assertRaisesRegex(ValueError, 'front matter|classification'):
                    make_wrapper(FIXTURE.replace(r'\maketitle', duplicate + '\n' + r'\maketitle'))
                without = re.sub(r'\\' + command + r'\*?(?:\[[^]]*\])?\{', r'\\unknown{', FIXTURE, count=1)
                with self.assertRaisesRegex(ValueError, 'front matter|classification'):
                    make_wrapper(without)

    def test_visible_or_unknown_front_matter_never_disappears(self):
        for addition in ('Important result.', r'\dedication{For a colleague}',
                         r'\thanks{Scientific contribution}', r'\newcommand{\x}{x}',
                         r'\abstract{Duplicate} ', r'\begin{abstract}Second abstract\end{abstract}'):
            with self.subTest(addition=addition), self.assertRaisesRegex(ValueError, 'front matter'):
                make_wrapper(FIXTURE.replace(r'\maketitle', addition + '\n' + r'\maketitle'))

    def test_unsupported_preamble_semantics_fail_closed(self):
        for addition in (r'\newcommand{\newmath}{x^2}', r'\def\newmath{x}',
                         r'\DeclareMathOperator{\rank}{rank}', r'\usepackage{physics}',
                         r'\usepackage[fleqn]{amsmath}', r'\input{scientific-definitions}',
                         'An important preamble statement.', r'\AtBeginDocument{New text}'):
            with self.subTest(addition=addition), self.assertRaisesRegex(ValueError, 'preamble'):
                make_wrapper(FIXTURE.replace(r'\begin{document}', addition + '\n' + r'\begin{document}'))

    def test_known_publisher_and_extraction_settings_are_supported(self):
        addition = r'''\usepackage{lmodern,xcolor,graphicx,placeins,needspace,booktabs}
\usepackage[utf8]{inputenc}
\hypersetup{hidelinks, pdftitle={A small manuscript}, pdfauthor={Ada Example}}
\input{tex-support/glyphtounicode-cmr.tex}
\pdfgentounicode=1
'''
        wrapper = make_wrapper(FIXTURE.replace(r'\begin{document}', addition + r'\begin{document}'))
        self.assertIn(r'\title{A small manuscript}', wrapper)
        self.assertNotIn('glyphtounicode', wrapper)

    def test_multiline_balanced_theorem_declarations_survive(self):
        declaration = r'''\newtheorem{lemma}[proposition]
  {A {nested} heading}
\newtheorem*{observation}{Observation}
\newtheorem{claim}{Claim}[section]'''
        wrapper = make_wrapper(FIXTURE.replace(r'\newtheorem{proposition}{Proposition}', declaration))
        self.assertIn(declaration, wrapper)

    def test_title_layout_removal_does_not_strip_later_scientific_layout(self):
        later = r'''\begin{minipage}{\linewidth}
\footnotesize Scientific table content.
\vspace{-28pt}
\end{minipage}'''
        wrapper = make_wrapper(FIXTURE.replace('An independent declaration.', later))
        self.assertIn(later, wrapper)

    def test_unrecognized_title_layout_is_preserved(self):
        for changed in (FIXTURE.replace(r'\linewidth', '.8\\linewidth'),
                        FIXTURE.replace(r'\footnotesize', r'\small'),
                        FIXTURE.replace(r'\vspace{-28pt}', r'\vspace{-10pt}')):
            wrapper = make_wrapper(changed)
            # Only the exact publisher title-page layout is adapted.
            self.assertIn(r'\begin{minipage}', wrapper)

    def test_comments_and_escaped_delimiters_are_lexical(self):
        changed = FIXTURE.replace(r'\abstract{An abstract with {nested text}.}',
                                  r'\abstract{A literal \{brace\} and 10\% improvement.}')
        changed = changed.replace(r'\begin{document}',
                                  '% \\newcommand{\\unsafe}{x}\n' + r'\begin{document}')
        changed = changed.replace(r'\keywords{Geometry, inference}',
                                  r'\keywords % trailing comment' + '\n{Geometry, inference}')
        self.assertIn(r'A literal \{brace\} and 10\% improvement.', make_wrapper(changed))

    def test_word_internal_comments_agree_in_metadata_arguments_and_wrapper(self):
        changed = FIXTURE.replace('A small manuscript', 'A com% title note\n    pact manuscript').replace(
            'An abstract with {nested text}.', r'A reproduc% abstract note' +
            '\n    ible result with $' + r'\text{con% math-text note' + '\n    nected}$.')
        self.assertEqual(source_metadata(changed)['title'], 'A compact manuscript')
        self.assertEqual(argument(changed, 'abstract'), r'A reproducible result with $\text{connected}$.')
        wrapper = make_wrapper(changed)
        self.assertIn(r'\title{A compact manuscript}', wrapper)
        self.assertIn(r'A reproducible result with $\text{connected}$.', wrapper)

    def test_source_reader_consumes_comments_before_production_wrapper(self):
        changed = FIXTURE.replace('A small manuscript', 'A com% note\n    pact manuscript').replace(
            'An abstract with {nested text}.', 'A reproduc% note\n    ible result.')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'manuscript.tex'
            path.write_text(changed)
            source = read_tex(path)
        self.assertIn(r'\title[Short title]{A compact manuscript}', source)
        self.assertIn(r'\abstract{A reproducible result.}', source)
        self.assertIn(r'\title{A compact manuscript}', make_wrapper(source))

    def test_unbalanced_or_nonliteral_classification_fails(self):
        for value in (r'\pacs', r'\pacs[]', r'\pacs[\customlabel]'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'classification'):
                make_wrapper(FIXTURE.replace(r'\pacs[MSC2020]', value))
        with self.assertRaisesRegex(ValueError, 'Unbalanced|unbalanced'):
            make_wrapper(FIXTURE.replace('{An abstract with {nested text}.}', '{An abstract'))

    def test_metadata_after_maketitle_is_rejected(self):
        for extra in (r'\keywords{Hidden update}', r'\abstract{A second abstract}',
                      r'\author{Another person}', r'\maketitle'):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'front matter'):
                make_wrapper(FIXTURE.replace(r'\end{document}', extra + r'\end{document}'))

    def test_front_matter_commands_allow_spacing_and_exact_token_names(self):
        changed = FIXTURE.replace(r'\author*[1]', r'\author * [1] ').replace(
            r'\pacs[MSC2020]', r'\pacs [MSC2010] ')
        self.assertIn(r'\author{Ada Example}', make_wrapper(changed))
        self.assertIn(r'\textbf{MSC2010:}', make_wrapper(changed))
        for command in ('title', 'author', 'email', 'affil'):
            with self.subTest(command=command), self.assertRaisesRegex(ValueError, 'front matter'):
                make_wrapper(FIXTURE.replace('\\' + command, '\\' + command + 'extra', 1))

    def test_unsupported_metadata_macros_never_disappear(self):
        for replacement in (r'\title{A \thanks{Hidden contribution} title}',
                            r'\title{A $mathematical$ title}', r'\title{}'):
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, 'front matter'):
                make_wrapper(FIXTURE.replace(r'\title[Short title]{A small manuscript}', replacement))

    def test_invalid_theorem_syntax_is_not_silently_truncated(self):
        for declaration in (r'\newtheorem{lemma}{Lemma}[section][extra]',
                            r'\newtheorem*{lemma}[proposition]{Lemma}',
                            r'\newtheorem{lemma}{Unbalanced'):
            with self.subTest(declaration=declaration), self.assertRaisesRegex(ValueError, 'preamble'):
                make_wrapper(FIXTURE.replace(r'\newtheorem{proposition}{Proposition}', declaration))

    def test_actual_source_is_characterized_from_its_active_statements(self):
        source = read_tex(ROOT / 'manuscript/manuscript.tex')
        wrapper = make_wrapper(source)
        # These expectations come from original source tokens, never converted artifacts.
        for command in ('title', 'abstract', 'keywords', 'pacs'):
            self.assertIn(argument(source, command), wrapper)
        for include in re.findall(r'\\input\s*\{([^}]+)\}', source.split(r'\maketitle', 1)[1]):
            self.assertIn(r'\input{' + include + '}', wrapper)
        declarations = source.split(r'\backmatter', 1)[1].split(r'\bibliography', 1)[0]
        self.assertIn(declarations, wrapper)


if __name__ == '__main__':
    unittest.main()
