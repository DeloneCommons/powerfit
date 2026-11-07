# powerfit

Source and reproducibility materials for **“Fixed-site inverse fitting of
power-diagram weights from pairwise separator data.”**

**Version 2.0.0** contains the revised mathematical article and its
reproducibility infrastructure. The article replaces the original manuscript;
its experimental protocols and numerical evidence are the unchanged [v1.0.0 archive](https://doi.org/10.5281/zenodo.19673558).
The fitting software is maintained separately in
[pyvoro2](https://github.com/DeloneCommons/pyvoro2).

Run the commands below from the repository root.

## 1. Read or build the article

The current source is [manuscript/manuscript.tex](manuscript/manuscript.tex).
The seven figure PDFs and four inline numerical tables are already included.
With TeX, Poppler and Python 3.10+ installed:

```bash
bash scripts/build_manuscript_pdfs.sh
```

This produces **`manuscript/manuscript.pdf`**, a 65-page article, from the
committed source and figures. It rebuilds the bibliography and checks the PDF.
It requires no scientific Python packages and performs no experiments.
See [TeX installation and source structure](manuscript/README.md) for the
dependency command and the bundled official `elsarticle` class/style.

To build the PDF and package the arXiv sources in one command:

```bash
python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip
```

The ZIP includes a fresh bibliography and the required source/figure files.
PDFs, ZIPs and other build outputs are ignored local files. Packaging does not
submit or publish the article.

## 2. Reproduce the seven figures and check the four tables

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
[figure source map](manuscript/figures/README.md) for inputs and interpretation.

The numerical tables are literal TeX, verified directly against the result CSVs:

```bash
python scripts/check_manuscript_tables.py
```

This standard-library check recomputes the E/H paired comparisons, J2 pooled
errors, J4b rankings and J3 candidate statistics. It reports mismatched cells
without rewriting the article. The
[table evidence map](manuscript/README.md#numerical-table-evidence) explains the
populations and aggregation rules. These figure/table commands reuse frozen
evidence; they do not repeat scientific calculations.

## 3. Find the code, configurations, inputs and results

| Location | Contents |
|---|---|
| [manuscript/](manuscript/README.md) | Current article, bibliography and seven figure PDFs. |
| [experiments/runners/](experiments/runners/) | Synthetic experiment runners A–H. |
| [experiments/configs/](experiments/configs/) | Frozen YAML protocols; the J YAML is a reference record, not a configuration loaded by the molecular CLIs. |
| [experiments/analysis/](experiments/analysis/) | Scientific postprocessing, including historical derived outputs. |
| [scripts/qtaim/](scripts/qtaim/) | Molecular analyses J and the separate PySCF/Multiwfn input-generation pipeline. |
| [data/](data/README.md) | Molecular manifests, geometries, wavefunctions, topology JSON and proatomic lookup data. |
| [results/](results/README.md) | Frozen run-level CSVs, summaries, metadata and historical derived assets. |
| [scripts/](scripts/README.md) | Current build/check commands and the scientific rerun entry point. |
| [environments/](environments/README.md) | Original requirements, package pins and recorded system information. |
| [external_software/](external_software/README.md) | Pinned `pyvoro2 0.6.3` wheel, Multiwfn executable and provenance. |

## 4. Repeat the scientific calculations

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
[scientific workflow guide](scripts/README.md#upstream-molecular-input-regeneration)
gives the fixed-manifest commands, additional environment and overwrite rules.
It also states which historical secondary outputs the default rerun excludes.

## 5. Understand the frozen v1.0.0 material

The new article changes the mathematics and interpretation, while retaining
the original experimental evidence. **989 files** under `experiments/`,
`results/`, `data/`, `environments/`, `external_software/`, `scripts/qtaim/`,
and the shared `scripts/_figure_io.py` remain byte-identical to
`80933a14c57d4766bd2c03b2990d949a452031fc` (`v1.0.0`).

Their historical READMEs, registry entries and source comments are frozen too:
old manuscript numbers, paths and commands describe v1.0.0. Use the current
guides for v2.0.0 commands. Retired manuscript-only generators are available in
the [v1.0.0 source](https://github.com/DeloneCommons/powerfit/tree/v1.0.0);
the experimental algorithms, postprocessing and shared scientific helpers remain
here because they are needed to understand or repeat the original calculations.

### Frozen records and the current manuscript

| Experiments | Current placement | Archived protocol |
|---|---|---|
| A / C / D: recovery, missing data, feasibility | Section 6.1; Appendix D.3.1 | [A](experiments/registry/A_exact_recovery.md), [C](experiments/registry/C_missing_data.md), [D](experiments/registry/D_infeasible_constraints.md) |
| B: noise and outliers | Section 6.1; Appendix D.3.2 | [B](experiments/registry/B_noise_robustness.md) |
| F: periodic images | Section 6.2; Appendix D.3.3 | [F](experiments/registry/F_periodic_cases.md) |
| G: structured mismatch | Section 6.2; Appendix D.3.4 | [G](experiments/registry/G_model_mismatch.md) |
| E / H: refinement | Section 6.3; Appendix D.3.4 | [E](experiments/registry/E_active_set.md), [H](experiments/registry/H_supergraph_mismatch.md) |
| J: molecular fitting and diagnostics | Section 7; Appendix E | [J](experiments/registry/J_qtaim_molecular.md) |

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
[the CI guide](.github/workflows/README.md) and
[release procedure](docs/releasing.md).

## Citation and licenses

| Resource | Persistent identifier |
|---|---|
| Evolving `powerfit` project | [10.5281/zenodo.19673557](https://doi.org/10.5281/zenodo.19673557), the all-versions concept DOI. |
| Frozen `powerfit` v1.0.0 evidence | [10.5281/zenodo.19673558](https://doi.org/10.5281/zenodo.19673558). |
| Fitting software `pyvoro2` 0.6.3 | [10.5281/zenodo.19143984](https://doi.org/10.5281/zenodo.19143984). |

[CITATION.cff](CITATION.cff) distinguishes these references. The concept DOI resolves to the latest **published** Zenodo version. Version
2.0.0 is prepared for manual deposit as a new version of the existing record;
see the [release procedure](docs/releasing.md). Its version DOI and date are
recorded after Zenodo publication.

The root [LICENSE](LICENSE) covers first-party materials. Bundled third-party
software retains its upstream terms in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md). The Zenodo archive uses
`Other (Open)` for the mixed-license collection.
