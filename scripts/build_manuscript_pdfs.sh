#!/usr/bin/env bash
# Canonical manuscript build. Figure generation is a separate, explicit command.
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
PYTHON_BIN=${PYTHON:-python3}

for tool in latexmk pdflatex bibtex kpsewhich pdfinfo pdffonts "$PYTHON_BIN"; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "error: required build tool not found: $tool" >&2
    exit 1
  fi
done

for tex_file in elsarticle.cls elsarticle-num.bst amsmath.sty amssymb.sty \
  amsthm.sty mathtools.sty graphicx.sty placeins.sty needspace.sty \
  booktabs.sty hyperref.sty fontenc.sty inputenc.sty; do
  if [[ ! -f "$REPO_ROOT/manuscript/$tex_file" ]] && ! kpsewhich "$tex_file" >/dev/null; then
    echo "error: missing TeX dependency $tex_file; see manuscript/README.md" >&2
    exit 1
  fi
done

"$PYTHON_BIN" "$SCRIPT_DIR/check_manuscript.py"
latexmk -norc -r "$REPO_ROOT/.latexmkrc" -g -pdf -bibtex \
  -interaction=nonstopmode -halt-on-error -file-line-error -recorder \
  "$REPO_ROOT/manuscript/manuscript.tex"
"$PYTHON_BIN" "$SCRIPT_DIR/check_manuscript.py" --built
echo "[build] PDF: $REPO_ROOT/manuscript/manuscript.pdf"
