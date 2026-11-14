"""Independent, ordered inventory of a bounded authored LaTeX grammar.

This reader consumes the original master and literal active inputs. It never
uses the website wrapper, converter XML, final HTML, directory globs or a TeX
macro interpreter as evidence. Unsupported content-bearing syntax fails closed.
All paths in the report are relative to the master directory.
"""

from hashlib import sha256
from pathlib import Path
import re

from texsyntax import command_at, group, skip_space, strip_comments
from mathsyntax import normalize_math, math_cells, split_top_level, ALIASES

HEADINGS = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}
STATEMENTS = {"proposition", "theorem", "corollary", "definition", "remark", "proof"}
CONTAINERS = STATEMENTS | {"figure", "table", "itemize", "enumerate"}
TRANSPARENT = {"center", "samepage", "minipage"}
MATH_ENV = {"equation", "equation*", "align", "align*"}
FORMATTING = {
    "emph",
    "texttt",
    "textbf",
    "textit",
    "textrm",
    "textsf",
    "underline",
    "mbox",
    "shortstack",
    "fnm",
    "sur",
    "orgname",
    "orgaddress",
    "city",
    "country",
}
LAYOUT = {
    "noindent",
    "centering",
    "footnotesize",
    "small",
    "raggedright",
    "clearpage",
    "newpage",
    "FloatBarrier",
    "par",
    "smallskip",
    "medskip",
    "bigskip",
    "backmatter",
    "maketitle",
}
LAYOUT_ARG = {"vspace", "hspace", "Needspace", "enlargethispage"}
TEXT_SYMBOLS = {
    "%": "%",
    "&": "&",
    "_": "_",
    "#": "#",
    "$": "$",
    "{": "{",
    "}": "}",
    " ": " ",
    "AA": "Å",
    "ldots": "…",
    "textbackslash": "\\",
}
METADATA = {"title", "author", "email", "affil", "abstract", "keywords", "pacs"}
CITATIONS = {"citep", "citet"}
REFERENCES = {"ref", "eqref"}
SCALAR = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
# Exact, nonprinting natbib settings write from the publisher source. No generic
# conditional, output-stream, or macro-definition grammar is authorized.
BIB_SETTINGS = re.compile(
    r"\\makeatletter\s*\\if@filesw\s*\\immediate\\write\\@auxout\{\\string\\citation\{camBibSettings\}\}\s*\\fi\s*\\makeatother"
)


def _literal(value, role):
    if not value or re.search(r"[\\{}%#\x00-\x1f]", value):
        raise ValueError(f"Unsupported nonliteral {role}: {value!r}")
    return value


def _layout_dimension(value, role, *, relatives=(), signed=True):
    """Authorize literal pt lengths and only explicitly named layout registers."""
    value = value.strip()
    sign = r"[+-]?" if signed else ""
    absolute = sign + SCALAR + r"\s*pt"
    relative = sign + "(?:" + SCALAR + r")?\s*\\(?:" + "|".join(relatives) + ")"
    if not re.fullmatch(absolute, value) and not (relatives and re.fullmatch(relative, value)):
        raise ValueError(f"Unsupported {role} layout dimension: {value!r}")


def _column_count(spec):
    """Actual l/c/r/p columns and empty @{ } spacing; no inserted content."""
    pos = 0
    count = 0
    while skip_space(spec, pos) < len(spec):
        pos = skip_space(spec, pos)
        char = spec[pos]
        pos += 1
        if char in "lcr":
            count += 1
        elif char == "p":
            width, pos = group(spec, skip_space(spec, pos))
            _layout_dimension(width, "tabular column", relatives=("linewidth",), signed=False)
            count += 1
        elif char == "@":
            spacing, pos = group(spec, skip_space(spec, pos))
            if spacing.strip():
                raise ValueError("Unsupported content in tabular column spacing")
        elif char == "|":
            pass
        else:
            raise ValueError(f"Unsupported tabular column specification: {spec!r}")
    if not count:
        raise ValueError("Unsupported empty tabular column specification")
    return count


class _Reader:
    def __init__(self, master):
        self.master = Path(master).resolve()
        self.root = self.master.parent
        self.sources = []
        self.seen = set()
        self.maps = []
        self.text = ""
        self.objects = []
        self.math = []
        self.labels = {}
        self.appendix = False
        self.equation_counter = 0
        self.heading_counters = [0, 0, 0, 0]
        self.theorems = {}
        self.statement_counters = {}
        self.float_counters = {"figure": 0, "table": 0}
        self.macro_context = sha256(
            ("bounded-math-v1:" + repr(sorted(ALIASES.items()))).encode()
        ).hexdigest()

    def expand(self, path, stack=()):
        path = path.resolve()
        if path in stack:
            raise ValueError(f"Active input cycle at {path.name}")
        if not path.is_relative_to(self.root):
            raise ValueError("Unsupported input outside manuscript directory")
        if not path.is_file():
            raise ValueError(f"Unsupported missing active input: {path}")
        relative = path.relative_to(self.root).as_posix()
        if relative not in self.seen:
            self.sources.append(
                {
                    "path": relative,
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                    "role": "authored",
                }
            )
            self.seen.add(relative)
        text = path.read_text()
        parts = []
        maps = []
        pos = 0
        line = 1
        while pos < len(text):
            if text[pos] == "%":
                finish = text.find("\n", pos)
                if finish < 0:
                    break
                line += 1
                pos = finish + 1
                # A percent comment suppresses its endline; TeX also ignores
                # indentation while entering the following physical line.
                while pos < len(text) and text[pos] in " \t":
                    pos += 1
                if (
                    parts
                    and re.fullmatch(r"\\[A-Za-z]+", parts[-1])
                    and pos < len(text)
                    and text[pos].isascii()
                    and text[pos].isalpha()
                ):
                    # The endline did not join distinct TeX control tokens.
                    parts.append(" ")
                    maps.append((relative, line))
                continue
            if text[pos] == "\\":
                name, end = command_at(text, pos)
                if name == "input":
                    start = skip_space(text, end)
                    value, finish = group(text, start)
                    _literal(value, "input path")
                    target = self.root / value
                    if not target.suffix:
                        target = target.with_suffix(".tex")
                    if value == "tex-support/glyphtounicode-cmr.tex":
                        if path != self.master or text.find("\\begin{document}") < pos:
                            raise ValueError(
                                "Unsupported publisher Unicode input outside original preamble"
                            )
                        if not target.is_file():
                            raise ValueError("Missing publisher Unicode dependency")
                        key = target.relative_to(self.root).as_posix()
                        if key not in self.seen:
                            self.sources.append(
                                {
                                    "path": key,
                                    "sha256": sha256(target.read_bytes()).hexdigest(),
                                    "role": "publisher-unicode",
                                }
                            )
                            self.seen.add(key)
                        replacement = "\n"
                        locations = [(relative, line)]
                    else:
                        replacement, locations = self.expand(target, stack + (path,))
                    parts.append(replacement)
                    maps.extend(locations)
                    line += text[pos:finish].count("\n")
                    pos = finish
                    continue
                # Escape/control words must be consumed together, otherwise the
                # second slash in \\input would become a false dependency.
                piece = text[pos:end]
                parts.append(piece)
                maps.extend((relative, line) for _ in piece)
                pos = end
                continue
            char = text[pos]
            parts.append(char)
            maps.append((relative, line))
            line += char == "\n"
            pos += 1
        return "".join(parts), maps

    def location(self, pos):
        if self.maps:
            return self.maps[min(pos, len(self.maps) - 1)]
        return self.master.name, 1

    def new(self, kind, parent, pos, **extra):
        source, line = self.location(pos)
        obj = {
            "id": f"o{len(self.objects) + 1}",
            "kind": kind,
            "source": source,
            "line": line,
            "owner": parent["id"] if parent else None,
            "order": len(self.objects),
            "labels": [],
            "content": [],
        }
        obj.update(extra)
        self.objects.append(obj)
        if parent:
            parent["content"].append({"kind": "object", "id": obj["id"]})
        return obj

    def label(self, value, obj):
        _literal(value, "label")
        if value in self.labels:
            raise ValueError(f"Duplicate source label: {value}")
        self.labels[value] = obj["id"]
        obj["labels"].append(value)

    def argument(self, pos):
        return group(self.text, skip_space(self.text, pos))

    def optional(self, pos):
        pos = skip_space(self.text, pos)
        if pos < len(self.text) and self.text[pos] == "[":
            return group(self.text, pos, "[", "]")
        return None, pos

    def environment_end(self, start, name):
        pos = start
        stack = [name]
        while pos < len(self.text):
            if self.text[pos] != "\\":
                pos += 1
                continue
            command, end = command_at(self.text, pos)
            if command in ("begin", "end"):
                value, finish = self.argument(end)
                if command == "begin":
                    stack.append(value)
                else:
                    if not stack or value != stack.pop():
                        raise ValueError(f"Unbalanced environment {value}")
                    if not stack:
                        return pos, finish
                pos = finish
            else:
                pos = end
        raise ValueError(f"Unclosed source environment {name}")

    def theorem_definitions(self, end):
        """Read only independently numbered, literal original theorem headings."""
        pos = 0
        while pos < end:
            if self.text[pos] == "{":
                _, pos = group(self.text, pos)
            elif self.text[pos] == "\\":
                name, pos = command_at(self.text, pos)
                if name != "newtheorem":
                    continue
                if self.text[pos : pos + 1] == "*":
                    raise ValueError("Unsupported starred theorem numbering declaration")
                environment, pos = self.argument(pos)
                if not re.fullmatch(r"[A-Za-z]+", environment) or environment == "proof":
                    raise ValueError("Unsupported theorem environment declaration")
                option, pos = self.optional(pos)
                if option is not None:
                    raise ValueError("Unsupported shared theorem numbering declaration")
                heading, pos = self.argument(pos)
                option, pos = self.optional(pos)
                if option is not None:
                    raise ValueError("Unsupported within-section theorem numbering declaration")
                if not heading.strip() or re.search(r"[\\{}$^_~%&#]", heading):
                    raise ValueError("Unsupported nonliteral theorem heading")
                if environment in self.theorems:
                    raise ValueError("Duplicate theorem declaration: " + environment)
                self.theorems[environment] = " ".join(heading.split())
            else:
                pos += 1

    @staticmethod
    def clean_tokens(tokens):
        result = []
        for token in tokens:
            if token["kind"] == "text":
                value = re.sub(r"\s+", " ", token["text"].replace("~", " "))
                if result and result[-1]["kind"] == "text":
                    result[-1]["text"] = re.sub(r"\s+", " ", result[-1]["text"] + value)
                else:
                    result.append({"kind": "text", "text": value})
            else:
                result.append(token)
        if result and result[0]["kind"] == "text":
            result[0]["text"] = result[0]["text"].lstrip()
        if result and result[-1]["kind"] == "text":
            result[-1]["text"] = result[-1]["text"].rstrip()
        return [token for token in result if token.get("text", True)]

    def math_record(
        self, tex, pos, end, parent, mode, environment, numbered=False, representation=None
    ):
        labels = []

        def remove_label(match):
            value = match.group(1)
            labels.append(value)
            return ""

        # Labels have literal arguments. Reject unsupported tag overrides instead
        # of accepting numbering the canonical compiler cannot disambiguate.
        clean = re.sub(r"\\label\s*\{([^{}\\]+)\}", remove_label, tex)
        suppressed = bool(re.search(r"\\(?:notag|nonumber)\b", clean))
        clean = re.sub(r"\\(?:notag|nonumber)\b", "", clean).strip()
        if "\\label" in clean:
            raise ValueError("Unsupported mathematical label syntax")
        start_content = pos + len(tex) - len(tex.lstrip())
        end_content = end - (len(tex) - len(tex.rstrip()))
        source, line = self.location(start_content)
        _, end_line = self.location(max(start_content, end_content - 1))
        cells = math_cells(clean)
        try:
            normalized = normalize_math(clean)
        except ValueError as error:
            raise ValueError(f"{error} at {source}:{line}: {clean}") from error
        record = {
            "id": f"m{len(self.math) + 1}",
            "source": source,
            "line": line,
            "end_line": end_line,
            "owner": parent["id"],
            "order": len(self.math),
            "mode": mode,
            "environment": environment,
            "tex": clean,
            "normalized": normalized,
            "cells": [normalize_math(c) for c in cells],
            "cell_tex": cells,
            "numbered": numbered and not suppressed,
            "labels": labels,
            "pure_script": bool(re.fullmatch(r"\^\s*(?:\\[A-Za-z]+|\{[^{}]+\}|[^\s{}])", clean)),
            "macro_context": self.macro_context,
        }
        if record["numbered"]:
            self.equation_counter += 1
        record["number"] = self.equation_counter if record["numbered"] else None
        if representation:
            record["representation"] = representation
        self.math.append(record)
        if representation != "container":
            for value in labels:
                self.label(value, parent)
        parent["content"].append({"kind": "math", "id": record["id"]})
        return record

    def inline(self, start, end, parent):
        """Read only mixed content; structural commands must occur at block level."""
        tokens = []
        pos = start
        while pos < end:
            char = self.text[pos]
            if char == "$":
                if pos + 1 < end and self.text[pos + 1] == "$":
                    raise ValueError("Unsupported double-dollar mathematics")
                finish = pos + 1
                while finish < end:
                    if self.text[finish] == "\\":
                        _, finish = command_at(self.text, finish)
                        continue
                    if self.text[finish] == "$":
                        break
                    finish += 1
                if finish == end:
                    raise ValueError("Unclosed inline mathematics")
                holder = {"id": parent["id"], "content": [], "labels": parent["labels"]}
                record = self.math_record(
                    self.text[pos + 1 : finish], pos, finish + 1, holder, "inline", "$"
                )
                tokens.append({"kind": "math", "id": record["id"]})
                pos = finish + 1
                continue
            if char == "{":
                _, finish = group(self.text, pos)
                tokens.extend(self.inline(pos + 1, finish - 1, parent))
                pos = finish
                continue
            if char == "}":
                raise ValueError("Unbalanced source prose group")
            if char != "\\":
                tokens.append({"kind": "text", "text": char})
                pos += 1
                continue
            name, finish = command_at(self.text, pos)
            if name in FORMATTING:
                value_start = skip_space(self.text, finish)
                _, after = group(self.text, value_start)
                if name == "shortstack":
                    # Explicit line breaks inside short table headings render as spaces.
                    pass
                tokens.extend(self.inline(value_start + 1, after - 1, parent))
                pos = after
                continue
            if name in CITATIONS | REFERENCES:
                option, finish = self.optional(finish)
                second, finish = self.optional(finish)
                if name in REFERENCES and option is not None:
                    raise ValueError("Unsupported reference option")
                value, after = self.argument(finish)
                values = value.split(",") if name in CITATIONS else [value]
                targets = [_literal(x.strip(), name + " target") for x in values]
                token = {
                    "kind": "cite" if name.startswith("cite") else name,
                    "command": name,
                    "targets": targets,
                }
                if second is not None:
                    token["prenote"] = option
                    token["postnote"] = second
                elif option is not None:
                    token["postnote"] = option
                tokens.append(token)
                pos = after
                continue
            if name in ("href", "url", "path"):
                value, after = self.argument(finish)
                _literal(value, "link/path")
                if name == "href":
                    nested = skip_space(self.text, after)
                    _, after = group(self.text, nested)
                    content = self.inline(nested + 1, after - 1, parent)
                else:
                    content = [{"kind": "text", "text": value}]
                if name == "path":
                    tokens.extend(content)
                else:
                    tokens.append({"kind": "link", "target": value, "content": content})
                pos = after
                continue
            if name in TEXT_SYMBOLS:
                tokens.append({"kind": "text", "text": TEXT_SYMBOLS[name]})
                pos = finish
                # Control-word whitespace terminates the command, not a word.
                if name.isalpha():
                    pos = skip_space(self.text, pos)
                continue
            if name in (",", "!", "allowbreak"):
                pos = skip_space(self.text, finish) if name.isalpha() else finish
                continue
            if name in ("\\", "tabularnewline", "par"):
                tokens.append({"kind": "text", "text": " "})
                pos = finish
                continue
            if name in ("raggedright", "footnotesize", "small", "noindent"):
                pos = finish
                continue
            raise ValueError(f"Unsupported prose command \\{name} at {self.location(pos)}")
        return self.clean_tokens(tokens)

    def tabular(self, start, end, parent, pos):
        table = self.new("tabular", parent, pos)
        column_spec, start = self.argument(start)
        table["columns"] = column_spec
        columns = _column_count(column_spec)
        raw = self.text[start:end]
        # Only known rules and their balanced layout arguments are nonprinting.
        raw_start = start
        cursor = start
        segments = []
        depth = 0
        in_math = False
        while cursor < end:
            if self.text[cursor] == "\\":
                name, finish = command_at(self.text, cursor)
                if name in ("toprule", "midrule", "bottomrule", "hline", "cmidrule"):
                    if depth or in_math:
                        raise ValueError("Unsupported table rule within cell content")
                    segments.append((raw_start, cursor))
                    rule_width, finish = self.optional(finish)
                    if rule_width is not None:
                        if name == "hline":
                            raise ValueError("Unsupported optional hline width")
                        _layout_dimension(rule_width, "table rule", signed=False)
                    if name == "cmidrule":
                        finish = skip_space(self.text, finish)
                        if self.text[finish : finish + 1] == "(":
                            trim, finish = group(self.text, finish, "(", ")")
                            if not re.fullmatch(r"[lr]*", trim):
                                raise ValueError("Unsupported table rule trim")
                        extent, finish = self.argument(finish)
                        match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", extent.strip())
                        if not match or not 1 <= int(match[1]) <= int(match[2]) <= columns:
                            raise ValueError("Unsupported table rule column extent")
                    raw_start = finish
                    cursor = finish
                    continue
                cursor = finish
            else:
                if self.text[cursor] == "{":
                    depth += 1
                elif self.text[cursor] == "}":
                    depth -= 1
                elif self.text[cursor] == "$":
                    in_math = not in_math
                cursor += 1
        segments.append((raw_start, end))
        # Keep original offsets by blanking layout instead of deleting it.
        chars = list(self.text[start:end])
        active = [False] * len(chars)
        for a, b in segments:
            for index in range(a - start, b - start):
                active[index] = True
        for index, keep in enumerate(active):
            if not keep:
                chars[index] = " "
        rows = split_top_level("".join(chars), ("\\\\",), spans=True)
        for raw_row, row_start, row_end in rows:
            row_pos = start + row_start
            if not raw_row.strip():
                continue
            row = self.new("row", table, row_pos + len(raw_row) - len(raw_row.lstrip()))
            cells = split_top_level(raw_row, ("&",), spans=True)
            if len(cells) != columns:
                raise ValueError(
                    "Unsupported tabular row: explicit cells must match column specification"
                )
            for value, cell_start, cell_end in cells:
                cell_offset = row_pos + cell_start
                cell = self.new("cell", row, cell_offset + len(value) - len(value.lstrip()))
                # Inline reads original source; replace removed rules only for this
                # range and restore immediately, preserving source coordinates.
                previous = self.text
                self.text = previous[:cell_offset] + value + previous[cell_offset + len(value) :]
                try:
                    cell["content"] = self.inline(cell_offset, cell_offset + len(value), cell)
                finally:
                    self.text = previous
        return table

    def parse(self, start, end, parent, allow_sections=True):
        pos = start
        owner = parent
        headings = []
        prose_start = None
        prose_end = None

        def flush():
            nonlocal prose_start, prose_end
            if prose_start is not None and self.text[prose_start:prose_end].strip():
                obj = self.new("prose", owner, prose_start)
                obj["content"] = self.inline(prose_start, prose_end, obj)
                if not obj["content"]:
                    self.objects.pop()
                    owner["content"].pop()
            prose_start = prose_end = None

        while pos < end:
            if self.text[pos : pos + 2] == "\n\n":
                flush()
                pos += 2
                continue
            char = self.text[pos]
            if char != "\\":
                if prose_start is None:
                    prose_start = pos
                if char == "$":
                    finish = pos + 1
                    while finish < end:
                        if self.text[finish] == "\\":
                            _, finish = command_at(self.text, finish)
                            continue
                        if self.text[finish] == "$":
                            break
                        finish += 1
                    if finish == end:
                        raise ValueError("Unclosed inline mathematics")
                    pos = finish + 1
                elif char == "{":
                    _, pos = group(self.text, pos)
                elif char == "}":
                    raise ValueError("Unbalanced source prose group")
                else:
                    pos += 1
                prose_end = pos
                continue
            name, finish = command_at(self.text, pos)
            if name in HEADINGS:
                flush()
                if not allow_sections:
                    raise ValueError("Unsupported heading inside content environment")
                starred = finish < end and self.text[finish] == "*"
                finish += starred
                alternate, finish = self.optional(finish)
                if alternate is not None:
                    raise ValueError("Unsupported alternate heading")
                argpos = skip_space(self.text, finish)
                _, after = group(self.text, argpos)
                level = HEADINGS[name]
                while headings and headings[-1][0] >= level:
                    headings.pop()
                above = headings[-1][1] if headings else parent
                obj = self.new(
                    "paragraph_heading" if name == "paragraph" else name,
                    above,
                    pos,
                    level=level,
                    starred=starred,
                    appendix=self.appendix,
                )
                obj["number"] = None
                if not starred and name != "paragraph":
                    self.heading_counters[level - 1] += 1
                    for index in range(level, 4):
                        self.heading_counters[index] = 0
                    counters = [str(v) for v in self.heading_counters[:level]]
                    if self.appendix:
                        counters[0] = chr(64 + self.heading_counters[0])
                    obj["number"] = ".".join(counters)
                obj["title"] = self.inline(argpos + 1, after - 1, obj)
                headings.append((level, obj))
                owner = obj
                pos = after
                continue
            if name == "label":
                flush()
                value, after = self.argument(finish)
                self.label(value, owner)
                pos = after
                continue
            if name == "appendix":
                flush()
                self.appendix = True
                headings = []
                owner = parent
                self.heading_counters = [0, 0, 0, 0]
                pos = finish
                continue
            if name in METADATA:
                flush()
                finish += finish < end and self.text[finish] == "*"
                option, finish = self.optional(finish)
                argpos = skip_space(self.text, finish)
                _, after = group(self.text, argpos)
                obj = self.new(name, parent, pos)
                obj["content"] = self.inline(argpos + 1, after - 1, obj)
                if option is not None:
                    obj["option"] = option
                pos = after
                continue
            if name == "begin":
                value, after = self.argument(finish)
                flush()
                close, after_env = self.environment_end(after, value)
                if value in MATH_ENV:
                    obj = self.new(value.rstrip("*"), owner, pos, environment=value)
                    raw = self.text[after:close]
                    if value.startswith(("align", "gather")):
                        outer = self.math_record(
                            raw, after, close, obj, "display", value, representation="container"
                        )
                        outer["rows"] = []
                        for row, row_start, row_end in split_top_level(raw, ("\\\\",), spans=True):
                            row_pos = after + row_start
                            if row.strip():
                                child = self.new("equation_row", obj, row_pos)
                                record = self.math_record(
                                    row,
                                    row_pos,
                                    row_pos + len(row),
                                    child,
                                    "row",
                                    value,
                                    not value.endswith("*"),
                                )
                                outer["rows"].append(record["id"])
                    else:
                        self.math_record(
                            raw, after, close, obj, "display", value, not value.endswith("*")
                        )
                elif value == "tabular":
                    self.tabular(after, close, owner, pos)
                elif value in CONTAINERS:
                    obj = self.new(value, owner, pos)
                    option_start = skip_space(self.text, after)
                    option, after = self.optional(after)
                    if value in STATEMENTS:
                        if value == "proof":
                            obj.update(statement_heading="Proof", number=None)
                        else:
                            if value not in self.theorems:
                                raise ValueError(
                                    "Unsupported undeclared theorem environment: " + value
                                )
                            self.statement_counters[value] = (
                                self.statement_counters.get(value, 0) + 1
                            )
                            obj.update(
                                statement_heading=self.theorems[value],
                                number=self.statement_counters[value],
                            )
                    elif value in self.float_counters:
                        obj["number"] = None
                    if option is not None:
                        if value == "proof":
                            raise ValueError("Unsupported custom proof heading")
                        if value in ("itemize", "enumerate"):
                            raise ValueError("Unsupported custom list option")
                        if value in ("figure", "table") and not re.fullmatch(r"[!htbp]+", option):
                            raise ValueError("Unsupported float placement option")
                        obj["option"] = option
                        if value in STATEMENTS:
                            obj["title"] = self.inline(option_start + 1, after - 1, obj)
                    self.parse(after, close, obj, False)
                    if value in self.float_counters and obj["number"] is None:
                        raise ValueError("Unsupported float without exactly one caption")
                elif value in TRANSPARENT:
                    if value == "minipage":
                        width, after = self.argument(after)
                        _layout_dimension(width, "minipage", relatives=("linewidth",), signed=False)
                    self.parse(after, close, owner, False)
                else:
                    raise ValueError(
                        f"Unsupported source environment {value} at {self.location(pos)}"
                    )
                pos = after_env
                continue
            if name == "[":
                flush()
                close = self.text.find("\\]", finish)
                if close < 0:
                    raise ValueError("Unclosed display mathematics")
                obj = self.new("display", owner, pos)
                self.math_record(self.text[finish:close], finish, close, obj, "display", "[]")
                pos = close + 2
                continue
            if name == "caption":
                flush()
                alternate, finish = self.optional(finish)
                if alternate is not None:
                    raise ValueError("Unsupported alternate caption")
                argpos = skip_space(self.text, finish)
                _, after = group(self.text, argpos)
                if owner["kind"] not in self.float_counters:
                    raise ValueError("Unsupported caption outside figure or table")
                if owner["number"] is not None:
                    raise ValueError("Unsupported multiple captions in one float")
                self.float_counters[owner["kind"]] += 1
                owner["number"] = self.float_counters[owner["kind"]]
                obj = self.new("caption", owner, pos, number=owner["number"])
                obj["content"] = self.inline(argpos + 1, after - 1, obj)
                pos = after
                continue
            if name == "includegraphics":
                flush()
                option, finish = self.optional(finish)
                value, after = self.argument(finish)
                if option is not None:
                    match = re.fullmatch(r"\s*width\s*=\s*(.+?)\s*", option)
                    if not match:
                        raise ValueError(
                            "Unsupported graphic option: only literal width is supported"
                        )
                    _layout_dimension(
                        match[1], "graphic width", relatives=("linewidth",), signed=False
                    )
                self.new(
                    "graphic", owner, pos, target=_literal(value, "graphic path"), options=option
                )
                pos = after
                continue
            if name == "item":
                flush()
                option, after = self.optional(finish)
                if parent["kind"] not in ("itemize", "enumerate"):
                    raise ValueError("Unsupported item outside list")
                owner = self.new("item", parent, pos)
                if option is not None:
                    raise ValueError("Unsupported custom list item marker")
                pos = after
                continue
            if name in LAYOUT:
                flush()
                pos = finish
                continue
            if name in LAYOUT_ARG:
                flush()
                length, pos = self.argument(finish)
                relatives = ("baselineskip",) if name in ("Needspace", "enlargethispage") else ()
                _layout_dimension(length, name, relatives=relatives, signed=name != "Needspace")
                continue
            if name == "setlength":
                flush()
                register, finish = self.argument(finish)
                length, pos = self.argument(finish)
                if register.strip() != r"\tabcolsep":
                    raise ValueError("Unsupported layout setlength register")
                _layout_dimension(length, "tabcolsep", signed=False)
                continue
            if name == "bibliography":
                flush()
                value, after = self.argument(finish)
                self.new(
                    "bibliography",
                    parent,
                    pos,
                    targets=[_literal(v.strip(), "bibliography") for v in value.split(",")],
                )
                pos = after
                continue
            if name == "makeatletter":
                match = BIB_SETTINGS.match(self.text, pos)
                if not match:
                    raise ValueError("Unsupported nonprinting bibliography directive")
                flush()
                pos = match.end()
                continue
            # Inline commands and their arguments are advanced as a unit, preventing
            # a formatted group's nested command becoming a false block boundary.
            if name in FORMATTING | CITATIONS | REFERENCES | {"href", "url", "path"}:
                if prose_start is None:
                    prose_start = pos
                if name in CITATIONS | REFERENCES:
                    option, finish = self.optional(finish)
                    _, finish = self.optional(finish)
                    if name in REFERENCES and option is not None:
                        raise ValueError("Unsupported reference option")
                _, finish = self.argument(finish)
                if name == "href":
                    _, finish = self.argument(finish)
                pos = finish
                prose_end = pos
                continue
            if name in TEXT_SYMBOLS or name in (",", "!", "allowbreak", "\\", "tabularnewline"):
                if prose_start is None:
                    prose_start = pos
                pos = finish
                prose_end = pos
                continue
            raise ValueError(f"Unsupported source command \\{name} at {self.location(pos)}")
        flush()

    def read(self):
        self.text, self.maps = self.expand(self.master)
        match = re.search(r"\\begin\s*\{document\}", self.text)
        if not match:
            raise ValueError("Unclosed/missing source document")
        close, after = self.environment_end(match.end(), "document")
        if self.text[after:].strip():
            raise ValueError("Unsupported content after source document")
        self.theorem_definitions(match.start())
        document = self.new("document", None, match.start())
        self.parse(match.end(), close, document)
        return {
            "schema": 1,
            "master": self.master.name,
            "sources": self.sources,
            "objects": self.objects,
            "math": self.math,
            "labels": self.labels,
            "macro_context": self.macro_context,
            "theorem_definitions": self.theorems,
        }


def read_inventory(manuscript: Path):
    """Return a JSON-serializable source tree, math inventory and dependency order."""
    return _Reader(manuscript).read()
