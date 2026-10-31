# Build, verification and scientific workflows

Run commands from the repository root. The [main README](../README.md) is the
starting point; this guide gives the command boundaries and detailed scientific
reproduction steps.

## Current article commands

| Task | Command | Reads and writes |
|---|---|---|
| Compile the article | `bash scripts/build_manuscript_pdfs.sh` | Reads committed TeX/PDFs; writes `manuscript/manuscript.pdf`, bibliography and TeX byproducts. |
| Generate seven figures | `python scripts/build_manuscript_figures.py --output-dir build/figures` | Reads exact constructions and frozen C/G results; writes seven PDFs and supplementary SVGs. |
| Check four inline tables | `python scripts/check_manuscript_tables.py` | Recomputes numerical cells from result CSVs; writes nothing. |
| Check frozen repository | `python scripts/check_repo_consistency.py` | Checks all 989 frozen files, source dependencies, links, requirements and bundled binaries; writes nothing. |
| Check figure reproduction | `python scripts/check_manuscript_figures.py` | Uses temporary outputs for repeatability, rendering, text and font checks. |
| Check scientific result completeness | `python scripts/check_rerun_results.py` | Checks expected run/system populations, fit outcomes and local diagnostic agreement; writes nothing. |
| Run focused tests | `python -m unittest discover -s tests -v` | Tests scientific aggregations, figure constructions and build/check helpers; no full scientific rerun. |
| Build PDF and arXiv ZIP | `python scripts/make_arxiv_bundle.py --output build/powerfit-arxiv.zip` | Builds once, then packages the source dependencies and fresh bibliography. |

The PDF build uses reviewed figures and literal TeX tables. It does not call
their generators or recompute experiments. The packager already builds the PDF;
there is no need to run the build command immediately before it. See
[manuscript/README.md](../manuscript/README.md) for TeX dependencies and archive
contents. All figure/article fonts must be embedded; Type 3 fonts are rejected.

### Figure inputs and outputs

The wrapper invokes three explicit generators:

| Generator | Outputs | Inputs |
|---|---|---|
| `plot_theory_figures.py` | Separators, cycle, realization, workflow | Exact geometric constructions and declared workflow routes. |
| `plot_editorial_figures.py` | C identifiability and BCP projection | Frozen C runs, summary and metadata; analytic conceptual density. |
| `plot_experiment_g.py` | G mismatch | Frozen paired G results and metadata. |

The default output directory is `manuscript/figures/`; use `--output-dir` to
inspect a separate build. `--results-root PATH` selects an unpacked result tree
with the same frozen contents. C/G input hashes, population and aggregation
checks remain enforced. No ZIP input mode is needed: the repository already
contains the results. See the [figure map](../manuscript/figures/README.md).

Figure generation needs NumPy, pandas and Matplotlib; the pinned lightweight
installation is in the main README. Figure checking additionally uses Poppler.
Repeated outputs must match within one environment; font/rendering versions
can change PDF bytes between environments. On restricted systems set
`MPLCONFIGDIR` to a writable directory.

The table and completeness checkers need only Python 3.10+. Both accept
`--results-root PATH`; the table checker also accepts `--manuscript-dir PATH`.
They compare the actual CSV contents with the current article and expected
protocol populations, without regenerating any table or figure. Their scopes
are separate from byte-for-byte frozen-artifact integrity.

## Full A–H and committed-data J rerun

Use a disposable checkout and the full Python 3.13 environment shown in the
main README: `requirements-py313.txt` constrained by
`requirements-lock-py313.txt`, plus `pyvoro2==0.6.3`. Neither PySCF nor Multiwfn
is run at this stage. Start with:

```bash
bash scripts/rerun_paper_results.sh
```

The wrapper checks the active `pyvoro2` version before writing, runs the
archived scientific commands in order, and stops on a failed command. Its final
steps check completeness and all four numerical tables. `PYTHON` can select a
specific interpreter. TeX is not required.

| Stage | Computation performed | Outputs under `results/` |
|---|---|---|
| A / B | Exact recovery; noise/outlier sweeps, with analyses | `exact_recovery/` (16 runs), `noise_robustness/` (144). |
| C | Standard missing-data sweep and analysis; dense manuscript sweep | `missing_data/` (30), `missing_data_manuscript/` (2,470). |
| D / E | Infeasible constraints; active-set refinement, with analyses | `infeasible/` (30), `active_set/` (40). |
| F / G / H | Periodic cases; model mismatch; supergraph refinement, with analyses | `periodic/` (132), `model_mismatch/` (2,280), `supergraph_mismatch/` (192). |
| J1 / J2 | Topology audit and known-support separator fits | `qtaim_main/J1_dataset_audit/`, `J2_true_support_ladder/`. |
| J3 | Fits at 4.0, 4.5 and 5.0 Å candidate cutoffs | `qtaim_main/J3_candidate_recovery_refresh/`. |
| J4b / J4a | Visible-face diagnostics at 5 Å padding; comparison with local formulas | `qtaim_main/J4_mask_transfer_refresh/`, `J4_local_diagnostic_validation/`. |
| J4d | Additional J4b runs at 3, 7 and 10 Å padding; four-margin summary | `qtaim_main/J4_mask_transfer_margin{3,7,10}_refresh/`, `J4_box_margin_summary_refresh/`. |

There are **5,334 synthetic rows** across the nine sweeps. Each molecular
analysis must process all 100 systems in `data/qtaim_main/systems_final.csv`
without skips; J3 has 300 system/cutoff fits. The completeness checker closes a
gap in the frozen molecular CLIs: `--require-all` rejects missing JSON files,
but other per-system errors can still be recorded as skips. J4a must have zero
visibility mismatches and finite clearance differences at most `1e-10` Å.
H's documented `cycle_detected` refinement outcomes are valid results and are
not treated as failed runs.

J reads atom positions/topology from the committed QTAIM JSON and uses the
frozen proatomic separator lookup. The J YAML under `experiments/configs/`
records the protocol; these CLIs use their own arguments/defaults. In the J4d
padding comparison, the Voronoi diagrams are recomputed at each margin, while
the recovered-powerfit rows are reused from J3. It is not a fresh powerfit
tessellation at each padding value; Appendix E states this limitation.

### What to compare after a rerun

The wrapper checks completeness and agreement at the precision printed in the
four tables. That is useful evidence of numerical reproduction, not a claim
that every historical file was recreated or every floating-point bit matches.
Compare raw scientific quantities with the frozen CSVs for deeper analysis;
exclude runtime, timestamps and machine/commit provenance from byte comparisons.
Do not replace the evidence or refresh its digest manifest to make new runs pass
the repository-integrity check.

The default rerun excludes the old manuscript-only generators, the curated J4c
geometry panel, upstream molecular input generation and some historical
secondary summaries. In particular, the dense C runner writes raw results, not
the archived `manuscript_analysis/` figure summary. To reaggregate that sweep
for comparison, keep the output separate:

```bash
python experiments/analysis/plot_missing_data_manuscript.py \
  --runs results/missing_data_manuscript/runs.csv \
  --output-dir build/rerun-comparison/missing_data_manuscript_analysis
```

This archived analysis also writes its historical plots/table fragment into
that output directory. Omit `--figure-path` to avoid an additional manuscript
copy. The current figure generators deliberately require frozen input bytes;
they are not a plotting interface for arbitrary newly computed result trees.

## Upstream molecular input regeneration

This separate calculation reconstructs the inputs consumed by J. Run it only
in a disposable checkout: the explicit `--overwrite` flags below replace
committed molecular/proatomic files. Without those flags, the PySCF runners
skip existing outputs, and the pair-law builder refuses existing lookup files.

Add the quantum-chemistry dependencies to the pinned scientific environment:

```bash
python -m pip install -r environments/requirements-qtaim.txt -c environments/requirements-lock-py313.txt
```

The archived constraints include PySCF 2.12.1 and geomeTRIC 1.1. The Multiwfn
runners default to the bundled executable and `settings.ini` under
`external_software/`. The commands below use four CPU threads; actual runtime
depends on the molecules and machine. Check each stage's CSV status/convergence
and error logs before consuming its outputs: a completed process alone does
not establish that every molecular calculation succeeded.

### Fixed 100-molecule benchmark

Use **`data/qtaim_main/systems_final.csv`** for each stage. Paths in a manifest
are resolved relative to its directory. The historical
`data/qtaim_main/systems.csv` example names an absent file;
`data/qtaim_main/selection/systems.csv` is an audit copy whose relative artifact
paths do not resolve from `selection/`. Neither is the current runnable input.

```bash
python scripts/qtaim/run_pyscf_geomopt.py \
  data/qtaim_main/systems_final.csv --nproc 4 --overwrite
python scripts/qtaim/run_pyscf_singlepoint.py \
  data/qtaim_main/systems_final.csv --nproc 4 --overwrite
python scripts/qtaim/run_multiwfn_topology.py \
  data/qtaim_main/systems_final.csv --nproc 4 --overwrite
```

The first command builds RDKit conformers from each SMILES (100 requested
conformers, seed 61453, MMFF94/UFF ranking), then optimizes the selected geometry
with PySCF/geomeTRIC. The second computes wavefunctions and exports Molden files;
the third runs Multiwfn topology searches and writes parsed critical-point JSON.
The molecular defaults are B3LYP/def2-SVP, DFT grid level 3 and SCF tolerance
`1e-9`, with charge/multiplicity from the manifest.

The small `data/qtaim_showcase/` dataset has deliberately fixed ideal and
symmetry-broken geometries. Its downstream single-point/topology workflow is
documented in the frozen [QTAIM guide](qtaim/README.md); do not apply the main
benchmark geometry-optimization command to that showcase.

### Proatomic reference branch

```bash
python scripts/qtaim/run_pyscf_atomic_singlepoint.py \
  data/proatomic/atom_manifest.csv --nproc 4 --overwrite
python scripts/qtaim/run_multiwfn_radial_density.py \
  data/proatomic/atom_manifest.csv --nproc 4 --overwrite
python scripts/qtaim/build_proatomic_separator_lookup.py --overwrite
```

This generates isolated-atom wavefunctions for H, C, N, O, F, S and Cl; samples
radial densities with Multiwfn; and builds the separator lookup used by J.
Atomic references use the manifest's states, B3LYP/def2-SVP, grid level 5 and
SCF tolerance `1e-10`. The radial grid has 501 points from 0 to 5 Å with 2,030
angular integration points. The pair-law grid spans 0.5–5 Å in 0.01 Å steps.
After both upstream branches succeed, run the A–H/J wrapper to evaluate the new
inputs; any changed numerical tables should be investigated, not overwritten.

`select_pubchem_main.py` is for a new online selection. A fixed random seed
cannot freeze a changing PubChem search universe. The archive includes the
selected manifests and selection audit, not a raw PubChem bulk snapshot; use
the fixed manifest above when repeating this benchmark. Fresh quantum-chemistry
outputs can also vary with numerical libraries and convergence, so their byte
identity with the archived wavefunctions/topology is not promised.

## Why historical code remains

The experiment runners, scientific postprocessing, QTAIM helpers and shared
`_figure_io.py` are part of the frozen computational record and remain intact.
Their README files and comments can name old tables, figure helpers or paths.
Those instructions describe the original article, recoverable through the
[v1.0.0 tag](https://github.com/DeloneCommons/powerfit/tree/v1.0.0).

The seven retired manuscript/environment utilities have no role in the current
workflow and were removed. In particular, normal builds never recapture or
overwrite the archived environment snapshot. The current guides supply the
correct commands without cosmetically editing protected historical files.
See [docs/releasing.md](../docs/releasing.md) for later release/deposit decisions.
