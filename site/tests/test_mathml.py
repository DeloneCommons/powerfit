"""Structural parity plus small expectations specified independently of LaTeXML."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from lxml import html
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mathml import presentation_structure


class MathStructureTests(unittest.TestCase):
    def signature(self, source):
        return presentation_structure(html.fromstring(source))

    def test_serialization_and_literal_zero_annotation_repair(self):
        self.assertEqual(self.signature('<math alttext="0"><mn>0</mn></math>'),
                         self.signature('<math alttext="0">\n<semantics><mn>0</mn><annotation encoding="application/x-tex">0</annotation></semantics>\n</math>'))
        self.assertNotEqual(self.signature('<math alttext="0"><mn>0</mn></math>'),
                            self.signature('<math alttext="0"><semantics><mi>0</mi><annotation encoding="application/x-tex">0</annotation></semantics></math>'))
        self.assertEqual(self.signature('<math><mo stretchy="false" form="prefix">(</mo></math>'),
                         self.signature('<math>\n<!-- serialization --> <mo form="prefix" stretchy="false">(</mo>\n</math>'))

    def test_structure_attributes_and_token_order_are_not_normalized_away(self):
        pairs = [
            ('<msup><mi>x</mi><mn>2</mn></msup>', '<msub><mi>x</mi><mn>2</mn></msub>'),
            ('<mfrac><mi>a</mi><mi>b</mi></mfrac>', '<mrow><mi>a</mi><mi>b</mi></mrow>'),
            ('<msqrt><mi>x</mi></msqrt>', '<mrow><mi>x</mi></mrow>'),
            ('<munder><mi>min</mi><mi>x</mi></munder>', '<mover><mi>min</mi><mi>x</mi></mover>'),
            ('<mrow><mi>a</mi><mi>b</mi></mrow>', '<mrow><mi>b</mi><mi>a</mi></mrow>'),
            ('<mi mathvariant="normal">R</mi>', '<mi mathvariant="bold">R</mi>'),
            ('<mtable columnalign="right"><mtr><mtd><mi>x</mi></mtd></mtr></mtable>',
             '<mtable columnalign="left"><mtr><mtd><mi>x</mi></mtd></mtr></mtable>'),
            ('<mtext>a b</mtext>', '<mtext>ab</mtext>'),
        ]
        for before, after in pairs:
            with self.subTest(before=before):
                self.assertNotEqual(self.signature('<math>' + before + '</math>'),
                                    self.signature('<math>' + after + '</math>'))


class RepresentativeMathTests(unittest.TestCase):
    """Spot-check high-risk roles, not full copies or symbolic equivalence.

    Expectations describe powers/roots, sum limits and a two-row minimum
    constraint directly; they are not harvested from converter output or TeX
    annotations. Review these three checks if the corresponding science changes.
    """
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / 'build/site/article.html'
        cls.page = html.parse(str(path))

    def math(self, key):
        nodes = self.page.xpath('//math[@id=$id]', id=key)
        self.assertEqual(len(nodes), 1)
        return nodes[0]

    def check_bound(self, node):
        self.assertEqual(len(node.xpath('.//msup[*[1][self::mi and .="w"] and *[2][self::mo and .="⋆"]]')), 2)
        self.assertEqual(len(node.xpath('.//msup[*[1][self::mi and .="R"]]/*[2][self::mrow and *[1][self::mn and .="1"] and *[2][self::mo and .="/"] and *[3][self::mn and .="2"]]')), 2)
        self.assertEqual(len(node.xpath('.//mfrac/*[2][self::msqrt]/msub[*[1][self::mi and .="λ"] and *[2][self::mi and .="min"]]')), 2)

    def check_sum(self, node):
        self.assertEqual(len(node.xpath('.//munderover[*[1][self::mo and .="∑"] and *[2][self::mrow and *[1][self::mi and .="r"] and *[2][self::mo and .="="] and *[3][self::mn and .="1"]] and *[3][self::mi and .="m"]]')), 1)
        self.assertEqual(len(node.xpath('.//msubsup[*[2][self::mn and .="2"] and *[3][self::mn and .="2"]]')), 1)

    def check_clearance(self, node):
        self.assertEqual(len(node.xpath('.//munder[*[1][self::mi and .="min"]]/*[2][self::mtable]/mtr')), 2)
        self.assertEqual(len(node.xpath('.//munder[*[1][self::mi and .="min"]]/following-sibling::*[1][self::mfrac]')), 1)
        self.assertEqual(len(node.xpath('./semantics/menclose[@notation="box"]')), 1)

    def test_appendix_c_bound_has_half_powers_and_square_root_denominators(self):
        self.check_bound(self.math('A3.E70.m1'))

    def test_appendix_c_sum_has_lower_and_upper_limits(self):
        self.check_sum(self.math('A3.E69.m1'))

    def test_clearance_minimum_has_two_constraint_rows_and_a_fraction(self):
        self.check_clearance(self.math('S4.E41.m1'))

    def test_role_swaps_fail_independent_expectations(self):
        # These checks must catch defects already present in converter output,
        # where converter/final parity and unchanged TeX annotations cannot help.
        for key, query, first, second, check in [
            ('A3.E70.m1', './/msup[mi="R"]', 0, 1, self.check_bound),
            ('A3.E69.m1', './/munderover', 1, 2, self.check_sum),
            ('S4.E41.m1', './/munder', 0, 1, self.check_clearance),
        ]:
            with self.subTest(key=key):
                node = deepcopy(self.math(key))
                for operator in node.xpath(query):
                    children = list(operator)
                    children[first], children[second] = children[second], children[first]
                    operator[:] = children
                with self.assertRaises(AssertionError):
                    check(node)


if __name__ == '__main__':
    unittest.main()
