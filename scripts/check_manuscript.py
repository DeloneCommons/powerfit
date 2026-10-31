#!/usr/bin/env python3
"""Validate nested manuscript sources and, optionally, logs, bibliography and PDF."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics\*?(?:\[[^\]]*\])?\s*\{([^}]+)\}")
BIB_RE = re.compile(r"\\bibliography\s*\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|eqref|pageref|autoref|cref|Cref)\*?\s*\{([^}]+)\}")
CITE_RE = re.compile(r"\\(?:cite[a-zA-Z]*|nocite)\*?(?:\[[^\]]*\])*\s*\{([^}]+)\}")
BIB_KEY_RE = re.compile(r"@(?!(?:comment|preamble|string)\b)\w+\s*\{\s*([^,\s]+)\s*,", re.I)
BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\s*\{([^}]+)\}")


def read_tex(path: Path) -> str:
    """Strip actual TeX comments, retaining escaped percent signs."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        escaped = False
        kept = []
        for char in line:
            if char == "%" and not escaped:
                break
            kept.append(char)
            escaped = not escaped if char == "\\" else False
        lines.append("".join(kept))
    return "\n".join(lines)


def _resolve(root: Path, name: str, suffixes: tuple[str, ...]) -> Path:
    if Path(name.strip()).is_absolute():
        raise ValueError(f"Absolute manuscript dependency is not portable: {name}")
    path = root / name.strip()
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"Dependency escapes outside the manuscript tree: {name}")
    candidates = [path] if path.suffix else [path.with_suffix(s) for s in suffixes]
    for candidate in candidates:
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Dependency escapes outside the manuscript tree: {name}")
        if candidate.is_file():
            if candidate != resolved:
                raise ValueError(f"Symbolic manuscript dependency is not self-contained: {name}")
            return candidate
    raise ValueError(f"Missing manuscript dependency: {name}")


def collect_dependencies(manuscript_dir: Path) -> list[Path]:
    """Resolve literal paths from the TeX working directory, preserving nesting.

    Standard TeX packages remain distribution dependencies. Any local class,
    style or bibliography style is included in the dependency set.
    """
    root = manuscript_dir.resolve()
    files: set[Path] = set()
    active: set[Path] = set()

    def visit(path: Path) -> None:
        if path in active:
            raise ValueError(f"Cyclic TeX input: {path.relative_to(root)}")
        if path in files:
            return
        files.add(path)
        active.add(path)
        text = read_tex(path)
        for name in INPUT_RE.findall(text):
            visit(_resolve(root, name, (".tex",)))
        for name in GRAPHICS_RE.findall(text):
            files.add(_resolve(root, name, (".pdf", ".png", ".jpg", ".jpeg")))
        for group in BIB_RE.findall(text):
            for name in group.split(","):
                files.add(_resolve(root, name, (".bib",)))
        for command, suffix in (("documentclass", ".cls"), ("usepackage", ".sty"),
                                ("bibliographystyle", ".bst")):
            pattern = rf"\\{command}(?:\[[^\]]*\])?\s*\{{([^}}]+)\}}"
            for group in re.findall(pattern, text):
                for name in group.split(","):
                    local = root / (name.strip() + suffix)
                    if not local.resolve().is_relative_to(root):
                        raise ValueError(f"TeX support path escapes the manuscript: {name}")
                    if local.is_file():
                        files.add(_resolve(root, name.strip() + suffix, (suffix,)))
        active.remove(path)

    visit(_resolve(root, "manuscript.tex", (".tex",)))
    if (root / "elsarticle.cls") in files and (root / "tex-support").is_dir():
        for name in ("README.md", "README.upstream", "elsarticle.dtx", "elsarticle.ins"):
            files.add(_resolve(root, f"tex-support/{name}", ("",)))
    return sorted(files)


def _tex_and_bib(manuscript_dir: Path) -> tuple[str, str]:
    files = collect_dependencies(manuscript_dir)
    tex = "\n".join(read_tex(p) for p in files if p.suffix == ".tex")
    bib = "\n".join(p.read_text(encoding="utf-8") for p in files if p.suffix == ".bib")
    return tex, bib


def _keys(pattern: re.Pattern, text: str) -> set[str]:
    return {key.strip() for group in pattern.findall(text)
            for key in group.split(",") if key.strip()}


def check_sources(manuscript_dir: Path) -> list[str]:
    try:
        tex, bib = _tex_and_bib(manuscript_dir)
    except (ValueError, OSError) as exc:
        return [str(exc)]
    errors = []
    labels = Counter(LABEL_RE.findall(tex))
    for key, count in labels.items():
        if count > 1:
            errors.append(f"Duplicate manuscript label: {key}")
    for key in sorted(_keys(REF_RE, tex) - labels.keys()):
        errors.append(f"Undefined manuscript reference: {key}")
    bib_keys = BIB_KEY_RE.findall(bib)
    for key, count in Counter(bib_keys).items():
        if count > 1:
            errors.append(f"Duplicate bibliography key: {key}")
    for key in sorted(_keys(CITE_RE, tex) - set(bib_keys) - {"*"}):
        errors.append(f"Undefined bibliography citation: {key}")
    return errors


def check_bibliography(manuscript_dir: Path) -> list[str]:
    bbl = manuscript_dir / "manuscript.bbl"
    if not bbl.is_file():
        return ["Missing generated manuscript.bbl; run the canonical PDF build first."]
    tex, bib = _tex_and_bib(manuscript_dir)
    citations = _keys(CITE_RE, tex)
    if "*" in citations:
        citations = set(BIB_KEY_RE.findall(bib))
    items = set(BIBITEM_RE.findall(bbl.read_text(encoding="utf-8")))
    errors = [f"Generated bibliography is missing citation: {key}"
              for key in sorted(citations - items)]
    errors += [f"Generated bibliography contains stale citation: {key}"
               for key in sorted(items - citations)]
    return errors


def _command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    if re.search(r"(?:Syntax|Internal) (?:Error|Warning)", result.stderr, re.I):
        raise ValueError(result.stderr.strip())
    return result.stdout


def check_built(manuscript_dir: Path) -> list[str]:
    errors = check_bibliography(manuscript_dir)
    for suffix in (".log", ".blg"):
        path = manuscript_dir / ("manuscript" + suffix)
        if not path.is_file():
            errors.append(f"Missing build diagnostic file: {path.name}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        patterns = [r"^!.*$", r"^.*(?:LaTeX|Package \S+|Class \S+) Warning:.*$",
                    r"^.*(?:undefined references|undefined citations|multiply defined).*$",
                    r"^.*(?:Overfull|Underfull) \\[hv]box.*$",
                    r"^Warning--.*$", r"^I (?:couldn't|found no).*$",
                    r"^.*(?:There (?:was|were) \d+ error|Fatal error).*$"]
        for pattern in patterns:
            errors.extend(f"{path.name}: {line}" for line in re.findall(pattern, text, re.M))
    pdf = manuscript_dir / "manuscript.pdf"
    if not pdf.is_file():
        return errors + ["Missing manuscript.pdf"]
    try:
        info = _command_output(["pdfinfo", str(pdf)])
        if not re.search(r"^Pages:\s+[1-9]\d*\s*$", info, re.M):
            errors.append("PDF has no readable pages")
        fonts = _command_output(["pdffonts", str(pdf)])
        if "Type 3" in fonts:
            errors.append("Type 3 fonts found in manuscript.pdf")
        for line in fonts.splitlines()[2:]:
            flags = re.search(r"\s(yes|no)\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", line)
            if flags and flags.group(1) == "no":
                errors.append(f"Unexpected unembedded PDF font: {line.strip()}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        errors.append(f"PDF inspection failed: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript-dir", type=Path, default=REPO_ROOT / "manuscript")
    parser.add_argument("--built", action="store_true", help="Also check logs, bibliography and PDF fonts.")
    args = parser.parse_args()
    errors = check_sources(args.manuscript_dir)
    if args.built and not errors:
        errors.extend(check_built(args.manuscript_dir))
    if errors:
        print("Manuscript check failed:")
        for error in sorted(set(errors)):
            print(f"  - {error}")
        return 1
    files = collect_dependencies(args.manuscript_dir)
    tex, _ = _tex_and_bib(args.manuscript_dir)
    print(f"Manuscript check passed: {sum(p.suffix == '.tex' for p in files)} TeX files, "
          f"{sum(p.suffix == '.pdf' for p in files)} PDF figures, "
          f"{len(_keys(CITE_RE, tex) - {'*'})} resolved bibliography citations."
          + (" Build logs, generated bibliography and PDF fonts checked." if args.built else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
