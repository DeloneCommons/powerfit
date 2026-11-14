# Reproducibility

Start with the level of verification you need. The public website and PDF can
be built without running scientific experiments. All commands below run from
the repository root. The [script guide](../scripts/README.md) owns detailed
workflow boundaries and full scientific protocols.

| Goal | Scope |
|---|---|
| Read the current article | [HTML](https://delonecommons.github.io/powerfit/article.html) or [PDF](https://delonecommons.github.io/powerfit/manuscript.pdf); generated from the same LaTeX. |
| Verify the checkout | Audit protected hashes, source dependencies, tables and focused tests. |
| Rebuild the article or website | Compile existing sources and convert existing illustrations; no experiments. |
| Repeat calculations | Use a disposable checkout and the pinned scientific environment. |

## Audit the existing evidence

To audit an untouched checkout and run the focused tests:

```bash
python scripts/check_repo_consistency.py
python scripts/check_rerun_results.py
python -m unittest discover -s tests -v
```

The integrity audit always verifies the frozen-file manifest. It should fail
on results deliberately overwritten by a scientific rerun; use the result and
table checkers to evaluate that separate checkout. CI checks frozen integrity,
figures, tables, result completeness, tests, A/B and J1 smoke subsets, and both
the canonical PDF and extracted arXiv archive. See
[the CI guide](../.github/workflows/README.md) and
[v2.0.0 release notes](release-v2.0.0.md).

## Build the current article


The current source is [manuscript/manuscript.tex](../manuscript/manuscript.tex).
The seven figure PDFs and four inline numerical tables are already included.
With TeX, Poppler and Python 3.10+ installed:

```bash
bash scripts/build_manuscript_pdfs.sh
```

This produces **`manuscript/manuscript.pdf`** from the
committed source and figures. It rebuilds the bibliography and checks the PDF.
It requires no scientific Python packages and performs no experiments.
See [TeX installation and source structure](../manuscript/README.md) for the
dependency command and the bundled official Springer Nature class/style.

To build the PDF and package the arXiv sources in one command:

```bash
python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip
```

The ZIP includes a fresh bibliography and the required source/figure files.
PDFs, ZIPs and other build outputs are ignored local files. Packaging does not
submit or publish the article.

## Verify figures and tables from frozen evidence

For figures, create a small environment using the archived package constraints:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -c environments/requirements-lock-py313.txt numpy pandas matplotlib
python scripts/build_manuscript_figures.py --output-dir build/figures
python scripts/check_manuscript_figures.py
```

The builder reads frozen results and exact schematic constructions, and writes
seven PDFs plus supplementary SVGs to `build/figures/`. The checker regenerates
them in temporary directories, checks repeatability and compares their rendered
content with the committed figures. It also needs Poppler. See the
[figure source map](../manuscript/figures/README.md) for inputs and interpretation.

The numerical tables are literal TeX, verified directly against the result CSVs:

```bash
python scripts/check_manuscript_tables.py
```

This standard-library check recomputes the E/H paired comparisons, J2 pooled
errors, J4b rankings and J3 candidate statistics. It reports mismatched cells
without rewriting the article. The
[table evidence map](../manuscript/README.md#numerical-table-evidence) explains the
populations and aggregation rules. These figure/table commands reuse frozen
evidence; they do not repeat scientific calculations.

## Build the public website

```bash
python site/build.py
python site/validate.py
python -m unittest discover -s site/tests -v
```

The [website build guide](../site/README.md) lists dependencies, conversion and
browser checks. Only `build/site/` is published; converter intermediates remain
in `build/site-work/`. The website build calls the existing canonical PDF build
and converts committed PDF figures to SVG. It never regenerates scientific
figures or runs experiments.

## Repeat scientific calculations in a disposable checkout


Use a **separate disposable checkout**: this command writes new results into
`results/`. In that checkout, install the full pinned scientific environment:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r environments/requirements-py313.txt -c environments/requirements-lock-py313.txt
python -m pip install external_software/pyvoro2-0.6.3-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl
bash scripts/rerun_paper_results.sh
```

The bundled wheel is for CPython 3.13 on Linux x86-64. Other platforms require
a compatible installation of **`pyvoro2==0.6.3`**; the rerun checks the active
version before writing results. The archived environment files stay unchanged.

The command performs all synthetic A–H runs, including the dense C sweep, and
J1/J2/J3/J4a/J4b/J4d analyses of the **committed molecular inputs**. It then
checks result completeness and agreement with the four printed tables. It does
not build the article or replace its figures/tables. Runtime and provenance
fields can differ, so new result files need not have the archive's byte hashes.

Repeating the upstream quantum chemistry is a separate, more expensive task:
RDKit/PySCF/geomeTRIC generate molecular geometries and wavefunctions; Multiwfn
generates topology and atomic radial data. The
[scientific workflow guide](../scripts/README.md#upstream-molecular-input-regeneration)
gives the fixed-manifest commands, additional environment and overwrite rules.
It also states which historical secondary outputs the default rerun excludes.

## Historical references

Archived protocols use the old manuscript's numbering. Consult the
[current experiment crosswalk](archives.md#frozen-records-and-the-current-manuscript)
and [archive guide](archives.md) when reading frozen documentation. The
[documentation index](README.md) links the experiment-specific guides.
