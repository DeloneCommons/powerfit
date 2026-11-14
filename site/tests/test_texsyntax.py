"""Hand-derived lexical cases shared by bounded manuscript readers."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from texsyntax import command_at, group, skip_space, strip_comments


class LexicalTests(unittest.TestCase):
    def test_comments_respect_control_symbols(self):
        self.assertEqual(strip_comments('one%hidden\ntwo\\% kept\nthree\\\\%hidden\n'),
                         'one\ntwo\\% kept\nthree\\\\\n')

    def test_commands_are_tokens_not_substrings(self):
        self.assertEqual(command_at(r'\titleextra{x}', 0), ('titleextra', 11))
        self.assertEqual(command_at(r'\{text}', 0), ('{', 2))
        with self.assertRaisesRegex(ValueError, 'command'):
            command_at('text', 0)

    def test_groups_balance_nesting_and_control_symbols(self):
        self.assertEqual(group(r'{A {nested} \{literal\} \\}tail', 0),
                         (r'A {nested} \{literal\} \\', 27))
        self.assertEqual(group('[a{]}[b]]tail', 0, '[', ']'), ('a{]}[b]', 9))
        self.assertEqual(skip_space(' \n x', 0), 3)

    def test_unclosed_groups_fail(self):
        for text in ('{missing', r'{escaped\}', '[missing'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'Unbalanced'):
                group(text, 0, text[0], '}' if text[0] == '{' else ']')


if __name__ == '__main__':
    unittest.main()
