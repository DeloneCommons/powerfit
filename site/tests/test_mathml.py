"""Structural parity plus small expectations specified independently of LaTeXML."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from lxml import etree, html
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mathml import presentation_structure
from scientific import resolve_scientific_math, scientific_math_errors, validate_scientific_math


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
        cls.xml = etree.parse(str(path.parents[1] / 'site-work/article.xml'))

    def math(self, label):
        self.assertIsNotNone(resolve_scientific_math, 'reviewed mathematical-role resolver is not implemented')
        return resolve_scientific_math(self.xml, self.page, label)

    def check_bound(self, node):
        self.assertEqual(scientific_math_errors('eq:reduced-spectral-bound', node), [])

    def check_sum(self, node):
        self.assertEqual(scientific_math_errors('eq:measurement-error-energy', node), [])

    def check_clearance(self, node):
        self.assertEqual(scientific_math_errors('eq:connector-clearance', node), [])

    def test_appendix_c_bound_has_half_powers_and_square_root_denominators(self):
        self.check_bound(self.math('eq:reduced-spectral-bound'))

    def test_appendix_c_sum_has_lower_and_upper_limits(self):
        self.check_sum(self.math('eq:measurement-error-energy'))

    def test_clearance_minimum_has_two_constraint_rows_and_a_fraction(self):
        self.check_clearance(self.math('eq:connector-clearance'))

    def test_role_swaps_fail_independent_expectations(self):
        # These checks must catch defects already present in converter output,
        # where converter/final parity and unchanged TeX annotations cannot help.
        for key, query, first, second, check in [
            ('eq:reduced-spectral-bound', './/msup[mi="R"]', 0, 1, self.check_bound),
            ('eq:measurement-error-energy', './/munderover', 1, 2, self.check_sum),
            ('eq:connector-clearance', './/munder', 0, 1, self.check_clearance),
        ]:
            with self.subTest(key=key):
                node = deepcopy(self.math(key))
                operators = node.xpath(query)
                self.assertTrue(operators, "role-swap mutation target must exist")
                before = etree.tostring(node)
                for operator in operators:
                    children = list(operator)
                    children[first], children[second] = children[second], children[first]
                    operator[:] = children
                self.assertNotEqual(etree.tostring(node), before)
                with self.assertRaises(AssertionError):
                    check(node)
                page = deepcopy(self.page)
                original = resolve_scientific_math(self.xml, page, key)
                original.getparent().replace(original, node)
                errors = validate_scientific_math(self.xml, page)
                self.assertTrue(any('Scientific MathML role mismatch' in error and key in error for error in errors), errors)

    def test_generated_ids_can_change_without_changing_reviewed_roles(self):
        xml, page = deepcopy(self.xml), deepcopy(self.page)
        changed = 0
        for label in ('eq:connector-clearance', 'eq:measurement-error-energy', 'eq:reduced-spectral-bound'):
            source = xml.xpath('//*[@labels=$label]', label='LABEL:' + label)
            self.assertEqual(len(source), 1)
            maths = source[0].xpath('.//l:Math', namespaces={'l':'http://dlmf.nist.gov/LaTeXML'})
            self.assertEqual(len(maths), 1)
            math = maths[0]
            old = math.get('{http://www.w3.org/XML/1998/namespace}id')
            nodes = page.xpath('//math[@id=$key]', key=old)
            self.assertEqual(len(nodes), 1)
            math.set('{http://www.w3.org/XML/1998/namespace}id', 'revised.' + label)
            nodes[0].set('id', 'revised.' + label)
            changed += 1
        self.assertEqual(changed, 3)
        self.assertIsNotNone(validate_scientific_math, 'reviewed mathematical-role validation is not implemented')
        self.assertEqual(validate_scientific_math(xml, page), [])

    def test_all_reviewed_labels_can_be_renamed_without_changing_science(self):
        xml = deepcopy(self.xml)
        for label in ('eq:connector-clearance', 'eq:measurement-error-energy', 'eq:reduced-spectral-bound'):
            owners = xml.xpath('//*[@labels=$label]', label='LABEL:' + label)
            self.assertEqual(len(owners), 1)
            owners[0].set('labels', 'LABEL:renamed:' + label)
            self.assertNotEqual(owners[0].get('labels'), 'LABEL:' + label)
        self.assertEqual(validate_scientific_math(xml, self.page), [])

    def test_each_independent_role_rejects_a_targeted_mutation(self):
        # Each target is specified independently of production's role table.
        mutations = [
            ('eq:reduced-spectral-bound', './/msup[mi="w"]/mo', 'text', 'x', 'two starred weights'),
            ('eq:reduced-spectral-bound', './/msup[mi="R"]/mrow/mn', 'text', '3', 'two half powers of R'),
            ('eq:reduced-spectral-bound', './/mfrac/msqrt', 'tag', 'mrow', 'two square-root minimum-eigenvalue denominators'),
            ('eq:measurement-error-energy', './/munderover/mrow/mn', 'text', '0', 'sum lower and upper limits'),
            ('eq:measurement-error-energy', './/msubsup/mn', 'text', '3', 'squared two-norm'),
            ('eq:connector-clearance', './/munder/mtable/mtr', 'remove', '', 'two minimum constraint rows'),
            ('eq:connector-clearance', './/munder/following-sibling::mfrac', 'tag', 'mrow', 'fraction following minimum'),
            ('eq:connector-clearance', './semantics/menclose', 'notation', 'circle', 'boxed clearance'),
        ]
        for label, query, action, value, role in mutations:
            with self.subTest(label=label, role=role):
                page = deepcopy(self.page)
                node = resolve_scientific_math(self.xml, page, label)
                targets = node.xpath(query)
                self.assertTrue(targets, 'mathematical-role mutation target must exist')
                target = targets[0]
                before = etree.tostring(node)
                if action == 'remove':
                    target.getparent().remove(target)
                elif action == 'notation':
                    target.set('notation', value)
                else:
                    setattr(target, action, value)
                self.assertNotEqual(etree.tostring(node), before)
                errors = validate_scientific_math(self.xml, page)
                self.assertTrue(any('Scientific MathML role mismatch' in error and label in error and role in error for error in errors), errors)


class ScientificResolutionTests(unittest.TestCase):
    def test_missing_label_and_missing_formula_require_review(self):
        self.assertIsNotNone(validate_scientific_math, 'reviewed mathematical-role validation is not implemented')
        errors = validate_scientific_math(etree.fromstring('<document/>'), html.fromstring('<article/>'))
        for label in ('eq:connector-clearance', 'eq:measurement-error-energy', 'eq:reduced-spectral-bound'):
            self.assertTrue(any(label in error and 'review' in error.lower() for error in errors), errors)


class ScientificLocatorFixtureTests(unittest.TestCase):
    """Small, hand-specified fixtures keep locator failures independent of builds."""
    def setUp(self):
        self.label = 'eq:measurement-error-energy'
        self.xml = etree.fromstring(r'''<document xmlns="http://dlmf.nist.gov/LaTeXML"><equation labels="LABEL:eq:measurement-error-energy"><Math xml:id="fixture.energy" tex="\|R^{1/2}\eta\|_2^2=\sum_{r=1}^m\lambda_r(\Delta y_r)^2."/></equation></document>''')
        self.page = html.fromstring('''<article><math id="fixture.energy"><semantics><mrow>
          <msubsup><mi>N</mi><mn>2</mn><mn>2</mn></msubsup><mo>=</mo>
          <munderover><mo>∑</mo><mrow><mi>r</mi><mo>=</mo><mn>1</mn></mrow><mi>m</mi></munderover>
        </mrow></semantics></math></article>''')
        self.assertIsNotNone(resolve_scientific_math, 'reviewed mathematical-role resolver is not implemented')

    def resolve(self):
        return resolve_scientific_math(self.xml, self.page, self.label)

    def test_hand_specified_roles_and_unique_label_resolution(self):
        self.assertEqual(scientific_math_errors(self.label, self.resolve()), [])

    def test_label_only_rename_uses_unique_unchanged_source_identity(self):
        self.xml[0].set('labels', 'LABEL:eq:renamed-energy')
        self.assertEqual(self.resolve().get('id'), 'fixture.energy')

    def test_comments_line_wraps_and_redundant_script_braces_preserve_identity(self):
        self.xml[0][0].set('tex', r'''\|R^{1/2}\eta\|_{2}^{2} = % harmless source formatting
          \sum_{r=1}^{m}\lambda_{r}(\Delta y_{r})^{2}.''')
        self.assertEqual(self.resolve().get('id'), 'fixture.energy')

    def test_duplicate_source_label_fails(self):
        self.xml.append(deepcopy(self.xml[0]))
        with self.assertRaisesRegex(ValueError, 'ambiguous source label'):
            self.resolve()

    def test_duplicate_source_math_fails(self):
        self.xml[0].append(deepcopy(self.xml[0][0]))
        with self.assertRaisesRegex(ValueError, 'expected one source Math, found 2'):
            self.resolve()

    def test_duplicate_rename_fingerprint_fails(self):
        self.xml[0].set('labels', 'LABEL:eq:renamed-energy')
        self.xml.append(deepcopy(self.xml[0]))
        self.assertEqual(len(self.xml), 2)
        with self.assertRaisesRegex(ValueError, 'unchanged reviewed expression has 2 matches'):
            self.resolve()

    def test_duplicate_xml_identifier_fails_even_with_a_unique_label(self):
        other = etree.SubElement(self.xml, '{http://dlmf.nist.gov/LaTeXML}equation')
        other_math = etree.SubElement(other, '{http://dlmf.nist.gov/LaTeXML}Math')
        other_math.set('{http://www.w3.org/XML/1998/namespace}id', 'fixture.energy')
        other_math.set('tex', 'x+y')
        self.assertEqual(len(self.xml), 2)
        with self.assertRaisesRegex(ValueError, 'ambiguous XML Math identifier'):
            self.resolve()

    def test_duplicate_rendered_id_fails(self):
        self.page.append(deepcopy(self.page[0]))
        with self.assertRaisesRegex(ValueError, 'expected one rendered math.*found 2'):
            self.resolve()

    def test_missing_rendered_math_fails(self):
        self.page.remove(self.page[0])
        self.assertEqual(len(self.page), 0)
        with self.assertRaisesRegex(ValueError, 'expected one rendered math.*found 0'):
            self.resolve()

    def test_changed_reviewed_expression_requires_review_even_if_roles_still_pass(self):
        math = self.xml[0][0]
        before = math.get('tex')
        self.assertIn('\\Delta y_r', before)
        math.set('tex', before.replace('\\Delta y_r', '\\Delta z_r'))
        self.assertNotEqual(math.get('tex'), before)
        self.assertEqual(scientific_math_errors(self.label, self.page[0]), [])
        errors = validate_scientific_math(self.xml, self.page)
        self.assertTrue(any(self.label in error and 'reviewed source expression changed' in error for error in errors), errors)

    def test_renamed_changed_or_removed_expression_requires_review(self):
        self.xml[0].set('labels', 'LABEL:eq:renamed-energy')
        self.xml[0][0].set('tex', 'x+y')
        with self.assertRaisesRegex(ValueError, 'review required.*unchanged reviewed expression has 0 matches'):
            self.resolve()

    def test_sum_limit_swap_reports_reviewed_role_error(self):
        operator = self.page.xpath('.//munderover')
        self.assertEqual(len(operator), 1)
        before = etree.tostring(operator[0])
        children = list(operator[0])
        children[1], children[2] = children[2], children[1]
        operator[0][:] = children
        self.assertNotEqual(etree.tostring(operator[0]), before)
        errors = validate_scientific_math(self.xml, self.page)
        self.assertTrue(any('Scientific MathML role mismatch' in error and self.label in error and 'sum lower and upper limits' in error for error in errors), errors)


if __name__ == '__main__':
    unittest.main()
