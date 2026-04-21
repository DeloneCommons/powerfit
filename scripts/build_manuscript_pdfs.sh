#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
PYTHON_BIN=${PYTHON:-python}
CREATED_MPLCONFIGDIR=0

if [[ ! -f "$REPO_ROOT/manuscript/manuscript.tex" ]]; then
  echo "error: could not locate manuscript/manuscript.tex relative to $REPO_ROOT" >&2
  exit 1
fi

if [[ -z "${MPLCONFIGDIR:-}" ]]; then
  MPLCONFIGDIR=$(mktemp -d /tmp/powerfit-mpl-XXXXXX)
  export MPLCONFIGDIR
  CREATED_MPLCONFIGDIR=1
fi

cleanup_temp_dirs() {
  if [[ $CREATED_MPLCONFIGDIR -eq 1 && -n "${MPLCONFIGDIR:-}" && -d "$MPLCONFIGDIR" ]]; then
    rm -rf -- "$MPLCONFIGDIR"
  fi
}

trap cleanup_temp_dirs EXIT

cleanup_latex_artifacts() {
  local target_dir=$1
  local gitignore=$REPO_ROOT/.gitignore
  local -a patterns=()

  mapfile -t patterns < <(
    awk '
      /^# LaTeX build artifacts$/ { inblock=1; next }
      /^# / && inblock { exit }
      inblock && /^\*\.[^[:space:]]+$/ { print $0 }
    ' "$gitignore"
  )

  local pattern
  for pattern in "${patterns[@]}"; do
    find "$target_dir" -maxdepth 1 -type f -name "$pattern" -delete
  done
}

cleanup_root_manuscript_artifacts() {
  local -a suffixes=(
    aux
    bcf
    bbl
    blg
    fdb_latexmk
    fls
    ilg
    ind
    lof
    log
    lot
    nlo
    nls
    out
    pdf
    run.xml
    spl
    synctex.gz
    toc
    xdv
  )
  local -a removed=()
  local suffix
  local path

  for suffix in "${suffixes[@]}"; do
    path="$REPO_ROOT/manuscript.$suffix"
    if [[ -f "$path" ]]; then
      rm -f -- "$path"
      removed+=("manuscript.$suffix")
    fi
  done

  if [[ ${#removed[@]} -gt 0 ]]; then
    printf '[build] removed stray repo-root LaTeX outputs: %s\n' "${removed[*]}"
  fi
}

require_command() {
  local name=$1

  if ! command -v "$name" >/dev/null 2>&1; then
    echo "error: required command not found on PATH: $name" >&2
    exit 1
  fi
}

compile_dir() {
  local rel_dir=$1
  local abs_dir="$REPO_ROOT/$rel_dir"
  local -a latexmk_args=(-g -pdf -bibtex -interaction=nonstopmode -halt-on-error)

  if [[ ! -d "$abs_dir" ]]; then
    echo "error: expected directory not found: $abs_dir" >&2
    exit 1
  fi

  cleanup_latex_artifacts "$abs_dir"
  echo "[build] compiling $rel_dir/manuscript.tex"
  (
    cd "$abs_dir"
    latexmk "${latexmk_args[@]}" manuscript.tex
  )
  cleanup_latex_artifacts "$abs_dir"
}

cleanup_root_manuscript_artifacts
require_command latexmk
require_command bibtex

echo "[build] refreshing manuscript-side tables"
"$PYTHON_BIN" "$REPO_ROOT/scripts/build_manuscript_tables.py"

echo "[build] refreshing manuscript-facing figures"
"$PYTHON_BIN" "$REPO_ROOT/scripts/build_manuscript_figures.py"

compile_dir manuscript

echo "[build] regenerating flat submission bundle"
"$PYTHON_BIN" "$REPO_ROOT/scripts/make_submission_bundle.py"

compile_dir submission/flat

cleanup_root_manuscript_artifacts

if [[ ! -f "$REPO_ROOT/manuscript/manuscript.pdf" ]]; then
  echo "error: expected output not found: $REPO_ROOT/manuscript/manuscript.pdf" >&2
  exit 1
fi

if [[ ! -f "$REPO_ROOT/submission/flat/manuscript.pdf" ]]; then
  echo "error: expected output not found: $REPO_ROOT/submission/flat/manuscript.pdf" >&2
  exit 1
fi

echo "[build] done"
echo "[build] main PDF: $REPO_ROOT/manuscript/manuscript.pdf"
echo "[build] flat PDF: $REPO_ROOT/submission/flat/manuscript.pdf"
