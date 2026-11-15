"""Tiny authored inputs check TeX file/token boundaries and source coordinates."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inventory import read_inventory


PREAMBLE = (
    "\\documentclass{article}\n"
    "\\usepackage[T1]{fontenc}\n"
    "\\usepackage{lmodern}\n"
    "\\usepackage{amsmath}\n"
    "\\pagestyle{empty}\n"
    "\\begin{document}\n"
)
PLAIN_CASES = (
    ("implicit-endline", r"\input{piece}bar.", "foo", "foo bar."),
    ("explicit-endline", r"\input{piece}bar.", "foo\n", "foo bar."),
    ("comment-at-eof", r"\input{piece}bar.", "foo% hidden", "foobar."),
    ("comment-before-lf", r"\input{piece}bar.", "foo% hidden\n", "foobar."),
    ("comment-before-input", "\\AA% hidden\n\\input{piece}", "B.\n", "ÅB."),
    ("command-before-input", r"\AA\input{piece}", "B.\n", "ÅB."),
    ("input-leading-space", r"\AA\input{piece}", " B.\n", "ÅB."),
    ("input-leading-indent", r"foo\input{piece}", " B.\n", "fooB."),
    ("input-return-space", r"\input{piece} B.", "\\AA\n", "Å B."),
    ("word-at-input-eof", r"\input{piece}B.", r"foo\AA% hidden", "fooÅB."),
    ("control-space", "foo\\\nbar.", "", "foo bar."),
    ("control-space-at-eof", r"\input{piece}bar.", "foo\\", "foo bar."),
)
DISPLAY = r"\[\begin{aligned}a&=b\\]&=c\end{aligned}\]After."


class InputBoundaryTests(unittest.TestCase):
    def fixture(self, body, piece):
        temporary = tempfile.TemporaryDirectory(prefix="powerfit-input-boundary-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "piece.tex").write_text(piece, encoding="utf-8")
        master = root / "manuscript.tex"
        master.write_text(PREAMBLE + body + "\n\\end{document}\n", encoding="utf-8")
        return master

    def test_literal_input_boundaries_preserve_visible_text(self):
        for name, body, piece, expected in PLAIN_CASES:
            with self.subTest(name=name):
                inventory = read_inventory(self.fixture(body, piece))
                prose = [item for item in inventory["objects"] if item["kind"] == "prose"]
                self.assertEqual(len(prose), 1)
                self.assertEqual(prose[0]["content"], [{"kind": "text", "text": expected}])

    def test_nested_input_keeps_boundary_after_a_comment_terminated_control_word(self):
        master = self.fixture(r"\input{piece}B.", r"foo\input{nested}% hidden")
        (master.parent / "nested.tex").write_text(r"\AA% hidden", encoding="utf-8")
        inventory = read_inventory(master)
        prose = next(item for item in inventory["objects"] if item["kind"] == "prose")
        self.assertEqual(prose["content"], [{"kind": "text", "text": "fooÅB."}])

    def test_empty_input_preserves_tex_paragraph_boundary(self):
        inventory = read_inventory(self.fixture(r"\AA\input{piece}B.", ""))
        self.assertEqual(
            [item["content"] for item in inventory["objects"] if item["kind"] == "prose"],
            [[{"kind": "text", "text": "Å"}], [{"kind": "text", "text": "B."}]],
        )

    def test_input_and_control_space_preserve_original_math_coordinates(self):
        inventory = read_inventory(
            self.fixture("\\AA% hidden\n\\input{piece}bar $r$.", "B.\\\n$q$")
        )
        self.assertEqual(
            [(item["source"], item["line"], item["end_line"]) for item in inventory["math"]],
            [("piece.tex", 2, 2), ("manuscript.tex", 8, 8)],
        )

    def test_input_does_not_turn_an_unsupported_control_word_into_a_known_one(self):
        master = self.fixture("$\\al% hidden\n\\input{piece}$", "pha% hidden")
        with self.assertRaisesRegex(ValueError, r"Unsupported.*\\al(?: |$)"):
            read_inventory(master)

    def test_rowbreak_followed_by_bracket_does_not_close_display(self):
        inventory = read_inventory(self.fixture(DISPLAY, ""))
        self.assertEqual(len(inventory["math"]), 1)
        self.assertEqual(
            inventory["math"][0]["tex"], r"\begin{aligned}a&=b\\]&=c\end{aligned}"
        )
        prose = next(item for item in inventory["objects"] if item["kind"] == "prose")
        self.assertEqual(prose["content"], [{"kind": "text", "text": "After."}])

    def test_rowbreak_bracket_without_closing_command_fails_closed(self):
        master = self.fixture(r"\[\begin{aligned}a&=b\\]&=c\end{aligned}", "")
        with self.assertRaisesRegex(ValueError, "Unclosed display mathematics"):
            read_inventory(master)

    @unittest.skipUnless(shutil.which("pdflatex") and shutil.which("pdftotext"), "TeX tools unavailable")
    def test_boundary_expectations_are_corroborated_by_actual_tex(self):
        cases = PLAIN_CASES + (
            ("empty-input", r"\AA\input{piece}B.", "", "Å B."),
            ("display-rowbreak-bracket", DISPLAY, "", "a=b ]=c After."),
        )
        for name, body, piece, expected in cases:
            with self.subTest(name=name):
                master = self.fixture(body, piece)
                compiled = subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", master.name],
                    cwd=master.parent,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(compiled.returncode, 0, compiled.stdout[-2000:])
                extracted = subprocess.run(
                    ["pdftotext", "-enc", "UTF-8", str(master.with_suffix(".pdf")), "-"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                self.assertEqual(unicodedata.normalize("NFC", " ".join(extracted.stdout.split())), expected)


if __name__ == "__main__":
    unittest.main()
