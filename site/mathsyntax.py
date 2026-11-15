"""Bounded syntactic math identity, deliberately without TeX macro expansion.

The serialized token tree retains argument roles, scripts, environments, row/cell
boundaries, delimiters and text spaces. Only sizing, formatting whitespace,
documented command aliases and redundant single-atom braces are normalized.
"""

import json
import re
from texsyntax import command_at, group, skip_space, strip_comments

ALIASES = {
    "leq": "le",
    "geq": "ge",
    "neq": "ne",
    "to": "rightarrow",
    "lnot": "neg",
    "varnothing": "emptyset",
    "Vert": "|",
    "lVert": "|",
    "rVert": "|",
}
SYMBOLS = set(
    """alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega in notin ni le ge ne approx sim simeq equiv cong propto ll gg subset subseteq supset supseteq cap cup setminus emptyset forall exists nexists neg land lor wedge vee infty partial nabla ell hbar imath jmath prime star ast circ bullet cdot times div pm mp perp parallel angle degree ldots cdots vdots ddots dots therefore because mapsto rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow Longrightarrow Longleftarrow Longleftrightarrow top bot Re Im wp aleph backslash lbrace rbrace langle rangle lceil rceil lfloor rfloor vert det dim gcd hom ker log ln exp sin cos tan tanh sinh cosh min max inf sup lim liminf limsup sum prod int iint iiint oint bigcup bigcap limits nolimits displaystyle textstyle scriptstyle scriptscriptstyle colon mid models square triangle triangleq overrightarrow underbrace overbrace AA""".split()
)
UNARY = set(
    "mathrm mathbf mathbb mathcal mathsf mathtt mathit mathnormal mathfrak boldsymbol operatorname text textrm textbf textit mbox underline overline widehat widetilde hat tilde bar vec dot ddot boxed substack phantom hphantom vphantom".split()
)
TEXT = {"text", "textrm", "textbf", "textit", "mbox", "operatorname"}
SIZING = set(
    "left right middle big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr Biggl Biggr".split()
)
SPACING = {",", ";", ":", "!", " ", "quad", "qquad", "enspace", "thinspace", "allowbreak"}
MATH_ENVS = {
    "aligned",
    "alignedat",
    "cases",
    "gathered",
    "split",
    "matrix",
    "pmatrix",
    "bmatrix",
    "vmatrix",
    "Vmatrix",
    "smallmatrix",
    "subarray",
}


def split_top_level(tex, separators=("\\\\", "&"), *, spans=False):
    """Split separators outside groups and nested environments; keep empty cells."""
    result, start, pos, depth, envs = [], 0, 0, 0, []
    while pos < len(tex):
        char = tex[pos]
        if char == "\\":
            name, end = command_at(tex, pos)
            if name in ("begin", "end"):
                value, finish = group(tex, skip_space(tex, end))
                if name == "begin":
                    envs.append(value)
                elif not envs or envs.pop() != value:
                    raise ValueError("Unbalanced mathematical environment")
                pos = finish
                continue
            if name == "\\" and not depth and not envs and "\\\\" in separators:
                result.append((tex[start:pos], start, pos) if spans else tex[start:pos])
                start = end
                # A literal optional row-spacing argument is layout, not a new cell.
                if start < len(tex) and tex[start] == "[":
                    _, start = group(tex, start, "[", "]")
                pos = start
                continue
            if name == "tabularnewline" and not depth and not envs and "\\\\" in separators:
                result.append((tex[start:pos], start, pos) if spans else tex[start:pos])
                start = end
                pos = end
                continue
            pos = end
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced mathematical group")
        elif char == "&" and not depth and not envs and "&" in separators:
            result.append((tex[start:pos], start, pos) if spans else tex[start:pos])
            start = pos + 1
        pos += 1
    if depth or envs:
        raise ValueError("Unbalanced mathematical group/environment")
    result.append((tex[start:], start, len(tex)) if spans else tex[start:])
    return result


class _Math:
    def __init__(self, text):
        self.text = strip_comments(text)
        self.pos = 0

    def sequence(self, stop=None):
        values = []
        while True:
            self.pos = skip_space(self.text, self.pos)
            if self.pos >= len(self.text):
                if stop:
                    raise ValueError("Unbalanced mathematical group")
                break
            if self.text[self.pos] == "}":
                if stop != "}":
                    raise ValueError("Unbalanced mathematical group")
                self.pos += 1
                break
            if self.text[self.pos] in "^_":
                role = self.text[self.pos]
                self.pos += 1
                value = self.argument()
                base = values.pop() if values else ["empty"]
                values.append(["script", role, base, value])
                continue
            atom = self.atom()
            if atom is not None:
                values.append(atom)
        return values

    def argument(self):
        self.pos = skip_space(self.text, self.pos)
        if self.pos >= len(self.text):
            raise ValueError("Unbalanced mathematical argument")
        if self.text[self.pos] == "{":
            self.pos += 1
            value = self.sequence("}")
            # An entire braced argument around one group is redundant.
            while len(value) == 1 and value[0][0] == "group":
                value = value[0][1]
            return value
        atom = self.atom()
        if atom is None:
            raise ValueError("Unsupported empty mathematical argument")
        return [atom]

    def atom(self):
        char = self.text[self.pos]
        self.pos += 1
        if char == "{":
            items = self.sequence("}")
            return items[0] if len(items) == 1 else ["group", items]
        if char != "\\":
            return ["char", char]
        name, self.pos = command_at(self.text, self.pos - 1)
        name = ALIASES.get(name, name)
        if (
            name in SIZING
            or name in SPACING
            or name in ("displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle")
        ):
            return None
        if name in ("frac", "dfrac", "tfrac", "binom", "dbinom", "tbinom"):
            return [
                "command",
                "frac" if "frac" in name else "binom",
                self.argument(),
                self.argument(),
            ]
        if name == "sqrt":
            self.pos = skip_space(self.text, self.pos)
            root = []
            if self.pos < len(self.text) and self.text[self.pos] == "[":
                raw, self.pos = group(self.text, self.pos, "[", "]")
                root = _Math(raw).sequence()
            return ["command", "sqrt", root, self.argument()]
        if name in TEXT:
            starred = name == "operatorname" and self.text[self.pos : self.pos + 1] == "*"
            self.pos += starred
            name += "*" if starred else ""
            self.pos = skip_space(self.text, self.pos)
            raw, self.pos = group(self.text, self.pos)
            check = 0
            while check < len(raw):
                if raw[check] == "\\":
                    command, check = command_at(raw, check)
                    if command not in ("%", "&", "_", "#", "$", "{", "}", " ", "AA"):
                        raise ValueError(f"Unsupported mathematical text command \\{command}")
                else:
                    check += 1
            # TeX text whitespace collapses but spaces between words matter.
            return ["text", name, re.sub(r"\s+", " ", raw)]
        if name == "substack":
            self.pos = skip_space(self.text, self.pos)
            raw, self.pos = group(self.text, self.pos)
            rows = split_top_level(raw, ("\\\\",))
            return [
                "environment",
                "subarray",
                "c",
                [[_Math(c).sequence() for c in split_top_level(r, ("&",))] for r in rows],
            ]
        if name in UNARY:
            return ["command", name, self.argument()]
        if name == "rm":
            # Old-style roman declaration consumes the remainder of its group.
            value = self.sequence("}")
            self.pos -= 1
            return ["command", "mathrm", value]
        if name == "begin":
            self.pos = skip_space(self.text, self.pos)
            env, self.pos = group(self.text, self.pos)
            if env not in MATH_ENVS:
                raise ValueError(f"Unsupported mathematical environment {env}")
            alignment = None
            if env == "subarray":
                alignment, self.pos = group(self.text, skip_space(self.text, self.pos))
                if alignment not in ("c", "l", "r"):
                    raise ValueError("Unsupported subarray alignment")
            start = self.pos
            depth = 1
            while self.pos < len(self.text):
                if self.text[self.pos] != "\\":
                    self.pos += 1
                    continue
                cmd, end = command_at(self.text, self.pos)
                if cmd in ("begin", "end"):
                    value, finish = group(self.text, skip_space(self.text, end))
                    if value == env:
                        depth += 1 if cmd == "begin" else -1
                    if not depth:
                        raw = self.text[start : self.pos]
                        self.pos = finish
                        rows = split_top_level(raw, ("\\\\",))
                        value = [
                            "environment",
                            env,
                            [
                                [_Math(c).sequence() for c in split_top_level(r, ("&",))]
                                for r in rows
                            ],
                        ]
                        if alignment is not None:
                            value.insert(2, alignment)
                        return value
                    self.pos = finish
                else:
                    self.pos = end
            raise ValueError("Unclosed mathematical environment")
        if name in ("end", "label", "tag", "notag", "nonumber"):
            raise ValueError(f"Unsupported mathematical command \\{name} in expression identity")
        if name in SYMBOLS or name in ("{", "}", "|", "%", "_", "#", "&", "$", "\\"):
            return ["command", name]
        raise ValueError(f"Unsupported mathematical command \\{name}")


def normalize_math(tex):
    """Return a stable syntactic identity, not an algebraic equivalence claim."""
    return json.dumps(_Math(tex).sequence(), ensure_ascii=False, separators=(",", ":"))


def math_rows(tex):
    """Authored rows/cells; nested non-numbering structures stay in their cell."""
    stripped = tex.strip()
    match = re.match(r"\\begin\{(aligned|split|gathered)\}", stripped)
    if match:
        env = match.group(1)
        ending = "\\end{" + env + "}"
        finish = stripped.rfind(ending)
        if finish < 0:
            raise ValueError("Unbalanced aligned math")
        suffix = stripped[finish + len(ending) :]
        if suffix.strip() and not re.fullmatch(r"[\s.,;:!?]*", suffix):
            return [[tex.strip()]]
        stripped = stripped[match.end() : finish] + suffix
    return [[cell.strip() for cell in split_top_level(row, ("&",))]
            for row in split_top_level(stripped, ("\\\\",)) if row.strip()]


def math_cells(tex):
    """Nonempty mathematical occurrences, retaining math_rows for ownership."""
    return [cell for row in math_rows(tex) for cell in row if cell]
