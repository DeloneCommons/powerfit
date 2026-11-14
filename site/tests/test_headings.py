"""Paragraph headings follow actual section parents without restyling or renaming."""
import sys
import unittest
from pathlib import Path
from lxml import html
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render import normalize_paragraph_headings


class HeadingTests(unittest.TestCase):
    def test_paragraphs_follow_subsection_or_subsubsection_parents(self):
        doc = html.fromstring('''<article><section><h2>Section</h2>
          <section><h3>Subsection</h3>
            <section id="paragraph"><h5 class="ltx_title ltx_title_paragraph" id="heading">Paragraph <em>text</em></h5></section>
            <section><h5 class="ltx_title_paragraph">Another paragraph</h5></section>
            <section><h4>Subsubsection</h4><section><h5 class="ltx_title_paragraph">Nested paragraph</h5></section></section>
          </section></section></article>''')
        before = [(n.get('id'), n.get('class'), ''.join(n.itertext())) for n in doc.xpath('//*[contains(@class,"ltx_title_paragraph")]')]
        normalize_paragraph_headings(doc)
        headings = doc.xpath('//*[contains(@class,"ltx_title_paragraph")]')
        self.assertEqual([n.tag for n in headings], ['h4', 'h4', 'h5'])
        self.assertEqual([(n.get('id'), n.get('class'), ''.join(n.itertext())) for n in headings], before)
        self.assertEqual(doc.get_element_by_id('heading').getparent().get('id'), 'paragraph')


if __name__ == '__main__':
    unittest.main()
