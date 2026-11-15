"""Small source/PDF-text fixtures for the independent CAM first-page contract."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_manuscript_titlepage import (titlepage_expectations, validate_titlepage,
                                      bibliography_page_expectations, validate_bibliography_pages)

SOURCE = r'''\documentclass[pdflatex,sn-mathphys-ay]{sn-jnl}
\begin{document}
\title{A tiny first-page study}
\author*[1]{\fnm{Ada} \sur{Example}}\email{ada@example.org}
\affil*[1]{\orgname{Tiny Institute}, \orgaddress{\city{Bath}, \country{UK}}}
\abstract{A fitted separator has scientific significance.}
\keywords{Geometry, inverse fitting}
\pacs[MSC2010]{Primary 52C22}
\maketitle
\noindent\begin{minipage}{\linewidth}\footnotesize
\textbf{Acknowledgments.} Thanks to a careful reader.
\par\smallskip
\textbf{Author contributions.} Ada designed the study
(\href{https://orcid.org/0000-0000-1111-2222}{ORCID: 0000-0000-1111-2222}).
\end{minipage}
\clearpage
\input{chapters/body}
\end{document}
'''
PAGE = '''A tiny first-page study
Ada Example1* Tiny Institute, Bath, UK.
Corresponding author. E-mail: ada@example.org;
Abstract
A fitted separator has scientific significance.
Keywords: Geometry, inverse fitting
MSC2010: Primary 52C22
Acknowledgments. Thanks to a careful reader.
Author contributions. Ada designed the study (ORCID: 0000-0000-1111-2222).
1
'''


class TitlePageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = self.root / 'manuscript.tex'
        self.master.write_text(SOURCE)
        (self.root / 'chapters').mkdir()
        (self.root / 'chapters/body.tex').write_text(r'\section{Body}Material for later pages.')

    def test_hand_authored_expectations_cover_metadata_and_opening_declarations(self):
        actual = [(entry['role'], entry['text']) for entry in titlepage_expectations(self.master)]
        self.assertEqual(actual, [
            ('title', 'A tiny first-page study'), ('author', 'Ada Example'),
            ('email', 'ada@example.org'), ('affiliation', 'Tiny Institute, Bath, UK'),
            ('abstract', 'A fitted separator has scientific significance.'),
            ('keywords', 'Geometry, inverse fitting'), ('classification', 'Primary 52C22'),
            ('classification label', 'MSC2010'),
            ('declaration', 'Acknowledgments. Thanks to a careful reader.'),
            ('declaration', 'Author contributions. Ada designed the study (ORCID: 0000-0000-1111-2222).')])
        self.assertEqual(validate_titlepage(self.master, PAGE), [])

    def test_each_omitted_or_substituted_source_field_fails_by_role(self):
        for role, value in (('title', 'A tiny first-page study'), ('author', 'Ada Example1*'),
                            ('email', 'ada@example.org'), ('affiliation', 'Tiny Institute'),
                            ('abstract', 'scientific significance'), ('keywords', 'inverse fitting'),
                            ('classification', '52C22'), ('classification label', 'MSC2010'),
                            ('declaration', 'Thanks to a careful reader.'),
                            ('declaration', '0000-0000-1111-2222')):
            self.assertEqual(PAGE.count(value), 1, value)
            with self.subTest(role=role):
                errors = validate_titlepage(self.master, PAGE.replace(value, 'OTHER'))
                self.assertTrue(any(f'[{role}]' in e for e in errors), errors)

    def test_extended_field_tokens_are_rejected_by_role(self):
        for role, target, replacement in (
            ('title', 'first-page study', 'first-page studying'),
            ('title', 'A tiny first-page study', 'BA tiny first-page study'),
            ('author', 'Ada Example1*', 'Ada Examples1*'),
            ('author', 'Ada Example1*', 'Bada Example1*'),
            ('email', 'ada@example.org', 'xada@example.org'),
            ('email', 'ada@example.org', 'ada@example.org.evil'),
            ('email', 'ada@example.org', 'ada@example.org\n.evil'),
            ('affiliation', 'Bath, UK.', 'Bath, UKs.'),
            ('abstract', 'scientific significance.', 'scientific significances.'),
            ('keywords', 'inverse fitting', 'inverse fittings'),
            ('classification', '52C22', '52C220'),
            ('classification label', 'MSC2010', 'MSC20100'),
            ('declaration', 'careful reader.', 'careful readers.'),
        ):
            with self.subTest(role=role, replacement=replacement):
                self.assertEqual(PAGE.count(target), 1, target)
                changed = PAGE.replace(target, replacement)
                self.assertNotEqual(changed, PAGE)
                errors = validate_titlepage(self.master, changed)
                self.assertTrue(any(f'[{role}]' in error for error in errors), errors)

    def test_reported_prefix_counterexamples_in_independent_source_fixture(self):
        source = SOURCE.replace(r'\fnm{Ada} \sur{Example}',
                                r'\fnm{Ivan Yu.} \sur{Chernyshov}')
        page = PAGE.replace('Ada Example1*', 'Ivan Yu. Chernyshov1*')
        for original, replacement in (
            ('A tiny first-page study', 'A study from pairwise separator data'),
            ('ada@example.org', 'ivan.chernyshoff@gmail.com'),
            ('52C22', '65F20'),
        ):
            source = source.replace(original, replacement)
            page = page.replace(original, replacement)
        self.master.write_text(source)
        self.assertEqual(validate_titlepage(self.master, page), [])
        for role, target, replacement in (
            ('author', 'Ivan Yu. Chernyshov1*', 'Ivan Yu. Chernyshova1*'),
            ('title', 'from pairwise separator data', 'from pairwise separator database'),
            ('classification', '65F20', '65F200'),
            ('email', 'ivan.chernyshoff@gmail.com', 'xivan.chernyshoff@gmail.com'),
            ('email', 'ivan.chernyshoff@gmail.com', 'ivan.chernyshoff@gmail.com.evil'),
        ):
            with self.subTest(role=role, replacement=replacement):
                self.assertEqual(page.count(target), 1, target)
                changed = page.replace(target, replacement)
                self.assertNotEqual(changed, page)
                errors = validate_titlepage(self.master, changed)
                self.assertTrue(any(f'[{role}]' in error for error in errors), errors)

    def test_email_boundaries_allow_layout_without_accepting_other_addresses(self):
        for email in ('ada @ example . org', 'ada@\nexample.org', 'ada@exam\nple.org'):
            with self.subTest(email=email):
                page = PAGE.replace('ada@example.org', email)
                self.assertEqual(validate_titlepage(self.master, page), [])
        # The exact email elsewhere on page one cannot repair a changed address
        # before the abstract, even when punctuation removal makes them equal.
        changed = PAGE.replace('ada@example.org', 'adaexample.org') + '\nada@example.org'
        errors = validate_titlepage(self.master, changed)
        self.assertTrue(any('[email]' in error for error in errors), errors)

    def test_author_numeric_footnote_markers_and_wrapping_remain_supported(self):
        for author in ('Ada Example1*', 'Ada Example¹*', 'Ada Example1,2*',
                       'Ada\nExample12†', 'Ada Example'):
            with self.subTest(author=author):
                self.assertEqual(validate_titlepage(
                    self.master, PAGE.replace('Ada Example1*', author)), [])

    def test_supported_source_revisions_change_the_expectations(self):
        revised_source = SOURCE.replace('MSC2010', 'MSC2020').replace('Ada', 'Grace').replace(
            'Tiny Institute', 'New Laboratory').replace('0000-0000-1111-2222', '9999-8888-7777-6666')
        revised_page = PAGE.replace('MSC2010', 'MSC2020').replace('Ada', 'Grace').replace(
            'Tiny Institute', 'New Laboratory').replace('0000-0000-1111-2222', '9999-8888-7777-6666')
        self.master.write_text(revised_source)
        self.assertEqual(validate_titlepage(self.master, revised_page), [])
        self.assertTrue(validate_titlepage(self.master, PAGE))

    def test_pdf_wrapping_ligatures_and_punctuation_spacing_are_supported(self):
        page = PAGE.replace('first-page', 'first-\npage').replace('fitted', 'ﬁtted').replace(
            'scientific', 'scienti-\nfic').replace('Geometry,', 'Geometry ,')
        self.assertEqual(validate_titlepage(self.master, page), [])
        self.assertTrue(any('[email]' in e for e in validate_titlepage(
            self.master, PAGE.replace('ada@example.org', 'ada@exampleorg'))))

    def test_metadata_and_declarations_cannot_be_satisfied_on_later_pages(self):
        value = 'Thanks to a careful reader.'
        split_pages = PAGE.replace(value, '') + '\f' + value
        self.assertTrue(any('[declaration]' in e for e in validate_titlepage(self.master, split_pages)))

    def test_later_content_is_not_required_on_page_one(self):
        source = SOURCE.replace(r'\clearpage', '').replace(r'\input{chapters/body}',
                        r'\section{Body}Later root text.\input{chapters/body}')
        self.master.write_text(source)
        self.assertEqual(validate_titlepage(self.master, PAGE), [])
        self.assertNotIn('Later root text.', [e['text'] for e in titlepage_expectations(self.master)])

    def test_plain_prose_around_math_references_and_citations_remains_required(self):
        self.master.write_text(SOURCE.replace('A fitted separator has scientific significance.',
            r'A fitted $x_i$ separator (\ref{eq:later}) has scientific significance \citep{Example}.'))
        page = PAGE.replace('A fitted separator has scientific significance.',
                            'A fitted xᵢ separator (2) has scientific significance (Example, 2024).')
        self.assertEqual(validate_titlepage(self.master, page), [])
        self.assertTrue(any('[abstract]' in e for e in validate_titlepage(
            self.master, page.replace('scientific significance', 'OTHER'))))

    def test_math_only_abstract_has_no_vacuous_text_requirement(self):
        self.master.write_text(SOURCE.replace('A fitted separator has scientific significance.', '$x_i$'))
        self.assertEqual(validate_titlepage(self.master, PAGE.replace(
            'A fitted separator has scientific significance.', 'xᵢ')), [])

    def test_titlepage_source_reflow_preserves_declarations(self):
        self.master.write_text(SOURCE.replace('\n', ' '))
        self.assertEqual([e['text'] for e in titlepage_expectations(self.master) if e['role'] == 'declaration'],
                         ['Acknowledgments. Thanks to a careful reader.',
                          'Author contributions. Ada designed the study (ORCID: 0000-0000-1111-2222).'])
        self.assertEqual(validate_titlepage(self.master, PAGE), [])

    def test_cli_failure_uses_source_and_page_one_text(self):
        text = self.root / 'page.txt'
        text.write_text(PAGE.replace('52C22', '99Z99'))
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_manuscript_titlepage.py'),
                                 '--manuscript', str(self.master), '--text', str(text)],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[classification]', result.stdout + result.stderr)


@unittest.skipUnless((ROOT / 'manuscript/manuscript.pdf').is_file() and shutil.which('pdftotext'),
                     'canonical PDF and pdftotext are required for real extraction regressions')
class CanonicalTitlePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = ROOT / 'manuscript/manuscript.tex'
        cls.pdf_text = subprocess.run(
            ['pdftotext', str(cls.master.with_suffix('.pdf')), '-'],
            check=True, capture_output=True, text=True).stdout

    def test_unmodified_full_pdf_extraction_passes(self):
        self.assertGreater(self.pdf_text.count('\f'), 1)
        self.assertEqual(validate_titlepage(self.master, self.pdf_text), [])


class BibliographyPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bbl = Path(self.temp.name) / 'manuscript.bbl'

    def write(self, body):
        self.bbl.write_text(r'\providecommand{\bfpage}[1]{#1}' + '\n' +
                           r'\bibitem[Author {2025}]{Example}' + '\n' + body + '\n' +
                           r'\endbibitem' + '\n')

    def test_balanced_page_fields_derive_complete_alphanumeric_range(self):
        self.write(r'\bfpage{{D1516}} % harmless wrap' + '\n--' + r'\blpage{D1525}')
        self.assertEqual(bibliography_page_expectations(self.bbl),
                         [{'key': 'Example', 'first': 'D1516', 'last': 'D1525'}])
        for pdf in ('Reference D1516–D1525.', 'D1516 -- D1525', 'D1516\n—\nD1525'):
            with self.subTest(pdf=pdf):
                self.assertEqual(validate_bibliography_pages(self.bbl, pdf), [])

    def test_prefix_loss_or_range_corruption_is_rejected(self):
        self.write(r'\bfpage{D1516}--\blpage{D1525}')
        for pdf in ('1516–1525', 'D1516–1525', 'D1516–D1526', 'D1516 D1525', 'D15160–D15250'):
            with self.subTest(pdf=pdf):
                self.assertTrue(validate_bibliography_pages(self.bbl, pdf))

    def test_literal_note_range_covers_actual_springer_botherref_form(self):
        self.write(r'\begin{botherref}Journal title. pp. D1516--D1525\end{botherref}')
        self.assertEqual(bibliography_page_expectations(self.bbl),
                         [{'key': 'Example', 'first': 'D1516', 'last': 'D1525'}])
        self.assertTrue(validate_bibliography_pages(self.bbl, 'Journal title. pp. 1516–1525'))
        self.assertEqual(validate_bibliography_pages(self.bbl, '\fReferences\npp. D1516–D1525'), [])

    def test_single_alphanumeric_page_has_token_boundaries(self):
        self.write(r'\bfpage{D1}')
        self.assertEqual(validate_bibliography_pages(self.bbl, 'page D1.'), [])
        for pdf in ('page D10.', 'page AD1.', 'page 1.'):
            with self.subTest(pdf=pdf):
                self.assertTrue(validate_bibliography_pages(self.bbl, pdf))

    def test_numeric_pages_and_unmarked_title_numbers_do_not_add_new_claims(self):
        self.write(r'\batitle{Study D123 to D456}\bfpage{1516}--\blpage{1525}')
        self.assertEqual(bibliography_page_expectations(self.bbl), [])
        self.assertEqual(validate_bibliography_pages(self.bbl, ''), [])

    def test_unsupported_or_ambiguous_page_fields_fail_clearly(self):
        for body in (r'\bfpage{\unknown{D1}}', r'\bfpage{D1}\bfpage{D2}',
                     r'\blpage{D2}', r'\bfpage{D1}\blpage{D2}', r'\bfpage{D1'):
            with self.subTest(body=body):
                self.write(body)
                with self.assertRaises(ValueError):
                    bibliography_page_expectations(self.bbl)

    def test_cli_bbl_checks_full_text_beyond_first_page(self):
        root = Path(self.temp.name)
        master = root / 'manuscript.tex'
        master.write_text(SOURCE)
        text = root / 'document.txt'
        self.write(r'\bfpage{D1516}--\blpage{D1525}')
        command = [sys.executable, str(ROOT / 'scripts/check_manuscript_titlepage.py'),
                   '--manuscript', str(master), '--text', str(text), '--bbl', str(self.bbl)]
        text.write_text(PAGE + '\fReferences\nD1516–D1525')
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        text.write_text(PAGE + '\fReferences\n1516–1525')
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('bibliography pagination', result.stderr)


if __name__ == '__main__':
    unittest.main()
