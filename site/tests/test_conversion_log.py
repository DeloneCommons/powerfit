"""Reviewed math-parser warnings are a finite allowance, never a category waiver."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build import check_conversion_log


class ConversionLogTests(unittest.TestCase):
    def check(self, contents, allow=True):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'conversion.log'
            path.write_text(contents)
            check_conversion_log(path, allow_math_parser=allow)

    def test_reviewed_diagnostic_is_allowed(self):
        self.check("Warning:not_parsed:ATOM.ADDOP.ATOM>PERIOD MathParser failed to match rule 'Anything' at 02_separators.tex; line 17 col 0\n")

    def test_new_parser_diagnostic_or_location_is_rejected(self):
        for line in (
            "Warning:not_parsed:NEW MathParser failed to match rule 'Anything'",
            "Warning:not_parsed:ATOM.ADDOP.ATOM>PERIOD MathParser failed to match rule 'Anything' at 02_separators.tex; line 18 col 0",
        ):
            with self.subTest(line=line), self.assertRaises(RuntimeError):
                self.check(line)

    def test_extra_occurrence_is_rejected(self):
        line = "Warning:not_parsed:ATOM.ADDOP.ATOM>PERIOD MathParser failed to match rule 'Anything' at 02_separators.tex; line 17 col 0\n"
        with self.assertRaises(RuntimeError):
            self.check(line * 2)

    def test_other_warnings_errors_and_postprocess_warnings_are_rejected(self):
        for line, allow in [('Warning:unexpected', True), ('Error:undefined', True),
                            ('Fatal:failure', True), ('2 missing files', True),
                            ("Warning:not_parsed:UNKNOWN.CLOSE.CLOSE>POSTSUPERSCRIPT MathParser failed to match rule 'Anything'", False)]:
            with self.subTest(line=line), self.assertRaises(RuntimeError):
                self.check(line, allow)


if __name__ == '__main__':
    unittest.main()
