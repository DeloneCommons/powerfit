"""Finite warning approvals bind full diagnostics to independently read math."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import conversion_warnings as warnings


class ConversionLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binding = self.root / 'TeX.pool.ltxml'
        self.binding.write_text('reviewed binding')
        self.console = self.root / 'conversion.log'
        self.rich = self.root / 'article.latexml.log'
        self.approvals = self.root / 'reviewed.json'
        self.expression = r'\boxed{x^{2}=a+b.}'
        self.item = dict(id='m1', source='sections/example.tex', line=10, end_line=14,
                         mode='display', environment='equation', tex=self.expression, labels=['eq:sample'])
        self.inventory = {'math': [self.item], 'macro_context': 'approved-macros'}
        self.header = "Warning:not_parsed:ATOM>PERIOD MathParser failed to match rule 'Anything'"
        self.trace = 'x[[UNKNOWN]] ^{2}[[POSTSUPERSCRIPT]] =[[RELOP]] a[[UNKNOWN]] +[[ADDOP]] b[[UNKNOWN]]\n        > .[[PERIOD]]'
        self.block = self.header + '\n\tat example.tex; line 12 col 0 - line 12 col 4\n\tIn "' + self.expression + '"\n\t' + self.trace.replace('\n', '\n\t')
        self.policy = {'schema_version': 1, 'converter_version': '0.8.8', 'stage': 'conversion',
                       'binding_context': [{'name': self.binding.name, 'sha256': hashlib.sha256(self.binding.read_bytes()).hexdigest()}],
                       'expressions': [{'id': 'reviewed-sample', 'source_hint': self.item['source'],
                           'labels': ['eq:sample'], 'environment': 'equation',
                           'source_fingerprint': warnings.expression_fingerprint(self.expression, 'equation'),
                           'macro_context': 'approved-macros', 'review_reference': 'explicit fixture review',
                           'rationale': 'Parser punctuation issue; full presentation reviewed.',
                           'roles': [{'signature': 'not_parsed:ATOM>PERIOD', 'rule': 'Anything',
                                      'in_fingerprint': warnings.diagnostic_fingerprint(self.expression),
                                      'trace_fingerprint': warnings.diagnostic_fingerprint(self.trace),
                                      'location': 'source', 'max_occurrences': 1}]}]}
        self.write_logs()

    def write_logs(self, blocks=None, console_headers=None, summary_count=None):
        blocks = [self.block] if blocks is None else blocks
        headers = [self.header + ' at example.tex; line 12 col 0'] if console_headers is None else console_headers
        count = len(blocks) if summary_count is None else summary_count
        summary = f'Conversion complete: {count} warnings (See article.latexml.log) (reqd. 1s)\n'
        self.console.write_text('\n'.join(headers) + '\n' + summary)
        self.rich.write_text('latexml (LaTeXML version 0.8.8) processing article.tex\n(Loading ' + str(self.binding) + '... 0.1 sec)\n' + '\n'.join(blocks) + '\n(Finalizing... 0.1 sec)\n' + summary)
        self.approvals.write_text(json.dumps(self.policy))

    def check(self):
        return warnings.check_conversion_warnings(self.console, self.rich, self.inventory, 'latexml (LaTeXML version 0.8.8)', self.approvals)

    def test_reviewed_complete_diagnostic_matches_source(self):
        report = self.check()
        self.assertEqual(report['matched'][0]['expression'], 'reviewed-sample')
        self.assertEqual(report['matched'][0]['source']['line'], 10)

    def test_line_move_label_rename_and_source_reflow_keep_identity(self):
        self.item.update(line=110, end_line=114, labels=['eq:renamed'], source='appendices/moved.tex',
                         tex='\\boxed{ x ^{2} = a % comment\n + b. }\\label{eq:renamed}')
        self.block = self.block.replace('example.tex; line 12', 'moved.tex; line 112')
        self.write_logs(console_headers=[self.header + ' at moved.tex; line 112 col 0'])
        self.check()

    def test_unused_record_allows_disappeared_or_changed_expression(self):
        self.item['tex'] = 'y=z'
        self.write_logs(blocks=[], console_headers=[])
        self.assertEqual(self.check()['matched'], [])

    def test_changed_full_expression_with_old_diagnostic_fails(self):
        self.item['tex'] = self.expression.replace('+', '-')
        with self.assertRaisesRegex(RuntimeError, 'source|expression'):
            self.check()

    def test_duplicate_expression_attribution_fails(self):
        self.inventory['math'].append(dict(self.item, id='m2', line=50, end_line=54))
        with self.assertRaisesRegex(RuntimeError, 'ambiguous|unique'):
            self.check()

    def test_extra_occurrence_fails(self):
        self.write_logs(blocks=[self.block]*2, console_headers=[self.header + ' at example.tex; line 12 col 0']*2)
        with self.assertRaisesRegex(RuntimeError, 'cap|occurrence'):
            self.check()

    def test_version_change_fails_even_without_warnings(self):
        self.write_logs(blocks=[], console_headers=[])
        with self.assertRaisesRegex(RuntimeError, 'version'):
            warnings.check_conversion_warnings(self.console, self.rich, self.inventory, '0.8.9', self.approvals)

    def test_binding_or_macro_context_change_fails(self):
        for change in ('binding', 'macro'):
            with self.subTest(change=change):
                self.binding.write_text('changed' if change == 'binding' else 'reviewed binding')
                self.inventory['macro_context'] = 'changed' if change == 'macro' else 'approved-macros'
                with self.assertRaisesRegex(RuntimeError, 'context|binding'):
                    self.check()

    def test_unknown_error_and_malformed_headers_fail(self):
        for header in ('Warning:unexpected novel warning', 'Error:undefined missing macro', 'Fatal:failure stopped', 'Warning malformed'):
            with self.subTest(header=header):
                self.write_logs(blocks=[header], console_headers=[header])
                with self.assertRaises(RuntimeError):
                    self.check()

    def test_incomplete_blocks_and_token_traces_fail(self):
        for block in (self.header, self.header+'\n\tIn "unfinished', self.block.rsplit('\n', 1)[0], self.block.replace('b[[UNKNOWN]]', '')):
            with self.subTest(block=block):
                self.write_logs(blocks=[block])
                with self.assertRaises(RuntimeError):
                    self.check()

    def test_summary_and_console_reconciliation_fail_closed(self):
        for mode in ('summary', 'console', 'missing-footer', 'rich-version'):
            with self.subTest(mode=mode):
                self.write_logs(summary_count=2 if mode == 'summary' else 1,
                                console_headers=[] if mode == 'console' else None)
                if mode == 'missing-footer':
                    self.rich.write_text(self.rich.read_text().split('Conversion complete:')[0])
                if mode == 'rich-version':
                    self.rich.write_text(self.rich.read_text().replace('version 0.8.8', 'version 0.8.9'))
                with self.assertRaises(RuntimeError):
                    self.check()

    def test_locationless_role_binds_complete_aligned_display(self):
        self.item.update(environment='[]', tex=r'\begin{aligned}x^2&=a+b\\y&=z\end{aligned}', labels=[])
        record = self.policy['expressions'][0]
        record.update(environment='[]', source_fingerprint=warnings.expression_fingerprint(self.item['tex'], '[]'))
        record['roles'][0]['location'] = 'none'
        self.block = self.block.replace('\n\tat example.tex; line 12 col 0 - line 12 col 4', '')
        self.write_logs(console_headers=[self.header])
        self.check()
        self.item['tex'] = self.item['tex'].replace('y&=z', 'y&=-z')
        with self.assertRaisesRegex(RuntimeError, 'source|expression'):
            self.check()

    def test_starred_operator_name_has_stable_distinct_identity(self):
        fingerprint = warnings.expression_fingerprint
        self.assertEqual(fingerprint(r'\operatorname*{argmin}_{x}f(x)', 'equation'),
                         fingerprint(r'\operatorname* {argmin} _{x} f(x)', 'equation'))
        self.assertNotEqual(fingerprint(r'\operatorname*{argmin}_{x}f(x)', 'equation'),
                            fingerprint(r'\operatorname{argmin}_{x}f(x)', 'equation'))

    def test_failure_report_preserves_complete_diagnostic_and_source(self):
        self.item['tex'] = self.expression.replace('+', '-')
        report_path = self.root / 'warning-review.json'
        with self.assertRaises(RuntimeError):
            warnings.check_conversion_warnings(self.console, self.rich, self.inventory, '0.8.8',
                                               self.approvals, report_path)
        report = json.loads(report_path.read_text())
        self.assertIn(self.trace.splitlines()[0], report['diagnostics'][0]['raw'])
        self.assertEqual(report['source_candidates'][0]['tex'], self.item['tex'])
        self.assertTrue(report['unmatched'])

    def test_source_fingerprint_preserves_math_and_text_roles(self):
        fingerprint = warnings.expression_fingerprint
        self.assertEqual(fingerprint(r'a+b', 'equation'), fingerprint('a %x\n + b', 'equation'))
        for other in (r'a_b', r'a^{-b}', r'b+a', r'\frac{b}{a}', r'\text{ab}', r'\inx'):
            with self.subTest(other=other):
                self.assertNotEqual(fingerprint(r'\text{a b}+\in x+\frac{a}{b}+a^b', 'equation'), fingerprint(other, 'equation'))
        self.assertNotEqual(fingerprint(r'\text{a b}', 'equation'), fingerprint(r'\text{ab}', 'equation'))
        self.assertNotEqual(fingerprint(r'\in x', 'equation'), fingerprint(r'\inx', 'equation'))


if __name__ == '__main__':
    unittest.main()
