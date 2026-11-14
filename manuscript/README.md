# Manuscript

This directory contains the source of **“Fixed-site inverse fitting of
power-diagram weights from pairwise separator data.”** All commands below are
run from the repository root.

The current sources are the final manuscript submitted to *Computational and
Applied Mathematics* (CAM), synchronized from the pinned CAM baseline recorded
in [CAM_SYNC.md](CAM_SYNC.md). This development-tree update is not a release;
the published v1.0.0 and v2.0.0 archives retain their original contents and DOIs.

## Source structure

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

The article uses 15 authored TeX files, seven figure PDFs, and 34 cited
references. A local TeX Live 2025 build is 52 pages. The four tables are literal TeX; there
is no generated table-fragment dependency. The Experiment H candidate graphic
is not part of the article; the E/H table and accompanying discussion present
that comparison.

## Numerical table evidence

```bash
python scripts/check_manuscript_tables.py
```

The standard-library checker reads the four labeled table blocks and compares
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
| `sections/*.tex` | Nine included section files. |
| `appendices/*.tex` | Five included appendix files. |
| `figures/*.pdf` | The seven article figures. |
| `refs.bib` | Bibliography source. |
| `manuscript.bbl` | Bibliography generated by the fresh build. |
| `sn-jnl.cls`, `sn-mathphys-ay.bst` | The pinned official class and author–year bibliography style. |
| `TEMPLATE_PROVENANCE.md`, `CAM_SYNC.md`, `tex-support/README.md` | Publisher/source-baseline provenance and upstream license information. |
| `tex-support/glyphtounicode-cmr.tex` | Unmodified upstream Computer Modern Unicode mappings and license notice. |

The archive contains 30 files, carrying the same unmodified official
class/style and provenance as the canonical build. The remaining packages are
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
references. Use the [current experiment crosswalk](../README.md#frozen-records-and-the-current-manuscript)
and the article itself for present placement and evaluation conventions. The
v2.0.0 archive includes the tagged source tree and the compiled
`manuscript/manuscript.pdf`; see the [release notes](../docs/release-v2.0.0.md).
