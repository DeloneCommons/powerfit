# Manuscript

This directory contains the source of **“Fixed-site inverse fitting of
power-diagram weights from pairwise separator data.”** All commands below are
run from the repository root.

The current sources are the final manuscript submitted to *Computational and
Applied Mathematics* (CAM), synchronized from the pinned CAM baseline recorded
in [CAM_SYNC.md](CAM_SYNC.md). This development-tree update is not a release;
the published v1.0.0 and v2.0.0 archives retain their original contents and DOIs.

## Source structure

The paths and numbering below describe the pinned CAM layout. Later revisions
use their active dependencies rather than this directory table as a CI inventory.

| Path | Role |
|---|---|
| [manuscript.tex](manuscript.tex) | Article entry point, abstract, front matter, availability and acknowledgments, bibliography, and includes. |
| [sections/](sections/) | Sections 1–9: introduction; observations; graph fitting; geometric realization; computational workflow; synthetic experiments; molecular application; discussion; conclusions. |
| [appendices/](appendices/) | Appendices A–E: graph and optimization arguments; geometry; perturbation estimates; algorithm and synthetic protocols; molecular background and protocols. |
| [refs.bib](refs.bib) | Bibliography source, including the powerfit v2.0.0 archive and pyvoro2 0.6.3 citations. |
| [figures/README.md](figures/README.md) | Source and interpretation map for the seven vector figure PDFs. |
| [sn-jnl.cls](sn-jnl.cls), [sn-mathphys-ay.bst](sn-mathphys-ay.bst) | Pinned, unmodified official Springer Nature class and author–year bibliography style. |
| [TEMPLATE_PROVENANCE.md](TEMPLATE_PROVENANCE.md), [tex-support/README.md](tex-support/README.md) | Publisher-file provenance, checksums, and retained upstream license information. |
| [CAM_SYNC.md](CAM_SYNC.md) | Public/CAM baselines, import scope, figure hashes, and packaging adaptations. |

At the pinned CAM baseline, the article used 15 authored TeX files, seven
figure PDFs and 34 cited references; a local TeX Live 2025 build was 52 pages.
These are dated observations, not current-manuscript acceptance counts. The four
reviewed numerical tables are literal TeX; there is no generated table-fragment
dependency. The Experiment H candidate graphic
is not part of the article; the E/H table and accompanying discussion present
that comparison.

## Numerical table evidence

```bash
python scripts/check_manuscript_tables.py
```

The standard-library checker locates the four reviewed labels through recursive
active inputs in source order, regardless of their current filenames, and compares
their numeric cells with calculations from the CSVs below. It reports table,
row and column on disagreement and never rewrites the TeX or results.

| Printed table | TeX source | Frozen evidence under `results/` | Aggregation |
|---|---|---|---|
| Table 1: E/H one-pass and refined fits | [sections/06_experiments.tex](sections/06_experiments.tex), `tab:refinement-paired` | `active_set/runs.csv`, `supergraph_mismatch/runs.csv` | Pair by seed and configuration; 20 E pairs and 72 H pairs with positive mismatch. Arithmetic mean of per-run scores; better/tied/worse counts from unrounded changes. |
| Table 2: J2 separator errors | [sections/07_molecular.tex](sections/07_molecular.tex), `tab:molecular-fits` | `qtaim_main/J2_true_support_ladder/edge_level.csv` | Pooled edge RMSE over 3,975 reference pairs: 3,703 bonded and 272 nonbonded. |
| Table 3: J4b rankings | [sections/07_molecular.tex](sections/07_molecular.tex), `tab:molecular-clearance-ranking` | `qtaim_main/J4_mask_transfer_refresh/edge_level.csv` | Average precision within each model's visible nonbonded faces, separately for clearance, distance and area. |
| Table 4: J3 candidate cutoffs | [appendices/appendix_e.tex](appendices/appendix_e.tex), `tab:molecular-candidates` | `qtaim_main/J3_candidate_recovery_refresh/{candidate,selected,qtaim}_edge_level.csv` | Whole realized graph and its visible subset; pooled reference-pair RMSE before visibility filtering, for each cutoff. |

For E/H, lower RMSE and higher F1 count as better; changes within an absolute
`1e-12` tolerance count as ties. Pair identities include configuration and seed,
so missing or duplicated partners fail. The historical E/H summary files use
different aggregations/populations and are not substituted for these raw runs.

J2 uses the stored position-error columns, including the raw proatomic error;
averaging per-molecule RMSEs would give a different statistic. J4b uses 2,269
Voronoi and 1,998 recovered-powerfit faces with 258 and 270 positives,
respectively. Scores rank by decreasing clearance, increasing distance, or
decreasing area. Average precision is the mean precision at positive ranks;
ties retain CSV row order, matching the
[v1.0.0 exporter](https://github.com/DeloneCommons/powerfit/blob/80933a14c57d4766bd2c03b2990d949a452031fc/scripts/build_manuscript_tables.py).
These model-specific populations are not a common candidate universe.

J3 includes realized pairs outside the fitted candidate set in its whole-graph
counts and visible precision/recall. Its common reference has 3,975 pairs per
cutoff; 3,973 are visible. The checker validates identities, required populations
and finite values as well as numbers at the precision printed in the article.
It is a focused check of these four tables, not a verifier of every numerical
statement in the manuscript.

## Compile the article

The build requires `latexmk`, pdfLaTeX, BibTeX, `kpsewhich`, and Poppler's
`pdfinfo` and `pdffonts` commands on `PATH`, plus Python 3.10+ for standard-library
source and PDF checks. It uses the pinned official `sn-jnl` class and
`sn-mathphys-ay` bibliography style included in this directory, from the
Springer Nature December 2024 distribution. Their upstream bytes and headers
are retained unchanged. The class selects the author–year style internally.
The wrapper also uses `fontenc`, `inputenc`, `lmodern`, `xcolor`, `amsmath`,
`amssymb`, `mathtools`, `graphicx`, `placeins`, `needspace`, and `booktabs`;
the class loads `hyperref`, `natbib`, `amsthm`, `geometry`, `setspace`,
`rotating`, `threeparttable`, `appendix`, `wrapfig`, and `fix-cm`.
The unmodified upstream `tex-support/glyphtounicode-cmr.tex` supplies
mathematical Unicode mappings for reliable text extraction across TeX versions;
it does not change the typeset content or load the `pdfx` package.

For Debian or Ubuntu:

```bash
sudo apt-get update
sudo apt-get install python3 latexmk poppler-utils lmodern \
  texlive-latex-base texlive-latex-recommended texlive-latex-extra \
  texlive-fonts-recommended
```

The bundled official class and style take precedence over distribution copies.
This pin keeps the reviewed layout independent of the distribution's publisher
version. See [TEMPLATE_PROVENANCE.md](TEMPLATE_PROVENANCE.md) and
[tex-support/README.md](tex-support/README.md) for upstream provenance and terms.
`lmodern` supplies scalable Latin Modern fonts for T1 encoding, and
`poppler-utils` supplies the PDF inspection and rendering tools. No scientific
Python packages are needed to compile the article.

```bash
bash scripts/build_manuscript_pdfs.sh
```

This compiles the committed sources and figures into
`manuscript/manuscript.pdf` and runs the bibliography build. It does not run
figure generators, export tables, or recompute scientific results. The article
PDF, generated `manuscript.bbl`, and auxiliary files are ignored build outputs.
The build first clears generated TeX auxiliaries so a previous publisher's
cached bibliography cannot prevent the CAM rebuild.

The build rejects Type 3 fonts and requires every font to be embedded, including
the workflow figure heading. There are no font-specific exceptions.

Unresolved citations/references, bibliography warnings, overfull boxes and
unexpected LaTeX/package warnings fail validation. For `sn-jnl` builds only,
the checker permits underfull boxes and the specific hyperref notice
`Difference (2) between bookmark levels is greater`: both also occur when the
unchanged CAM baseline is compiled. These layout notices are retained in the
logs; no source or publisher file is patched to suppress them.

## Revise the manuscript and review CI

Edit the authoritative master and its active literal inputs. The website builds
its inventory from those original sources in document order, so a file merely
present in a section/appendix directory is not active. Supported changes to
front metadata, ordinary prose/math, section structure, equation numbering,
references, tables or non-colliding figures are validated against their new
source-derived objects rather than fixed article totals. See the
[site grammar and validation guide](../site/README.md#validation-and-browser-inspection)
for the bounded command/environment support and evidence reports.

The Springer adapter requires unambiguous title, author, affiliation, email,
abstract, keywords and classification fields. It rejects unknown content before
`\maketitle`, unsupported scientific preamble macros/packages/options and
ambiguous metadata instead of omitting them. A new unsupported construct needs
a focused reader/adapter test and conversion-support change; it is not a reason
to skip coverage or weaken an unrelated check.

Smoke preserves the CAM first-page contract with source-derived metadata and
opening declaration text. Run it against the fresh PDF with:

```bash
python scripts/check_manuscript_titlepage.py \
  --manuscript manuscript/manuscript.tex --pdf manuscript/manuscript.pdf \
  --bbl manuscript/manuscript.bbl
```

It checks the supported plain-text fragments on page one, tolerating PDF
hyphenation, ligatures and punctuation spacing. Math, references and citations
within those fields are left to canonical compilation and independent site
coverage; the first-page text check does not claim their full PDF projection.

Fresh `.aux`, `.bbl` and `.fls` files supplement the original-source inventory
with label numbering, full formatted bibliography content/order and compiler
input evidence. Complete bibliography entry text is checked in HTML. A separate
bounded PDF regression derives alphanumeric page ranges from the fresh `.bbl`
and requires their full prefixes/digits in extracted PDF text. It supports
literal page fields and Springer's `pp.` notes, tolerates dash/line wrapping,
and does not claim complete PDF bibliography attribution or semantic validation.
Inspect `build/site-work/source-validation.json` and the other
[review artifacts](../site/README.md#actions-and-github-pages-configuration)
when diagnosing a conversion failure.

Some obligations intentionally require review. The four frozen numerical table
recipes and original seven approved figure identities retain their independent
scientific checks. The three selected mathematical role predicates are located
by source identity and tolerate renumbering; changing or removing their reviewed
expressions needs scientific review. A changed source expression with a reviewed
LaTeXML warning, a new warning role, or converter/binding/context drift needs the
finite JSON policy review described in the
[warning guide](../site/README.md#known-conversion-limits). Disappeared warnings
need not be recreated, and reports never grant automatic approval.

Run both required checks: `smoke` retains the scientific/PDF/package boundary;
`build` validates the website and browser reading behavior. The frozen manifest
is authenticated independently before its protected file hashes are checked.
Neither manuscript revisions nor checker maintenance authorize changing frozen
scientific evidence, the manifest baseline, historical tags or archival metadata.

## Regenerate or check figures

```bash
python scripts/build_manuscript_figures.py --output-dir build/figures
python scripts/check_manuscript_figures.py
python -m unittest discover -s tests -v
```

The figure builder reads the local frozen result files and supports
`--output-dir build/figures` for a separate output directory. It needs Python
3.10+, NumPy, Matplotlib, and pandas. The figure checker also uses Poppler,
writes temporary outputs, checks repeatability within the same environment, and compares the
rendered figures with their committed counterparts. Consult
[figures/README.md](figures/README.md) before changing any scientific
construction, data selection, or aggregation convention.

## Build an arXiv source archive

```bash
python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip
```

The helper performs a fresh article build before packaging the bibliography.
The source ZIP preserves the layout required by the TeX `\input` and
`\includegraphics` commands:

| Archive path | Contents |
|---|---|
| `manuscript.tex` | Main article source at the archive root. |
| Active section `.tex` paths | Included section files; nested literal dependency paths are preserved. |
| Active appendix `.tex` paths | Included appendix files; inactive orphan files are excluded. |
| Active graphic paths | Article graphics, including the original seven approved vector PDFs. |
| `refs.bib` | Bibliography source. |
| `manuscript.bbl` | Bibliography generated by the fresh build. |
| `sn-jnl.cls`, `sn-mathphys-ay.bst` | The pinned official class and author–year bibliography style. |
| `TEMPLATE_PROVENANCE.md`, `CAM_SYNC.md`, `tex-support/README.md` | Publisher/source-baseline provenance and upstream license information. |
| `tex-support/glyphtounicode-cmr.tex` | Unmodified upstream Computer Modern Unicode mappings and license notice. |

The archive contains the resolved active dependencies, carrying the same
unmodified official class/style and provenance as the canonical build. The remaining packages are
TeX-distribution dependencies. Unlike the journal portal's flat source export,
this public bundle retains nested sources and original figure filenames, with
no text expansion or figure renaming. Entries have stable timestamps and
permissions; the generated bibliography is refreshed before packaging.
Only resolved dependencies and the listed notices are included, excluding
administrative records, stale files, build logs, and the review PDF.
The ZIP is an ignored output under `build/`; it is not a
tracked flat submission tree. Review the built PDF and the archive before any
submission. Creating the archive does not publish a release or submit to arXiv.

## Release and evidence provenance

The [powerfit v2.0.0 archive](https://doi.org/10.5281/zenodo.24047266)
contains the archived v2.0.0 manuscript and reproducibility materials; it does
not identify the CAM-synchronized development tree. The numerical
evidence is unchanged from the
[v1.0.0 archive](https://doi.org/10.5281/zenodo.19673558), and the reported
fitting software is [pyvoro2 0.6.3](https://doi.org/10.5281/zenodo.19143984).
The [all-versions project DOI](https://doi.org/10.5281/zenodo.19673557)
identifies the published project versions, rather than an unpublished `main`.
`CITATION.cff`, `.zenodo.json` and the v2.0.0 release notes remain historical
archive metadata. No tag, release or deposit is created by this synchronization.

The frozen experiment registry retains its historical numbering and asset
references. Use the [current experiment crosswalk](../docs/archives.md#frozen-records-and-the-current-manuscript)
and the article itself for present placement and evaluation conventions. The
v2.0.0 archive includes the tagged source tree and the compiled
`manuscript/manuscript.pdf`; see the [release notes](../docs/release-v2.0.0.md).
