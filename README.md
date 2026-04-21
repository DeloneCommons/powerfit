# powerfit

Frozen reproducibility repository for the manuscript **“Fixed-site inverse fitting of power-diagram weights from pairwise separator data.”**

This repository is the paper artifact. It contains the manuscript source, frozen
experiment protocols, archived results, molecular benchmark data, and the pinned
external binaries used by the paper-side reruns. The citable reproducibility
archive DOI is `10.5281/zenodo.19673558`
(<https://doi.org/10.5281/zenodo.19673558>). The canonical `pyvoro2` software
repository lives outside this archive.

## License scope for this archive

The repository contains both first-party materials and bundled third-party
software artifacts. The root [LICENSE](LICENSE) file covers the original
repository content; the bundled files under
[external_software/](external_software/README.md) retain their own upstream
licenses and notices. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)
for the precise scope split used by this archive. The Zenodo record is marked
as a mixed-license open archive; this does not relicense bundled third-party
artifacts under MIT.

## Read the repository in this order

1. [manuscript/README.md](manuscript/README.md) — manuscript entry point, main
   figures/tables, and PDF build notes.
2. [experiments/registry/README.md](experiments/registry/README.md) — stable
   crosswalk from manuscript labels A--H and J to configs, runners, analyses, and
   result roots.
3. [results/README.md](results/README.md) — archived outputs used by the
   manuscript.
4. [data/README.md](data/README.md) — frozen manifests and QTAIM/proatomic data
   behind Experiment J.
5. [scripts/README.md](scripts/README.md) — table, figure, PDF, and submission
   helpers.
6. [environments/README.md](environments/README.md),
   [external_software/README.md](external_software/README.md), and
   [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) — pinned runtime
   environment, bundled third-party artifacts, and archive license scope.
7. [submission/README.md](submission/README.md) — generated flat submission bundle.

For a reviewer or reader who only wants to understand the released artifact,
steps 1–3 are usually enough.

## Top-level layout

- [manuscript/](manuscript/README.md) — LaTeX source plus the final figure/table
  assets wired into the submission.
- [experiments/](experiments/README.md) — frozen synthetic protocols and the
  manuscript-to-code registry.
- [results/](results/README.md) — archived benchmark outputs used by the paper.
- [data/](data/README.md) — frozen molecular and proatomic inputs for Experiment
  J.
- [scripts/](scripts/README.md) — manuscript and submission build helpers.
- [environments/](environments/README.md) — Python dependency sets and the
  reference system note.
- [external_software/](external_software/README.md) — pinned `pyvoro2` wheel and
  the bundled Multiwfn binary.
- [submission/](submission/README.md) — generated flat upload bundle.
- [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) — scope note for bundled
  third-party software versus first-party repository content.

## Paper scope inside this repository

- **Experiments A–H**: compact synthetic validation and stress tests.
- **Experiment J**: the molecular QTAIM benchmark. This is the main empirical
  branch in the current manuscript, organized as J1 (dataset audit), J2
  (true-support ladder), J3 (candidate-graph recovery), and J4a--J4d
  (local validation, representative geometry, mask transfer, and box-margin
  robustness).

## Experiment map

| Label | Topic | Crosswalk | Results |
|---|---|---|---|
| A | Exact recovery | [A_exact_recovery.md](experiments/registry/A_exact_recovery.md) | `results/exact_recovery/` |
| B | Noise robustness | [B_noise_robustness.md](experiments/registry/B_noise_robustness.md) | `results/noise_robustness/` |
| C | Missing data / sparsity | [C_missing_data.md](experiments/registry/C_missing_data.md) | `results/missing_data/` and `results/missing_data_manuscript/` |
| D | Infeasible hard constraints | [D_infeasible_constraints.md](experiments/registry/D_infeasible_constraints.md) | `results/infeasible/` |
| E | Supergraph inputs and active-set refinement | [E_active_set.md](experiments/registry/E_active_set.md) | `results/active_set/` |
| F | Periodic wrong-image stress tests | [F_periodic_cases.md](experiments/registry/F_periodic_cases.md) | `results/periodic/` |
| G | Structured model mismatch | [G_model_mismatch.md](experiments/registry/G_model_mismatch.md) | `results/model_mismatch/` |
| H | Structured misspecification under supergraph uncertainty | [H_supergraph_mismatch.md](experiments/registry/H_supergraph_mismatch.md) | `results/supergraph_mismatch/` |
| J | Molecular QTAIM benchmark | [J_qtaim_molecular.md](experiments/registry/J_qtaim_molecular.md) | `results/qtaim_main/` |

## Relationship to `pyvoro2`

- Canonical package repository:
  `https://github.com/DeloneCommons/pyvoro2`
- Version-specific Zenodo archive for the exact `pyvoro2 0.6.3` snapshot used
  in this paper:
  `https://zenodo.org/records/19143984`
  (DOI `10.5281/zenodo.19143984`)
- This repository: manuscript, experiment definitions, archived results, and
  paper-side repro helpers.
- The pinned wheel provenance is recorded in
  `external_software/pyvoro2-version.txt`.

The repository logic is platform-agnostic, but the bundled wheel is a Linux
manylinux artifact. On non-Linux systems, install `pyvoro2==0.6.3` from PyPI or
build the same version from source instead of using the bundled wheel.

## Quick start

### Minimal paper-side environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r environments/requirements-py313.txt
pip install external_software/pyvoro2-0.6.3-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl
```


### Capture the exact release-time environment snapshot

When you are ready to freeze the final public artifact, capture the exact
Python environment and the concise system note with:

```bash
python scripts/capture_environment_snapshot.py
```

This rewrites `environments/system.txt` and
`environments/requirements-lock-py313.txt`. Run it only from the clean final
paper-side environment you want archived.

### Run the repository consistency audit

```bash
python scripts/check_repo_consistency.py
```

This fast audit checks markdown links, leaked absolute paths, documented runtime
requirements, flat-bundle consistency, and the recorded SHA256 digests of the
bundled `pyvoro2` wheel and `Multiwfn_noGUI` executable.

### Rerun the paper artifact from committed data

```bash
bash scripts/rerun_paper_results.sh
```

This reruns Experiments A--H, reruns the committed-data Experiment J analyses
(J1--J4d), then calls the canonical manuscript build to refresh manuscript-side
tables and figures, regenerate the flat submission bundle, build the local PDF
outputs, and finish with the repository consistency audit. It does not rerun
the upstream PySCF/Multiwfn molecular-generation pipeline.

### Refresh manuscript-side tables and figures

```bash
python scripts/build_manuscript_tables.py
python scripts/build_manuscript_figures.py
```

Use these targeted refreshers when you are editing only one asset family. For a
canonical end-to-end manuscript rebuild, prefer `bash scripts/build_manuscript_pdfs.sh`.
The figure script refreshes the manuscript-facing PDF/PNG files from the
lightweight figure generators and archived result figures. In the same locked
Python environment recorded under `environments/`, these manuscript-facing
figure assets are expected to be byte-identical across rebuilds; across other
environments, visual equivalence is the relevant check. The final LaTeX-built
`manuscript/manuscript.pdf` and `submission/flat/manuscript.pdf` remain separate
build products and are not part of that byte-stability guarantee. For a direct
spot check of the figure-side guarantee, run `python
scripts/check_figure_binary_constancy.py`; this reruns a representative subset
of the generators twice in a throwaway directory and compares hashes. For
targeted edits, use the source maps in
[manuscript/tables/README.md](manuscript/tables/README.md),
[manuscript/figures/README.md](manuscript/figures/README.md), and
[scripts/README.md](scripts/README.md); they list which script or archived
output regenerates each table and image.

### Build the local manuscript PDF and the flat submission bundle

```bash
bash scripts/build_manuscript_pdfs.sh
```

`manuscript/manuscript.pdf` and `submission/flat/manuscript.pdf` are local build
products created by that script and are not committed to the archive. The same
script first refreshes manuscript-side tables and figures, then rebuilds the
tracked submission artifact under `submission/flat/`. The canonical PDF build
requires both `latexmk` and `bibtex` on `PATH` and fails immediately if either
one is unavailable.

### Tiny smoke subset for CI or local checks

```bash
python experiments/runners/run_exact_recovery.py --smoke --output-dir .smoke/exact_recovery
python experiments/runners/run_noise_robustness.py --smoke --output-dir .smoke/noise_robustness
```

### Optional molecular-data regeneration helpers

The frozen paper artifact already contains the committed Experiment J data and
results. Only use the optional QTAIM/PySCF helpers if you want to regenerate the
molecular branch itself:

- [data/qtaim_main/README.md](data/qtaim_main/README.md)
- [data/proatomic/README.md](data/proatomic/README.md)
- [scripts/qtaim/README.md](scripts/qtaim/README.md)
- `pip install -r environments/requirements-qtaim.txt`
