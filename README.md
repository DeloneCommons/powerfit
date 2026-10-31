# powerfit

Manuscript and reproducibility materials for **“Fixed-site inverse fitting of
power-diagram weights from pairwise separator data.”**

The article studies how pairwise separator observations determine power-diagram
weights at fixed sites, and why fitting those observations must be distinguished
from realizing shared faces. This repository contains the revised LaTeX source,
its figures, and the frozen protocols, numerical results, molecular inputs, and
runtime artifacts underlying the experiments. The fitting software is maintained
separately in [pyvoro2](https://github.com/DeloneCommons/pyvoro2).

## Cite the project or the frozen evidence

| Resource | Persistent identifier | Use |
|---|---|---|
| Evolving `powerfit` project | [10.5281/zenodo.19673557](https://doi.org/10.5281/zenodo.19673557) | All-versions concept DOI; follows the latest published project release. |
| Frozen `powerfit` v1.0.0 | [10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558) | Exact experimental scripts, configurations, and numerical evidence used by the article. |
| `pyvoro2` 0.6.3 | [10.5281/zenodo.19143984](https://doi.org/10.5281/zenodo.19143984) | Version of the fitting and tessellation software used for the reported calculations. |

[CITATION.cff](CITATION.cff) uses the concept DOI for this evolving project and
also identifies the frozen evidence and software versions. The revised article
is available in this source tree. Until a new Zenodo release is published, the
concept DOI still resolves to the older v1.0.0 release; a working branch or local
PDF does not create a new deposit. See [the release procedure](docs/releasing.md)
for the remaining publication gates.

## Build the article

Run all commands below from the repository root. The seven figure PDFs and four
inline tables are already present. Compilation requires TeX, Poppler's PDF
inspection tools, and Python 3.10+ for standard-library checks; it needs no
scientific Python packages or experimental rerun.

Use `latexmk`, pdfLaTeX, and BibTeX with the pinned official `elsarticle` 3.5
class and `elsarticle-num` bibliography style included in `manuscript/`. This
unchanged upstream pair takes precedence over the distribution's version and
keeps the article layout consistent across installations. Its sources and
license provenance are documented in
[manuscript/tex-support/README.md](manuscript/tex-support/README.md). On Debian
or Ubuntu, install the remaining TeX and inspection dependencies with:

```bash
sudo apt-get update
sudo apt-get install python3 latexmk poppler-utils cm-super \
  texlive-latex-base texlive-latex-recommended texlive-latex-extra \
  texlive-publishers texlive-fonts-recommended
```

Then build:

```bash
bash scripts/build_manuscript_pdfs.sh
```

The output is `manuscript/manuscript.pdf`. The build compiles the checked-in
source and figure PDFs and regenerates the bibliography. It does not generate
figures, rewrite tables, or run experiments. The PDF and TeX build byproducts are
ignored local outputs. The source structure and package requirements are
documented in [manuscript/README.md](manuscript/README.md).

## Repository guide

| Location | Contents |
|---|---|
| [manuscript/](manuscript/README.md) | Main TeX file, Sections 1–9, Appendices A–E, bibliography, and seven vector figure PDFs. |
| [experiments/](experiments/README.md) | Frozen synthetic protocols, runners, analyses, and experiment registries. |
| [results/](results/README.md) | Frozen numerical outputs used by the article. |
| [data/](data/README.md) | Frozen molecular and proatomic inputs for Experiment J. |
| [scripts/](scripts/README.md) | Current figure, PDF, checking, and arXiv-bundle helpers, alongside historical utilities. |
| [environments/](environments/README.md) | Archived Python dependency sets and reference system information. |
| [external_software/](external_software/README.md) | Pinned `pyvoro2` wheel, bundled Multiwfn executable, and provenance notices. |
| [docs/releasing.md](docs/releasing.md) | Review, release, citation, and deposit procedure. |

### Frozen records and the current manuscript

The experimental evidence remains the v1.0.0 evidence. The files under
`experiments/`, `results/`, `data/`, `environments/`, `external_software/`, and
`scripts/qtaim/` retain their archived contents. Their README files and registry
entries preserve historical manuscript numbering, generated-asset links, and
descriptions. Use them to locate archived protocols and outputs; use the current
manuscript for its interpretation and qualifications. Some historical links
refer to superseded manuscript assets.

The current article organizes the synthetic tests in Section 6 and the
molecular application in Section 7. Appendix D gives the synthetic protocols;
Appendix E gives the molecular background, protocols, and limits of the auxiliary
checks. Experiment letters remain stable:

| Experiment | Topic | Current placement | Archived source map |
|---|---|---|---|
| A | Exact recovery | Section 6.1; Appendix D.3.1 | [A_exact_recovery.md](experiments/registry/A_exact_recovery.md) |
| B | Noise and outliers | Section 6.1; Appendix D.3.2 | [B_noise_robustness.md](experiments/registry/B_noise_robustness.md) |
| C | Missing observations and identifiability | Section 6.1; Appendix D.3.1 | [C_missing_data.md](experiments/registry/C_missing_data.md) |
| D | Hard-constraint feasibility | Section 6.1; Appendix D.3.1 | [D_infeasible_constraints.md](experiments/registry/D_infeasible_constraints.md) |
| E | Candidate-pair refinement with noisy targets | Section 6.3; Appendix D.3.4 | [E_active_set.md](experiments/registry/E_active_set.md) |
| F | Periodic image choices | Section 6.2; Appendix D.3.3 | [F_periodic_cases.md](experiments/registry/F_periodic_cases.md) |
| G | Structured separator mismatch and realized adjacency | Section 6.2; Appendix D.3.4 | [G_model_mismatch.md](experiments/registry/G_model_mismatch.md) |
| H | Refinement under structured mismatch | Section 6.3; Appendix D.3.4 | [H_supergraph_mismatch.md](experiments/registry/H_supergraph_mismatch.md) |
| J | Molecular separator fitting and geometric diagnostics | Section 7; Appendix E | [J_qtaim_molecular.md](experiments/registry/J_qtaim_molecular.md) |

In the current molecular account, J1 provides the dataset audit, J2 evaluates
known reference pairs, J3 fits distance-selected candidates, and J4a/J4b examine
local diagnostics and ranking within visible-face populations. Appendix E.5
states the scope of the J4c/J4d auxiliary checks. All three reported J3 cutoffs
contain the full reference-pair set, and the J4b ranking populations differ
between models; the current text makes these evaluation conventions explicit.

## Reproduce the current figures and run checks

Figure generation needs Python 3.10 or later, NumPy, Matplotlib, and pandas. The
archived full paper environment uses Python 3.13. For a lightweight figure
environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install numpy matplotlib pandas
```

Regenerate the current figure set from the local frozen results:

```bash
python scripts/build_manuscript_figures.py
```

Use `--output-dir build/figures` to inspect regenerated assets separately. No
simulation or molecular calculation is run. See
[the figure source map](manuscript/figures/README.md) for the seven inputs and
their interpretation. The four article tables are written directly in the TeX
sections and appendix; the historical table exporter does not generate them.

Run the repository and figure checks with:

```bash
python scripts/check_repo_consistency.py
python scripts/check_manuscript_figures.py
python -m unittest discover -s tests -v
```

The consistency audit verifies frozen scientific-file digests as well as the
current manuscript dependencies, links, requirements, and bundled binaries.
The figure check uses Poppler, writes temporary output, checks repeated generation
in the same environment, and compares renderings with the committed PDFs. Font and renderer
versions can change PDF bytes across environments, so matching the committed
files byte for byte is not a cross-platform guarantee. The focused tests check
figure constructions and build-helper behavior. These commands do not rerun the
scientific experiments.

## Prepare an arXiv source archive

```bash
python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip
```

The bundle helper builds the article and includes the freshly generated `.bbl`,
the authored TeX sources, the bibliography, the seven figure PDFs, and the pinned
official class/style with their source and license support. It preserves the
`sections/`, `appendices/`, `figures/`, and `tex-support/` paths. The archive is an ignored
build product. Creating it does not submit the article to arXiv. See
[manuscript/README.md](manuscript/README.md) for the bundle contents and
[docs/releasing.md](docs/releasing.md) for review and publication checks.

## Optional full scientific rerun

The source/PDF build and figure reproduction above use the archived evidence
directly. To rerun the experiments, use a disposable checkout because the full
rerun writes into experimental result directories. Install the full archived
paper environment first:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r environments/requirements-py313.txt -c environments/requirements-lock-py313.txt
python -m pip install external_software/pyvoro2-0.6.3-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl
bash scripts/rerun_paper_results.sh
```

The bundled wheel targets CPython 3.13 on Linux x86-64. On other platforms,
install or build the same `pyvoro2==0.6.3` version using the
[upstream package](https://github.com/DeloneCommons/pyvoro2); preserve the version
when comparing with the archived results.

The constraints file applies the archived package pins while retaining both
environment files unchanged. CI uses the same constrained installation.

The rerun executes Experiments A–H and the committed-data Experiment J analyses,
then compiles the article from the reviewed sources and figure PDFs and checks
repository consistency with `--skip-frozen`. Its scientific commands are the
archived commands. It does not rerun the upstream PySCF/Multiwfn
molecular-generation pipeline. New outputs are no longer an untouched copy of
the frozen evidence, so compare them with v1.0.0 in a separate checkout. The
article figures and inline tables remain the reviewed versions until explicitly
updated; the current figure generators deliberately verify frozen inputs and
are not run on newly computed results by this script.

Optional molecular-data regeneration is documented in
[scripts/qtaim/README.md](scripts/qtaim/README.md),
[data/qtaim_main/README.md](data/qtaim_main/README.md), and
[data/proatomic/README.md](data/proatomic/README.md). Historical table and figure
helpers write to `build/legacy/`; they are outside the current article build.

## License scope

The root [LICENSE](LICENSE) applies to first-party repository materials. Bundled
third-party artifacts retain their own upstream licenses and notices, as
specified in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md). The Zenodo
archive uses `Other (Open)` for this mixed-license collection; this does not
relicense the bundled software under MIT.
