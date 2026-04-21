# Manuscript directory

This directory contains the LaTeX source for the manuscript.

## Read this directory in this order

1. `manuscript.tex` — primary manuscript source.
2. [figures/README.md](figures/README.md) — figures wired into the manuscript.
3. [tables/README.md](tables/README.md) — editable table fragments.
4. `refs.bib`, `highlights.txt`, `keywords.txt` — supporting submission files.

## Current manuscript state

- The numerical story is organized as a compact synthetic block plus the
  molecular J1–J4 benchmark, with J4 split into local validation, representative
  geometry, quantitative mask transfer, and box-margin robustness.
- Section 5 includes theorem-backed connector-visibility and clearance
  diagnostics, with proofs in the appendix.
- The manuscript-facing figures and tables are materialized under `figures/`
  and `tables/`.


## Manuscript asset source map

For a targeted table or figure edit, use these entry points before opening the
script internals:

| Asset family | Main refresh command | Targeted map |
|---|---|---|
| Generated tables | `python scripts/build_manuscript_tables.py` | [tables/README.md](tables/README.md) lists each table and its generator function. |
| Generated figures | `python scripts/build_manuscript_figures.py` | [figures/README.md](figures/README.md) lists each figure and its source script or archived source file. |
| Flat submission bundle | `python scripts/make_submission_bundle.py` | The bundle is rebuilt from `manuscript.tex` dependencies; stale files are removed first. |
| Local and optional flat verification PDFs | `bash scripts/build_manuscript_pdfs.sh` | Runs the table refresh, figure refresh, local PDF build, flat-bundle rebuild, and an ignored flat verification PDF build. |

## Build notes

`manuscript/manuscript.pdf` and `../submission/flat/manuscript.pdf` are local
build products, not committed artifacts. The tracked submission material is the
flat source bundle under `../submission/flat/`. The canonical manuscript build
requires both `latexmk` and `bibtex` on `PATH`. To run the canonical end-to-end
manuscript build (tables, figures, local PDF, and flat bundle), use:

```bash
bash ../scripts/build_manuscript_pdfs.sh
```

For targeted refreshes of only the manuscript-side tables or figures from the
archived results, run:

```bash
python ../scripts/build_manuscript_tables.py
python ../scripts/build_manuscript_figures.py
```

For a one-off manual build from the repository root, prefer
`latexmk -cd manuscript/manuscript.tex`; the repo-level `.latexmkrc` applies
the same source-local behavior to plain `latexmk manuscript/manuscript.tex`
runs so artifacts do not spill into the repo root.

The manuscript-facing figure pairs under `figures/` are written through a
deterministic Matplotlib save helper. In the same locked Python environment
recorded under `environments/`, both the PNG and PDF copies are expected to be
byte-identical across rebuilds. Outside that locked environment, visual
equivalence remains the relevant check. This guarantee does not extend to the
LaTeX-built `manuscript/manuscript.pdf`. The dedicated verification helper is
`python scripts/check_figure_binary_constancy.py --suite manuscript`.

## Internal planning files

Historical revision-planning notes were removed from this directory so that the
manuscript tree contains only current source files and generated manuscript
assets.
