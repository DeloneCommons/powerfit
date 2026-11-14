"""Guard the generated wrapper against omissions and stale copied science."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source import make_wrapper, source_metadata
ROOT = Path(__file__).resolve().parents[2]

class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'manuscript/manuscript.tex').read_text()

    def test_current_front_matter_is_extracted_without_a_second_copy(self):
        meta = source_metadata(self.source)
        self.assertEqual(meta['author'], 'Ivan Yu. Chernyshov')
        self.assertEqual(meta['title'], 'Fixed-site inverse fitting of power-diagram weights from pairwise separator data')
        changed = self.source.replace('Local estimates of where', 'Revised estimates of where')
        self.assertIn('Revised estimates of where', make_wrapper(changed))
        self.assertNotIn('Local estimates of where', make_wrapper(changed))

    def test_every_include_and_declaration_survives(self):
        wrapper = make_wrapper(self.source)
        self.assertEqual(wrapper.count(r'\input{sections/'), 9)
        self.assertEqual(wrapper.count(r'\input{appendices/'), 5)
        self.assertIn('The author remains responsible', wrapper)
        self.assertIn('his mother for unconditional support', wrapper)
        self.assertIn(r'\input{manuscript.bbl}', wrapper)
        self.assertNotIn(r'\begin{minipage}', wrapper)

    def test_additional_author_fails_instead_of_silently_disappearing(self):
        extra = self.source.replace(r'\affil*[1]', r'\author*[2]{\fnm{Another} \sur{Author}}' + '\n' + r'\affil*[1]')
        with self.assertRaisesRegex(ValueError, 'front matter'):
            make_wrapper(extra)

    def test_unsupported_front_matter_fails_instead_of_disappearing(self):
        with self.assertRaisesRegex(ValueError, 'front matter'):
            make_wrapper(self.source.replace(r'\maketitle', r'\differenttitle'))

if __name__ == '__main__':
    unittest.main()
