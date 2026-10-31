# Scripts

These helpers build and verify the current article using the frozen experimental
evidence. Run the commands below from the repository root.

## Current article workflow

| Task | Command | Effect |
|---|---|---|
| Compile the article | `bash scripts/build_manuscript_pdfs.sh` | Uses the committed TeX and figure PDFs to build `manuscript/manuscript.pdf` and its bibliography. |
| Regenerate seven figures | `python scripts/build_manuscript_figures.py` | Reads local frozen results and exact schematic constructions; writes the current figure set. |
| Check repository consistency | `python scripts/check_repo_consistency.py` | Audits current manuscript dependencies, documentation, frozen evidence, and bundled-artifact provenance. |
| Check current figure reproduction | `python scripts/check_manuscript_figures.py` | Generates temporary outputs, checks repeatability, and compares rendered figures with the committed PDFs. |
| Run focused tests | `python -m unittest discover -s tests -v` | Checks construction and build-helper behavior without scientific reruns. |
| Make an arXiv source ZIP | `python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip` | Builds a fresh bibliography and packages the nested TeX/figure source tree. |

Compilation, figure generation, and packaging are separate tasks. The canonical
PDF build does not generate figures or tables and does not run experiments.
The arXiv helper builds before packaging so that `manuscript.bbl` belongs to
the current sources. Its ZIP is ignored; no submission or release is performed.

The article has four tables embedded directly in
`manuscript/sections/06_experiments.tex`,
`manuscript/sections/07_molecular.tex`, and
`manuscript/appendices/appendix_e.tex`. Historical table fragments are not
dependencies of the current TeX source.

### Figure generators

```bash
python scripts/build_manuscript_figures.py --output-dir build/figures
```

Omit `--output-dir` to write to `manuscript/figures/`. The wrapper is the
standard entry point and uses these generators:

| Script | Current outputs | Main inputs |
|---|---|---|
| `plot_theory_figures.py` | `figure_02_separators`, `figure_03_cycle`, `figure_04_realization`, `figure_05_workflow` | Exact constructions and declared workflow routes. |
| `plot_editorial_figures.py` | `figure_C_identifiability.pdf`, `figure_E_bcp_projection.pdf` | Frozen Experiment C data and an analytic conceptual density. |
| `plot_experiment_g.py` | `figure_G_mismatch.pdf` | Frozen Experiment G results. |

See [the complete figure source map](../manuscript/figures/README.md) for
placement, data populations, and scientific qualifications. Figure generation
requires Python 3.10+, NumPy, Matplotlib, and pandas. The article uses only the
seven vector PDFs; extra SVG exports are not TeX dependencies.

Repeated generation is checked within one environment. PDF bytes can differ
between font and rendering installations, and the current figure checker also
compares renderings against the committed figures. The compiled article PDF is
a separate build product and is outside the figure repeatability check.

### TeX dependencies

Use `latexmk`, pdfLaTeX, BibTeX, and `kpsewhich` with the pinned official
`elsarticle` 3.5 class and `elsarticle-num` style in `manuscript/`. The bundled
pair takes precedence over the distribution's versions; provenance and upstream
source/license material are in
[manuscript/tex-support/README.md](../manuscript/tex-support/README.md).
The arXiv helper includes this same pair and the allowlisted `tex-support/`
files. Python 3.10+ runs standard-library checks, and Poppler
supplies PDF inspection and rendering tools. The package list and Debian/Ubuntu
installation command, including `texlive-publishers`, `cm-super`, and
`poppler-utils`, are in
[manuscript/README.md](../manuscript/README.md#compile-the-article).

## Historical asset helpers

The following utilities retain the older asset-generation paths for inspecting
the archived evidence. Their output is isolated under ignored `build/legacy/`
directories; they do not supply the revised article's tables or figures.

| Script | Historical role | Default output |
|---|---|---|
| `build_manuscript_tables.py` | Export the older per-experiment table fragments from archived results. | `build/legacy/tables/` |
| `build_legacy_figures.py` | Rebuild the previous workflow, missing-data, J4 geometry, and J4 mask-transfer figure set. | `build/legacy/figures/` |
| `make_workflow_schematic.py` | Draw the previous workflow schematic. | Under `build/legacy/`. |
| `make_j4_geometry_cases.py` | Draw the archived molecular geometry examples. | Under `build/legacy/`. |
| `make_j4_mask_transfer_figure.py` | Draw the archived J4 mask-transfer plot. | Under `build/legacy/`. |
| `check_figure_binary_constancy.py` | Compare repeated output of the historical generator suite. | Temporary output; use `check_manuscript_figures.py` for current article figures. |

The shared `_figure_io.py` helper remains in use by historical and frozen
scientific plot writers. The experiment/data/result README files preserve their
original asset references and numbering. Use the
[current experiment crosswalk](../README.md#frozen-records-and-the-current-manuscript)
for present manuscript locations and the current article for evaluation
conventions.

## Full scientific rerun

```bash
bash scripts/rerun_paper_results.sh
```

Use a disposable checkout with the archived Python environment and `pyvoro2`
0.6.3 installed. Install the paper requirements with their archived constraints:

```bash
python -m pip install -r environments/requirements-py313.txt -c environments/requirements-lock-py313.txt
```

The constraints preserve the recorded package pins without rewriting the
environment files. This script writes experimental outputs: it runs Experiments
A–H and the committed-data Experiment J analyses, then builds the article from
the reviewed source and figure PDFs and runs the consistency check with
`--skip-frozen`. The scientific commands are retained from the archived
workflow. This is not needed to compile the article, regenerate its figures
from frozen results, or prepare its source ZIP. A deliberately rerun result tree
is no longer the untouched frozen evidence; compare it against v1.0.0 in a
separate checkout.

The current article figures and inline tables remain reviewed assets until
explicitly updated. The C/G figure generators check frozen input digests, so
the full rerun does not feed newly computed CSVs into them or claim that new
outputs retain the archived hashes.

The full rerun does not regenerate the upstream PySCF/Multiwfn molecular
calculations. Those optional workflows are documented in
[qtaim/README.md](qtaim/README.md), together with their separate dependencies.

## Environment capture and releases

`capture_environment_snapshot.py` records a Python lock file and a system note
under `environments/`. Running it rewrites archived environment files, so it is
not part of ordinary manuscript builds or figure reproduction. Use it only when
deliberately preparing a new computational snapshot; do not relabel a local
rendering environment as the environment that produced the frozen evidence.

See [docs/releasing.md](../docs/releasing.md) for metadata, source/PDF inclusion,
review, DOI verification, and publication gates.
