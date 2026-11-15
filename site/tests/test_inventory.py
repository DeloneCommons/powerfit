"""Independent tiny manuscripts exercise supported authored-source semantics."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from inventory import read_inventory
    from mathsyntax import normalize_math
except ImportError:
    read_inventory = normalize_math = None


class InventoryTests(unittest.TestCase):
    def parse(self, body, files=None, preamble=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in (files or {}).items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            master = root / "manuscript.tex"
            if preamble is None:
                preamble = (
                    r"\newtheorem{proposition}{Proposition}\newtheorem{theorem}{Theorem}"
                    r"\newtheorem{corollary}{Corollary}\newtheorem{definition}{Definition}"
                    r"\newtheorem{remark}{Remark}"
                )
            master.write_text(
                "\\documentclass{article}"
                + preamble
                + "\n\\begin{document}\n"
                + body
                + "\n\\end{document}"
            )
            self.assertIsNotNone(read_inventory, "source inventory reader is not implemented")
            return read_inventory(master)

    def test_active_inputs_have_recursive_source_order_and_orphans_are_ignored(self):
        data = self.parse(
            r"\input{b}\input{a}",
            {
                "a.tex": r"\section{Last}Last.",
                "b.tex": r"\section{First}\input{nested/c}",
                "nested/c.tex": "First.",
                "unused.tex": "Never read.",
            },
        )
        self.assertEqual(
            [x["path"] for x in data["sources"]],
            ["manuscript.tex", "b.tex", "nested/c.tex", "a.tex"],
        )
        self.assertEqual(
            [x["title"][0]["text"] for x in data["objects"] if x["kind"] == "section"],
            ["First", "Last"],
        )
        self.assertNotIn("Never read", json.dumps(data))

    def test_short_mixed_proof_math_and_declaration_are_owned_and_ordered(self):
        data = self.parse(r"""\section{Claim}\label{sec:c}
Before $x_i$; see \eqref{eq:q} and \citep{One,Two}.
\begin{equation}q=\frac{x_i}{2}\label{eq:q}\end{equation}
After.
\begin{proof}It follows from $q>0$.\end{proof}
\subsection*{Funding}None.""")
        kinds = [x["kind"] for x in data["objects"]]
        self.assertEqual(
            kinds,
            [
                "document",
                "section",
                "prose",
                "equation",
                "prose",
                "proof",
                "prose",
                "subsection",
                "prose",
            ],
        )
        section = data["objects"][1]
        self.assertEqual(
            [
                data["objects"][int(t["id"][1:]) - 1]["kind"]
                for t in section["content"]
                if t["kind"] == "object"
            ],
            ["prose", "equation", "prose", "proof", "subsection"],
        )
        self.assertEqual(data["labels"]["sec:c"], section["id"])
        self.assertEqual(len(data["math"]), 3)
        self.assertTrue(data["math"][1]["numbered"])
        self.assertEqual(data["math"][1]["labels"], ["eq:q"])
        self.assertIn(
            {"kind": "cite", "command": "citep", "targets": ["One", "Two"]},
            data["objects"][2]["content"],
        )

    def test_align_numbering_nested_nonnumbering_and_pure_script(self):
        data = self.parse(r"""\section{Rows}
\begin{align}a&=b\\ c&=\begin{cases}1&x>0\\0&x\le0\end{cases}\notag\\ d&=e\label{eq:d}\end{align}
The $^\star$ marker.""")
        rows = [x for x in data["math"] if x["mode"] == "row"]
        self.assertEqual([x["numbered"] for x in rows], [True, False, True])
        self.assertEqual(rows[-1]["labels"], ["eq:d"])
        self.assertEqual(len(rows[1]["cells"]), 2)
        self.assertTrue(data["math"][-1]["pure_script"])

    def test_tables_figures_caption_and_cell_multiplicity(self):
        data = self.parse(r"""\section{Objects}
\begin{figure}\includegraphics[width=.8\linewidth]{figures/new.pdf}\caption{A $q$ plot.}\label{fig:q}\end{figure}
\begin{tabular}{lc}A & B\\ Same & Same\\\end{tabular}""")
        objects = data["objects"]
        graphic = next(x for x in objects if x["kind"] == "graphic")
        self.assertEqual(graphic["target"], "figures/new.pdf")
        cells = [x for x in objects if x["kind"] == "cell"]
        self.assertEqual([x["content"][0]["text"] for x in cells], ["A", "B", "Same", "Same"])
        self.assertEqual(len([x for x in objects if x["kind"] == "row"]), 2)

    def test_comments_escapes_balanced_arguments_and_ordinary_reflow(self):
        a = self.parse(
            "\\section{A {nested} title}\nA literal \\{brace\\} and 10\\% gain. % ignored $x$\nNext $x_{i}$."
        )
        b = self.parse(
            "\\section{A {nested} title}\nA literal \\{brace\\} and 10\\% gain. Next $x_i$."
        )
        self.assertEqual([x["content"] for x in a["objects"]], [x["content"] for x in b["objects"]])
        self.assertEqual(a["math"][0]["normalized"], b["math"][0]["normalized"])

    def test_unsupported_content_and_recursive_inputs_fail_closed(self):
        for body in (
            r"\unknown{lost}",
            r"\begin{unknown}lost\end{unknown}",
            r"$\newmath{x}$",
            r"\input{\dynamic}",
            r"\label{same}\label{same}",
            r"$x",
            r"\begin{proof}No end.",
        ):
            with (
                self.subTest(body=body),
                self.assertRaisesRegex(
                    ValueError, "Unsupported|unsupported|Duplicate|Unbalanced|Unclosed|cycle"
                ),
            ):
                self.parse(body)
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.parse(r"\input{a}", {"a.tex": r"\input{a}"})

    def test_actual_manuscript_grammar_is_covered_without_frozen_totals(self):
        self.assertIsNotNone(read_inventory, "source inventory reader is not implemented")
        root = Path(__file__).resolve().parents[2]
        data = read_inventory(root / "manuscript/manuscript.tex")
        self.assertTrue(data["math"])
        self.assertTrue(all(m["normalized"] and m["cells"] for m in data["math"]))
        self.assertTrue(any(m["numbered"] and not m["labels"] for m in data["math"]))
        self.assertTrue(any(m["pure_script"] for m in data["math"]))
        self.assertTrue(any(o["kind"] == "tabular" and not o["labels"] for o in data["objects"]))
        self.assertEqual(set(data["labels"]), {v for o in data["objects"] for v in o["labels"]})

    def test_math_serialization_aliases_and_nested_aligned_cells(self):
        from mathsyntax import math_cells

        self.assertEqual(
            normalize_math(r"\min_{\substack{i\ne j\\x>0}}x"),
            normalize_math(r"\min_{\begin{subarray}{c}i\neq j\\x>0\end{subarray}}x"),
        )
        self.assertEqual(
            math_cells(r"\begin{aligned}a&=b\\c&=d\end{aligned}"), ["a", "=b", "c", "=d"]
        )
        whole = r"\begin{aligned}a&=b\\c&=d\end{aligned}\qquad e=f"
        self.assertEqual(math_cells(whole), [whole])
        self.assertNotEqual(normalize_math(r"\text{ for all }"), normalize_math(r"\text{for all}"))

    def test_numbered_rows_and_heading_numbers_follow_supported_source_counters(self):
        data = self.parse(
            r"\section{A}\begin{equation}a=b\end{equation}"
            r"\begin{align}a&=b\nonumber\\c&=d\end{align}"
            r"\section*{Unnumbered}\appendix\section{B}\subsection{C}"
            r"\begin{equation*}x=y\end{equation*}\begin{equation}d=e\end{equation}"
        )
        self.assertEqual([m["number"] for m in data["math"] if m["numbered"]], [1, 2, 3])
        self.assertEqual(
            [o["number"] for o in data["objects"] if o["kind"] == "section"], ["1", None, "A"]
        )
        self.assertEqual(
            next(o for o in data["objects"] if o["kind"] == "subsection")["number"], "A.1"
        )

    def test_comment_newlines_join_text_without_creating_spaces(self):
        data = self.parse("\\section{A}ab% joined\ncd.")
        prose = next(o for o in data["objects"] if o["kind"] == "prose")
        self.assertEqual(prose["content"], [{"kind": "text", "text": "abcd."}])
        self.assertEqual(
            normalize_math("\\text{%\nnormalized coordinate}"),
            normalize_math(r"\text{normalized coordinate}"),
        )
        self.assertNotEqual(normalize_math(r"\text{a b}"), normalize_math(r"\text{ab}"))

    def test_statement_titles_notes_and_row_spans_preserve_mixed_content(self):
        data = self.parse(
            "\\section{A}\n\\begin{proposition}[A $q$ claim]Done.\\end{proposition}\n"
            "\\citep[see][p.~2]{One}.\\citet[p.~3]{Two}\n"
            "\\begin{align}a&=b\\\\[2pt]\nc&=d\\label{eq:d}\\end{align}\n"
            "\\begin{tabular}{lc}A&B\\tabularnewline\nC&D\\\\\\end{tabular}"
        )
        proposition = next(o for o in data["objects"] if o["kind"] == "proposition")
        self.assertEqual([t["kind"] for t in proposition["title"]], ["text", "math", "text"])
        cites = [t for o in data["objects"] for t in o["content"] if t["kind"] == "cite"]
        self.assertEqual((cites[0]["prenote"], cites[0]["postnote"]), ("see", "p.~2"))
        self.assertEqual((cites[1].get("prenote"), cites[1]["postnote"]), (None, "p.~3"))
        rows = [m for m in data["math"] if m["mode"] == "row"]
        self.assertEqual(rows[1]["line"], 7)
        cells = [o for o in data["objects"] if o["kind"] == "cell"]
        self.assertEqual([o["line"] for o in cells], [8, 8, 9, 9])
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.parse(r"$\text{\unknown{lost}}$")

    def test_no_width_control_words_consume_their_terminating_whitespace(self):
        data = self.parse(r"\texttt{realized\_\allowbreak same\_\allowbreak shift}")
        prose = next(o for o in data["objects"] if o["kind"] == "prose")
        self.assertEqual(prose["content"], [{"kind": "text", "text": "realized_same_shift"}])

    def test_unmapped_list_statement_citation_and_reference_forms_fail_closed(self):
        unsupported = [
            r"\begin{description}\item[Claim]Visible marker.\end{description}",
            r"\begin{itemize}[Custom]\item Text.\end{itemize}",
            r"\begin{enumerate}\item[Custom]Text.\end{enumerate}",
            r"\begin{lemma}An unmapped heading.\end{lemma}",
            r"\begin{claim}An unmapped heading.\end{claim}",
            r"\begin{observation}An unmapped heading.\end{observation}",
            r"\begin{proof}[Custom heading]Short proof.\end{proof}",
            r"\begin{gather}a=b\\c=d\end{gather}",
            r"\begin{multline}a+b\\=c\end{multline}",
            r"\cite{One}",
            r"\citealp{One}",
            r"\citeauthor{One}",
            r"\citeyear{One}",
            r"\autoref{sec:a}",
            r"\ref[Custom]{sec:a}",
            r"\eqref[Custom]{eq:a}",
            r"\section[Lost alternate $q$]{Heading}",
            r"\begin{figure}\caption[Lost alternate $q$]{Caption}\end{figure}",
        ]
        for body in unsupported:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, "Unsupported"):
                self.parse(body)
        supported = self.parse(
            r"\begin{itemize}\item A.\item B.\end{itemize}"
            r"\begin{enumerate}\item First.\end{enumerate}"
            r"\citep[see][p.~2]{One}\citet{Two}"
        )
        self.assertEqual(len([o for o in supported["objects"] if o["kind"] == "item"]), 3)

    def test_column_specs_and_nonprinting_table_rules_are_bounded_layout(self):
        unsupported = [
            r"\begin{tabular}{>{\textbf{Lost}}lc}A&B\\\end{tabular}",
            r"\begin{tabular}{@{Lost}lc}A&B\\\end{tabular}",
            r"\begin{tabular}{@{\newcommand{\q}{x}}lc}A&B\\\end{tabular}",
            r"\begin{tabular}{p{\scientificwidth}c}A&B\\\end{tabular}",
            r"\begin{tabular}{lc}\midrule[\scientific]A&B\\\end{tabular}",
            r"\begin{tabular}{lc}\cmidrule(\scientific){1-2}A&B\\\end{tabular}",
            r"\begin{tabular}{lc}\cmidrule{\scientific}A&B\\\end{tabular}",
            r"\begin{tabular}{lc}Only one column\\\end{tabular}",
        ]
        for body in unsupported:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, "Unsupported"):
                self.parse(body)
        data = self.parse(
            r"\begin{tabular}{@{}p{0.62\linewidth}p{0.31\linewidth}@{}}"
            r"\toprule A&B\\\cmidrule(lr){1-2}C&D\\\bottomrule\end{tabular}"
        )
        self.assertEqual(
            [o["columns"] for o in data["objects"] if o["kind"] == "tabular"],
            [r"@{}p{0.62\linewidth}p{0.31\linewidth}@{}"],
        )
        self.assertEqual(len([o for o in data["objects"] if o["kind"] == "cell"]), 4)

    def test_only_recognized_layout_lengths_can_be_discarded(self):
        unsupported = [
            r"\setlength{\scientific}{1pt}Important.",
            r"\setlength{\tabcolsep}{\scientific}Important.",
            r"\setlength{\tabcolsep}{1pt Important text}Important.",
            r"\Needspace{\scientific}Important.",
            r"\vspace{Important text}Important.",
            r"\enlargethispage{\newcommand{\q}{x}}Important.",
            r"\begin{minipage}{\scientific}Important.\end{minipage}",
            r"\includegraphics[trim=0 0 5 0,clip]{figures/a.pdf}",
            r"\begin{figure}[Lost $q$]\caption{Visible.}\end{figure}",
        ]
        for body in unsupported:
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, "Unsupported"):
                self.parse(body)
        data = self.parse(
            r"\setlength{\tabcolsep}{4.5pt}\Needspace{3\baselineskip}"
            r"\vspace{-28pt}\enlargethispage{\baselineskip}"
            r"\begin{minipage}{\linewidth}Important.\end{minipage}"
        )
        self.assertEqual(
            [o["content"] for o in data["objects"] if o["kind"] == "prose"],
            [[{"kind": "text", "text": "Important."}]],
        )

    def test_comment_join_discards_next_line_indentation_and_keeps_locations(self):
        data = self.parse("\\section{A}com% ignored\n    pact.\nNext $q$.")
        prose = next(o for o in data["objects"] if o["kind"] == "prose")
        self.assertEqual(prose["content"][0], {"kind": "text", "text": "compact. Next "})
        self.assertEqual(data["math"][0]["line"], 5)

    def test_statement_heading_and_per_environment_counters_come_from_original_preamble(self):
        data = self.parse(
            r"\section{A}\begin{proposition}First.\end{proposition}"
            r"\begin{corollary}Consequence.\end{corollary}"
            r"\begin{proposition}Second.\end{proposition}"
            r"\begin{proof}Done.\end{proof}",
            preamble="\\newtheorem\n{proposition}\n{Conjecture}\n"
            r"\newtheorem{corollary}{Consequence}",
        )
        statements = [
            o for o in data["objects"] if o["kind"] in ("proposition", "corollary", "proof")
        ]
        self.assertEqual(
            [(o["statement_heading"], o["number"]) for o in statements],
            [("Conjecture", 1), ("Consequence", 1), ("Conjecture", 2), ("Proof", None)],
        )
        self.assertEqual(
            data["theorem_definitions"], {"proposition": "Conjecture", "corollary": "Consequence"}
        )
        for declaration in (
            r"\newtheorem*{proposition}{Claim}",
            r"\newtheorem{proposition}[theorem]{Claim}",
            r"\newtheorem{proposition}{Claim}[section]",
            r"\newtheorem{proposition}{A $q$ claim}",
            r"\newtheorem{proposition}{\textbf{Claim}}",
            r"\newtheorem{proposition}{Claim}\newtheorem{proposition}{Duplicate}",
        ):
            with (
                self.subTest(declaration=declaration),
                self.assertRaisesRegex(ValueError, "Unsupported|Duplicate"),
            ):
                self.parse(r"\begin{proposition}A claim.\end{proposition}", preamble=declaration)
        with self.assertRaisesRegex(ValueError, "Unsupported.*undeclared"):
            self.parse(r"\begin{proposition}A claim.\end{proposition}", preamble="")

    def test_float_numbers_follow_actual_caption_occurrences_and_continue_in_appendix(self):
        data = self.parse(
            r"\section{A}\begin{figure}\caption{One.}\end{figure}"
            r"\begin{table}\caption{A.}\begin{tabular}{l}Cell\\\end{tabular}\end{table}"
            r"\appendix\section{B}\begin{figure}\caption{Two.}\end{figure}"
            r"\begin{tabular}{l}Unnumbered\\\end{tabular}"
        )
        self.assertEqual([o["number"] for o in data["objects"] if o["kind"] == "figure"], [1, 2])
        self.assertEqual([o["number"] for o in data["objects"] if o["kind"] == "table"], [1])
        self.assertEqual(
            [o["number"] for o in data["objects"] if o["kind"] == "caption"], [1, 1, 2]
        )
        self.assertTrue(all("number" not in o for o in data["objects"] if o["kind"] == "tabular"))
        for body in (
            r"\begin{figure}\caption{First}\caption{Second}\end{figure}",
            r"\begin{table}Uncaptioned float.\end{table}",
            r"\caption{Outside any float}",
        ):
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, "Unsupported"):
                self.parse(body)

    def test_comment_join_keeps_control_word_token_boundaries(self):
        data = self.parse("\\AA% ignored\n    B.")
        prose = next(o for o in data["objects"] if o["kind"] == "prose")
        self.assertEqual(prose["content"], [{"kind": "text", "text": "ÅB."}])
        with self.assertRaisesRegex(ValueError, r"Unsupported.*\\al(?: |$)"):
            self.parse("$\\al% ignored\n    pha$")

    def test_reference_comma_is_literal_but_citation_comma_separates_keys(self):
        data = self.parse(
            r"\section{A}\label{sec:a,b}"
            r"Section~\ref{sec:a,b}; Eq.~\eqref{eq:a,b}; \citep{One,Two}."
            r"\begin{equation}x=y.\label{eq:a,b}\end{equation}"
        )
        tokens = [
            t
            for o in data["objects"]
            for t in o["content"]
            if t["kind"] in ("ref", "eqref", "cite")
        ]
        self.assertEqual(
            [(t["kind"], t["targets"]) for t in tokens],
            [("ref", ["sec:a,b"]), ("eqref", ["eq:a,b"]), ("cite", ["One", "Two"])],
        )
        for token in tokens[:2]:
            self.assertIn(token["targets"][0], data["labels"])

    def test_math_normalization_preserves_roles_operators_order_and_text_spacing(self):
        self.assertIsNotNone(normalize_math, "math normalizer is not implemented")
        for left, right in (
            (r"x_i", r"x_{i}"),
            (r"\frac12", r"\frac{1}{2}"),
            (r"\mathbb R", r"\mathbb{R}"),
            (r"\le", r"\leq"),
        ):
            self.assertEqual(normalize_math(left), normalize_math(right))
        for left, right in (
            (r"x_i", r"x^i"),
            (r"\frac{a}{b}", r"\frac{b}{a}"),
            ("a+b", "a-b"),
            (r"\sqrt{x}", r"x"),
            ("a+b", "b+a"),
            (r"\text{a b}", r"\text{ab}"),
            ("(a+b)c", "a+bc"),
        ):
            self.assertNotEqual(normalize_math(left), normalize_math(right))


if __name__ == "__main__":
    unittest.main()
